"""Use case: force a fresh quiz for a document, replacing any cached one."""

import logging
from uuid import UUID, uuid4

from app.domain.entities import Quiz
from app.domain.errors import DocumentNotFound, DocumentNotReady
from app.domain.ports.storage import IngestionQueue
from app.domain.ports.unit_of_work import UnitOfWorkFactory
from app.domain.values.quiz import QuizStatus
from app.domain.values.status import DocumentStatus

logger = logging.getLogger(__name__)


class RegenerateQuiz:
    """Use case: unconditionally reset and re-enqueue a document's quiz."""

    def __init__(self, uow_factory: UnitOfWorkFactory, queue: IngestionQueue):
        self.uow_factory = uow_factory
        self.queue = queue

    async def execute(self, document_id: UUID) -> Quiz:
        """Reset the quiz to PENDING and enqueue a fresh generation. Raises if not READY."""
        async with self.uow_factory() as uow:
            document = await uow.documents.get(document_id)
            if document is None:
                raise DocumentNotFound()
            if document.status != DocumentStatus.READY:
                raise DocumentNotReady(activity="quiz generation")

            quiz = await uow.quizzes.get_for_document(document_id)
            if quiz is None:
                quiz = Quiz(id=uuid4(), document_id=document_id, status=QuizStatus.PENDING)
            else:
                quiz.mark_pending()

            await uow.quizzes.save(quiz)
            await uow.commit()

        try:
            await self.queue.enqueue_quiz(document_id)
        except Exception as e:
            logger.error(f"failed to enqueue quiz for {document_id}: {e}")

        return quiz
