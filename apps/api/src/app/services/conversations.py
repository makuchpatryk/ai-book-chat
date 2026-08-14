"""Conversation service — CRUD and helper operations."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation, Message, MessageRole

if TYPE_CHECKING:
    from sqlalchemy.orm import AsyncSession as AsyncSessionType


async def create_conversation(
    db: "AsyncSessionType", document_id: uuid.UUID, title: str | None = None
) -> Conversation:
    """Create a new conversation."""
    conversation = Conversation(document_id=document_id, title=title)
    db.add(conversation)
    await db.flush()
    return conversation


async def get_conversation(db: "AsyncSessionType", conversation_id: uuid.UUID) -> Conversation | None:
    """Get a conversation by ID."""
    result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    return result.scalar_one_or_none()


async def list_conversations(db: "AsyncSessionType", document_id: uuid.UUID) -> list[Conversation]:
    """List all conversations for a document."""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.document_id == document_id)
        .order_by(Conversation.created_at.desc())
    )
    return result.scalars().all()


async def delete_conversation(db: "AsyncSessionType", conversation_id: uuid.UUID) -> bool:
    """Delete a conversation (cascades to messages and sources)."""
    conversation = await get_conversation(db, conversation_id)
    if conversation is None:
        return False
    await db.delete(conversation)
    await db.flush()
    return True


async def next_order_index(db: "AsyncSessionType", conversation_id: uuid.UUID) -> int:
    """Get the next order_index for a message in this conversation."""
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.order_index.desc())
        .limit(1)
    )
    last_message = result.scalar_one_or_none()
    return (last_message.order_index + 1) if last_message else 0


async def recent_turns(
    db: "AsyncSessionType", conversation_id: uuid.UUID, limit: int
) -> list[tuple[str, str]]:
    """Get the most recent N message turns (role, content pairs)."""
    result = await db.execute(
        select(Message.role, Message.content)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.order_index.desc())
        .limit(limit * 2)  # User + assistant pairs
    )
    messages = result.all()
    # Reverse to get chronological order
    return [(str(role), content) for role, content in reversed(messages)]


def derive_title(text: str, max_length: int = 60) -> str:
    """Derive a conversation title from the first message, word-boundary trimmed."""
    if not text or len(text) <= max_length:
        return text.strip()

    # Trim to max_length, then back to word boundary
    trimmed = text[:max_length].strip()
    # Find last space
    last_space = trimmed.rfind(" ")
    if last_space > 0:
        trimmed = trimmed[:last_space]
    return trimmed + "…"
