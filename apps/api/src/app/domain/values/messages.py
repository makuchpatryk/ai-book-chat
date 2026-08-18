"""Message-related value objects."""

from dataclasses import dataclass

from app.domain.values.status import MessageRole


@dataclass(frozen=True)
class Turn:
    """A (role, content) pair in a conversation history."""

    role: MessageRole
    content: str
