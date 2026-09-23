"""A generated multiple-choice quiz for a document."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.document import Document


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # One quiz per document — unique index, cascade delete with the document.
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), unique=True, index=True
    )
    # Plain string, not a native enum — mirrors Document.overview_status (values are the
    # lowercase QuizStatus.value, e.g. "pending"), since a native Enum column stores the
    # Python enum member's *name*, not its .value.
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    # List of {position, question, option_a..d, correct_option} dicts.
    questions: Mapped[list[dict[str, object]] | None] = mapped_column(sqlalchemy.JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    document: Mapped["Document"] = relationship()
