"""Use case: fetch a document's quiz (for client polling)."""

from uuid import UUID

from app.domain.entities import Quiz
from app.domain.ports.unit_of_work import UnitOfWorkFactory


class GetQuiz:
    """Use case: fetch a document's quiz, if one exists."""

    def __init__(self, uow_factory: UnitOfWorkFactory):
        self.uow_factory = uow_factory

    async def execute(self, document_id: UUID) -> Quiz | None:
        """Return the quiz for a document, or None if none has been requested yet."""
        async with self.uow_factory() as uow:
            return await uow.quizzes.get_for_document(document_id)
