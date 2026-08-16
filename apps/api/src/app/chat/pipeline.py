"""Chat pipeline: rewrite → search → guard → generate → persist."""

import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.generate import ChatMessage, Generator, GenerationDone, TextDelta
from app.chat.prompts import ANSWER_PROMPT
from app.chat.rewrite import rewrite as rewrite_question
from app.config import Settings
from app.db.models import Message, MessageRole, MessageSource
from app.retrieval.pipeline import search as search_pipeline
from app.services import conversations as conv_service

logger = logging.getLogger(__name__)


@dataclass
class SourcesEvent:
    """Streamed when retrieval is complete."""

    results: list[dict]
    pages: list[int]


@dataclass
class TokenEvent:
    """Streamed per text delta."""

    text: str


@dataclass
class DoneEvent:
    """Streamed when generation completes."""

    grounded: bool
    truncated: bool


@dataclass
class ErrorEvent:
    """Streamed on error."""

    detail: str


StreamEventType = SourcesEvent | TokenEvent | DoneEvent | ErrorEvent


async def answer(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    user_question: str,
    generator: Generator,
    rewriter_impl: "Rewriter",
    settings: Settings,
) -> AsyncIterator[StreamEventType]:
    """Generate an answer to a question, streaming sources, tokens, and done event.

    Returns an async generator of StreamEventType events.
    """
    try:
        # Get conversation and recent history
        conversation = await conv_service.get_conversation(db, conversation_id)
        if conversation is None:
            yield ErrorEvent(detail="conversation not found")
            return

        # Get recent turns for rewriting (exclude current user message, which hasn't been persisted yet)
        recent_history = await conv_service.recent_turns(
            db, conversation_id, limit=settings.chat_history_turns
        )

        # Step 1: Rewrite the question using history
        rewritten_question = await rewrite_question(
            user_question, recent_history, rewriter_impl, settings
        )
        if rewritten_question != user_question:
            logger.info(f"rewrite: {user_question!r} -> {rewritten_question!r}")

        # Step 2: Retrieve matching chunks
        search_outcome = await search_pipeline(
            db, conversation.document_id, rewritten_question, settings
        )

        # Step 3: Check if grounded (has relevant results)
        grounded = search_outcome.grounded

        # Emit sources event
        pages_set = set()
        source_results = []
        for candidate, score in search_outcome.results:
            chunk = candidate.chunk
            source_results.append(
                {
                    "chunk_id": str(chunk.id),
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "score": score,
                    "section_title": candidate.section_title,
                    "snippet": chunk.content[:240],
                }
            )
            pages_set.update(range(chunk.page_start, chunk.page_end + 1))

        pages_list = sorted(list(pages_set))
        yield SourcesEvent(results=source_results, pages=pages_list)

        # If not grounded, emit refusal and return
        if not grounded:
            yield TokenEvent(text="I couldn't find that in this document.")
            yield DoneEvent(grounded=False, truncated=False)
            return

        # Step 4: Generate answer using retrieved chunks
        context_chunks = [candidate.chunk for candidate, _ in search_outcome.results]
        chunk_text = "\n\n".join(
            f"[Page {c.page_start}-{c.page_end}] {c.content}" for c in context_chunks
        )

        # Build conversation history for context (last N turns)
        chat_messages = [
            ChatMessage(role=role, content=content)
            for role, content in recent_history
        ]
        chat_messages.append(ChatMessage(role="user", content=user_question))

        # Generate with context
        system_prompt = f"{ANSWER_PROMPT}\n\nContext from the document:\n{chunk_text}"
        answer_text = ""
        truncated = False
        async for event in generator.stream(system_prompt, chat_messages):
            if isinstance(event, TextDelta):
                answer_text += event.text
                yield TokenEvent(text=event.text)
            elif isinstance(event, GenerationDone):
                # "max_tokens" is Anthropic's vocabulary, "length" is the
                # OpenAI-compatible one the HF router speaks.
                truncated = event.stop_reason in ("max_tokens", "length")
                logger.info(
                    "generation usage",
                    extra={
                        "phase": "generate",
                        "provider": settings.chat_provider,
                        "model": settings.chat_model,
                        "input_tokens": event.input_tokens,
                        "output_tokens": event.output_tokens,
                        "estimated": event.estimated,
                        "conversation_id": str(conversation_id),
                        "document_id": str(conversation.document_id),
                    },
                )

        # Step 5: Return done event (persistence happens in the route)
        yield DoneEvent(grounded=True, truncated=truncated)

    except Exception as e:
        logger.exception(f"answer generation failed: {e}")
        yield ErrorEvent(detail=f"generation failed: {str(e)}")
