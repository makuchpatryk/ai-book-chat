"""Conversation entity — a sequence of messages about a document."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass
class Conversation:
    """A conversation about a document."""

    id: UUID
    document_id: UUID
    title: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @staticmethod
    def derive_title(text: str, max_length: int = 60) -> str:
        """Derive a conversation title from the first message, word-boundary trimmed."""
        if not text or len(text) <= max_length:
            return text.strip()

        trimmed = text[:max_length].strip()
        last_space = trimmed.rfind(" ")
        if last_space > 0:
            trimmed = trimmed[:last_space]
        return trimmed + "…"
