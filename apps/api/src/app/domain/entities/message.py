"""Message entity — a message in a conversation."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.domain.values.status import MessageRole


@dataclass
class Message:
    """A message in a conversation."""

    id: UUID
    conversation_id: UUID
    role: MessageRole
    content: str
    order_index: int
    grounded: bool = False
    truncated: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
