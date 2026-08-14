"""An embedded slice of a document — the unit retrieval searches over."""

import uuid
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.document import Document
    from app.db.models.section import Section

# Fixed by the column type, so it cannot follow `settings.embedding_dimensions`:
# changing it means a migration, not a config change.
EMBEDDING_DIMENSIONS = 1536


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sections.id", ondelete="CASCADE")
    )
    content: Mapped[str] = mapped_column(Text)
    page_start: Mapped[int]
    page_end: Mapped[int]
    token_count: Mapped[int]
    order_index: Mapped[int]
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))

    document: Mapped["Document"] = relationship(back_populates="chunks")
    section: Mapped["Section | None"] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("document_id", "order_index"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
