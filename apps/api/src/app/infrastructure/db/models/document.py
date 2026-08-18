"""An uploaded PDF and its processing state."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.chunk import Chunk
    from app.infrastructure.db.models.section import Section


class DocumentStatus(enum.StrEnum):
    """Lifecycle of a document, driven by the ingestion pipeline."""

    PENDING = "PENDING"
    PARSING = "PARSING"
    EMBEDDING = "EMBEDDING"
    READY = "READY"
    FAILED = "FAILED"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(512))
    title: Mapped[str] = mapped_column(String(512))
    # NULL until the PDF has been parsed.
    page_count: Mapped[int | None]
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status", native_enum=True),
        default=DocumentStatus.PENDING,
        server_default=DocumentStatus.PENDING.value,
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    file_path: Mapped[str] = mapped_column(String(1024))
    # SHA-256 of the raw upload bytes — the dedupe key, unique across all statuses.
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Which section-detection strategy won: outline | headings | flat.
    chunking_strategy: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    sections: Mapped[list["Section"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Section.order_index",
    )
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Chunk.order_index",
    )

    __table_args__ = (Index("ix_documents_created_at", created_at.desc()),)
