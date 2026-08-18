"""A detected chapter/section of a document — the boundary chunking never crosses."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.chunk import Chunk
    from app.infrastructure.db.models.document import Document


class Section(Base):
    __tablename__ = "sections"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(512))
    order_index: Mapped[int]
    start_page: Mapped[int]
    end_page: Mapped[int]

    document: Mapped["Document"] = relationship(back_populates="sections")
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="section",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Chunk.order_index",
    )

    __table_args__ = (UniqueConstraint("document_id", "order_index"),)
