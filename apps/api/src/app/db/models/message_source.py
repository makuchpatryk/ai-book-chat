"""Citations for assistant messages — which chunks were used to answer."""

import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MessageSource(Base):
    __tablename__ = "message_sources"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE")
    )
    score: Mapped[int | None] = mapped_column(nullable=True)
    rank: Mapped[int]

    message = relationship("Message", back_populates="sources")
    chunk = relationship("Chunk")

    __table_args__ = (UniqueConstraint("message_id", "chunk_id"),)
