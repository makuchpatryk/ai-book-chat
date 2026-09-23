"""Use case: request quiz generation for a document (get-or-create, cached)."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.domain.entities import Quiz
from app.domain.errors import DocumentNotFound, DocumentNotReady
from app.domain.ports.storage import Clock, IngestionQueue
from app.domain.ports.unit_of_work import UnitOfWorkFactory
from app.domain.values.quiz import QuizStatus
from app.domain.values.status import DocumentStatus

logger = logging.getLogger(__name__)

# If quiz generation is pending and older than this, allow re-request.
PENDING_TIMEOUT = timedelta(minutes=10)


def _as_naive_utc(value: datetime) -> datetime:
    """The DB hands back aware datetimes; the clock hands out naive UTC."""
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


class RequestQuiz:
    """Use case: get-or-create a document's quiz, deduping recent pending requests."""

    def __init__(self, uow_factory: UnitOfWorkFactory, queue: IngestionQueue, clock: Clock):
        self.uow_factory = uow_factory
        self.queue = queue
        self.clock = clock

    async def execute(self, document_id: UUID) -> tuple[Quiz, bool]:
        """Return the cached/in-flight quiz, or enqueue a new generation.

        Returns (quiz, enqueued) — `enqueued` is True only when this call triggered a
        fresh generation (as opposed to a cache hit or an already-pending request).
        Raises DocumentNotFound / DocumentNotReady. Never raises for an existing quiz.
        """
        enqueue = False
        async with self.uow_factory() as uow:
            document = await uow.documents.get(document_id)
            if document is None:
                raise DocumentNotFound()
            if document.status != DocumentStatus.READY:
                raise DocumentNotReady(activity="quiz generation")

            quiz = await uow.quizzes.get_for_document(document_id)
            now = self.clock.now()

            if quiz is None:
                quiz = Quiz(id=uuid4(), document_id=document_id, status=QuizStatus.PENDING)
                enqueue = True
            elif quiz.status == QuizStatus.READY:
                pass
            elif quiz.status == QuizStatus.PENDING:
                fresh = now - _as_naive_utc(quiz.updated_at) < PENDING_TIMEOUT
                if not fresh:
                    quiz.mark_pending()
                    enqueue = True
            else:  # FAILED
                quiz.mark_pending()
                enqueue = True

            await uow.quizzes.save(quiz)
            await uow.commit()

        if enqueue:
            try:
                await self.queue.enqueue_quiz(document_id)
            except Exception as e:
                logger.error(f"failed to enqueue quiz for {document_id}: {e}")

        return quiz, enqueue
