"""Messages in a conversation — user and assistant turns."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.message_source import MessageSource


class MessageRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[MessageRole] = mapped_column(
        # The pg enum labels are the member *values* ("user"), not the names
        # ("USER") SQLAlchemy would send by default.
        Enum(
            MessageRole,
            name="message_role",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        )
    )
    content: Mapped[str] = mapped_column(Text)
    order_index: Mapped[int]

    grounded: Mapped[bool | None] = mapped_column(nullable=True)
    truncated: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sources: Mapped[list["MessageSource"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MessageSource.rank",
    )

    conversation = relationship("Conversation", back_populates="messages")

    __table_args__ = (UniqueConstraint("conversation_id", "order_index"),)
