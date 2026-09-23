"""Quiz entity — a generated multiple-choice quiz for a document."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.domain.values.quiz import QuizQuestion, QuizStatus

QUESTION_COUNT = 10


@dataclass
class Quiz:
    """A 10-question multiple-choice quiz generated from a document's chunks."""

    id: UUID
    document_id: UUID
    status: QuizStatus
    questions: list[QuizQuestion] = field(default_factory=list)
    error_message: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def mark_pending(self) -> None:
        """Mark quiz as pending, ready to (re)generate."""
        self.status = QuizStatus.PENDING
        self.questions = []
        self.error_message = None
        self.updated_at = datetime.utcnow()

    def apply_questions(self, questions: list[QuizQuestion]) -> None:
        """Apply generated questions. Raises ValueError unless exactly 10 well-formed questions."""
        if len(questions) != QUESTION_COUNT:
            raise ValueError(f"expected {QUESTION_COUNT} questions, got {len(questions)}")
        for q in questions:
            if q.correct_option not in ("A", "B", "C", "D"):
                raise ValueError(f"invalid correct_option: {q.correct_option!r}")

        self.questions = questions
        self.status = QuizStatus.READY
        self.error_message = None
        self.updated_at = datetime.utcnow()

    def mark_failed(self, reason: str) -> None:
        """Mark quiz generation as failed with a truncated error message."""
        self.status = QuizStatus.FAILED
        self.error_message = reason[:1000]
        self.updated_at = datetime.utcnow()
