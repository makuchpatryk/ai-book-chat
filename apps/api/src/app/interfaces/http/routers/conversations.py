"""Chat endpoints — conversations and messaging (thin layer)."""

from collections.abc import AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.application.usecases.chat.ask_question import AskQuestion
from app.application.usecases.chat.create_conversation import CreateConversation
from app.application.usecases.chat.delete_conversation import DeleteConversation
from app.application.usecases.chat.get_messages import GetMessages
from app.application.usecases.chat.list_conversations import ListConversations
from app.infrastructure.config.settings import Settings, get_settings
from app.interfaces.http.composition import (
    get_ask_question,
    get_create_conversation,
    get_delete_conversation,
    get_get_messages,
    get_list_conversations,
)
from app.interfaces.http.schemas.chat import (
    ConversationRead,
    MessageRead,
    SendMessageRequest,
    SourceRead,
)
from app.interfaces.http.sse import with_heartbeat


router = APIRouter(tags=["chat"])


@router.post("/documents/{document_id}/conversations", response_model=ConversationRead, status_code=201)
async def create_conversation(
    document_id: UUID,
    use_case: CreateConversation = Depends(get_create_conversation),
) -> ConversationRead:
    """Create a new conversation for a document."""
    conversation = await use_case.execute(document_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")

    return ConversationRead(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at.isoformat(),
    )


@router.get("/documents/{document_id}/conversations", response_model=list[ConversationRead])
async def list_conversations(
    document_id: UUID,
    use_case: ListConversations = Depends(get_list_conversations),
) -> list[ConversationRead]:
    """List all conversations for a document."""
    conversations = await use_case.execute(document_id)
    if conversations is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")

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
    use_case: GetMessages = Depends(get_get_messages),
) -> list[MessageRead]:
    """Get all messages in a conversation."""
    messages = await use_case.execute(conversation_id)
    if messages is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")

    response = []
    for msg in messages:
        sources_list = []
        for source in msg.sources if hasattr(msg, "sources") else []:
            chunk = source.chunk
            if chunk:
                section_title = chunk.section.title if hasattr(chunk, "section") and chunk.section else None
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
    use_case: DeleteConversation = Depends(get_delete_conversation),
) -> None:
    """Delete a conversation (cascades to messages and sources)."""
    success = await use_case.execute(conversation_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: UUID,
    request: SendMessageRequest,
    use_case: AskQuestion = Depends(get_ask_question),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Send a message and stream the response with sources, tokens, and completion."""
    events = use_case.execute(conversation_id, request.content)

    async def event_generator() -> AsyncGenerator[str, None]:
        async for frame in with_heartbeat(events, settings.chat_heartbeat_seconds):
            yield frame

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
