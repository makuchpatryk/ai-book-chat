"""Chat endpoints — conversations and messaging."""

import asyncio
import logging
from uuid import UUID

import anyio
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AppSettings, DbSession
from app.db.session import AsyncSessionLocal
from app.chat.generate import build_generator
from app.chat.pipeline import DoneEvent, ErrorEvent, SourcesEvent, TokenEvent, answer
from app.chat.rewrite import build_rewriter
from app.db.models import Conversation, DocumentStatus, Message, MessageRole, MessageSource
from app.schemas.chat import (
    ConversationRead,
    DonePayload,
    ErrorPayload,
    MessageRead,
    SendMessageRequest,
    SourceRead,
    SourcesPayload,
    TokenPayload,
)
from app.services import conversations as conv_service
from app.services import documents as doc_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@router.post("/documents/{document_id}/conversations", response_model=ConversationRead, status_code=201)
async def create_conversation(
    document_id: UUID,
    db: DbSession,
) -> ConversationRead:
    """Create a new conversation for a document."""
    document = await doc_service.get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")

    conversation = await conv_service.create_conversation(db, document_id)
    await db.commit()

    return ConversationRead(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at.isoformat(),
    )


@router.get("/documents/{document_id}/conversations", response_model=list[ConversationRead])
async def list_conversations(
    document_id: UUID,
    db: DbSession,
) -> list[ConversationRead]:
    """List all conversations for a document."""
    document = await doc_service.get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")

    conversations = await conv_service.list_conversations(db, document_id)

    return [
        ConversationRead(
            id=c.id,
            title=c.title,
            created_at=c.created_at.isoformat(),
        )
        for c in conversations
    ]


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageRead])
async def get_messages(
    conversation_id: UUID,
    db: DbSession,
) -> list[MessageRead]:
    """Get all messages in a conversation."""
    conversation = await conv_service.get_conversation(db, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")

    # Load messages with sources using joinedload for chunks
    from app.db.models import Chunk

    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.order_index)
        .options(selectinload(Message.sources).joinedload(MessageSource.chunk))
    )
    messages = result.unique().scalars().all()

    response = []
    for msg in messages:
        sources_list = []
        for source in msg.sources:
            chunk = source.chunk
            if chunk:
                section_title = chunk.section.title if chunk.section else None
                source_item = SourceRead(
                    chunk_id=chunk.id,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    score=source.score,
                    section_title=section_title,
                    snippet=chunk.content[:240],
                )
                sources_list.append(source_item)

        response.append(
            MessageRead(
                id=msg.id,
                role=msg.role.value,
                content=msg.content,
                grounded=msg.grounded,
                truncated=msg.truncated,
                sources=sources_list,
            )
        )

    return response


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: UUID,
    db: DbSession,
) -> None:
    """Delete a conversation (cascades to messages and sources)."""
    success = await conv_service.delete_conversation(db, conversation_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")

    await db.commit()


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: UUID,
    request: SendMessageRequest,
    db: DbSession,
    settings: AppSettings,
) -> StreamingResponse:
    """Send a message and stream the response with sources, tokens, and completion."""

    # Validate conversation exists
    conversation = await conv_service.get_conversation(db, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")

    # Validate document is READY
    document = await doc_service.get_document(db, conversation.document_id)
    if document is None or document.status != DocumentStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="document not ready for chat"
        )

    # Persist user message
    order_index = await conv_service.next_order_index(db, conversation_id)
    user_message = Message(
        conversation_id=conversation_id,
        role=MessageRole.USER,
        content=request.content,
        order_index=order_index,
    )
    db.add(user_message)

    # Set title if unset
    if conversation.title is None:
        conversation.title = conv_service.derive_title(request.content)

    await db.commit()

    # Return 200 with streaming response
    async def event_generator():
        """Generate SSE events."""
        # Open own session for streaming (request-scoped session is torn down after response)
        async with AsyncSessionLocal() as stream_db:
            queue: asyncio.Queue = asyncio.Queue()
            producer_task: asyncio.Task | None = None

            async def producer():
                """Feed pipeline events into the queue."""
                try:
                    generator = build_generator(settings)
                    rewriter = build_rewriter(settings)

                    async for event in answer(
                        stream_db, conversation_id, request.content, generator, rewriter, settings
                    ):
                        await queue.put(event)
                except Exception as e:
                    await queue.put(ErrorEvent(detail=f"generation failed: {str(e)}"))
                finally:
                    await queue.put(None)

            async def stop_producer() -> None:
                """Cancel the producer and wait for it to actually stop.

                cancel() only requests cancellation; the task may still be mid-query
                on stream_db, and an AsyncSession cannot be driven by two coroutines
                at once. Anything that touches stream_db afterwards must await this.
                """
                if producer_task is None or producer_task.done():
                    return
                producer_task.cancel()
                await asyncio.gather(producer_task, return_exceptions=True)

            answer_text = ""
            retrieved_chunks = []
            grounded = False
            truncated = False
            persisted = False

            try:
                producer_task = asyncio.create_task(producer())

                while True:
                    try:
                        event = await asyncio.wait_for(
                            queue.get(), timeout=settings.chat_heartbeat_seconds
                        )
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"
                        continue

                    if event is None:
                        break

                    if isinstance(event, SourcesEvent):
                        payload = SourcesPayload(
                            results=[
                                {
                                    "chunk_id": r["chunk_id"],
                                    "page_start": r["page_start"],
                                    "page_end": r["page_end"],
                                    "score": r["score"],
                                    "section_title": r["section_title"],
                                    "snippet": r["snippet"],
                                }
                                for r in event.results
                            ],
                            pages=event.pages,
                        )
                        yield f"event: sources\ndata: {payload.model_dump_json()}\n\n"
                        retrieved_chunks = event.results

                    elif isinstance(event, TokenEvent):
                        answer_text += event.text
                        payload = TokenPayload(text=event.text)
                        yield f"event: token\ndata: {payload.model_dump_json()}\n\n"

                    elif isinstance(event, DoneEvent):
                        grounded = event.grounded
                        truncated = event.truncated
                        # Safe to use stream_db here: the pipeline issues no further
                        # queries after it yields DoneEvent.
                        try:
                            persisted_message = await persist_assistant_message(
                                stream_db,
                                conversation_id,
                                answer_text,
                                retrieved_chunks,
                                grounded=grounded,
                                truncated=truncated,
                            )
                        except Exception as exc:
                            # A failed save must not tear down the response mid-body:
                            # the client has already seen the answer stream.
                            logger.exception(f"failed to persist assistant message: {exc}")
                            await stream_db.rollback()
                            payload = ErrorPayload(detail="failed to save the answer")
                            yield f"event: error\ndata: {payload.model_dump_json()}\n\n"
                            break

                        persisted = True
                        payload = DonePayload(
                            message_id=str(persisted_message.id),
                            grounded=grounded,
                            truncated=truncated,
                        )
                        yield f"event: done\ndata: {payload.model_dump_json()}\n\n"

                    elif isinstance(event, ErrorEvent):
                        payload = ErrorPayload(detail=event.detail)
                        yield f"event: error\ndata: {payload.model_dump_json()}\n\n"

            except anyio.get_cancelled_exc_class():
                # Client disconnected — persist what we streamed, flagged truncated.
                with anyio.CancelScope(shield=True):
                    await stop_producer()
                    if not persisted:
                        try:
                            await persist_assistant_message(
                                stream_db,
                                conversation_id,
                                answer_text,
                                retrieved_chunks,
                                grounded=grounded,
                                truncated=True,
                            )
                        except Exception as exc:
                            logger.exception(
                                f"failed to persist truncated assistant message: {exc}"
                            )
                            await stream_db.rollback()
                raise
            finally:
                # stream_db is closed on the way out of the `async with`; the
                # producer must be off it first.
                with anyio.CancelScope(shield=True):
                    await stop_producer()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def persist_assistant_message(
    db: AsyncSession,
    conversation_id: UUID,
    answer_text: str,
    retrieved_chunks: list[dict],
    grounded: bool,
    truncated: bool,
) -> Message:
    """Persist assistant message and its sources to the database.

    Returns the persisted Message row.
    """
    order_index = await conv_service.next_order_index(db, conversation_id)
    assistant_message = Message(
        conversation_id=conversation_id,
        role=MessageRole.ASSISTANT,
        content=answer_text,
        grounded=grounded,
        truncated=truncated,
        order_index=order_index,
    )
    db.add(assistant_message)
    await db.flush()

    # Persist message sources
    for rank, chunk_data in enumerate(retrieved_chunks):
        source = MessageSource(
            message_id=assistant_message.id,
            chunk_id=UUID(chunk_data["chunk_id"]),
            score=chunk_data.get("score"),
            rank=rank,
        )
        db.add(source)

    await db.commit()
    return assistant_message
