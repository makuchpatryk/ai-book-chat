"""Use case: generate a document's quiz from sampled chunks."""

import logging
from uuid import UUID

from app.application.usecases.documents.generate_overview import sample_chunks
from app.domain.ports.llm import QuizGenerator
from app.domain.ports.unit_of_work import UnitOfWorkFactory
from app.domain.values.quiz import QuizQuestion, QuizStatus
from app.domain.values.status import DocumentStatus

logger = logging.getLogger(__name__)

QUIZ_ATTEMPTS = 2  # one retry when the model returns unusable JSON


class GenerateQuiz:
    """Use case: generate a document's quiz from sampled chunk content. Never raises."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        generator: QuizGenerator,
        max_input_tokens: int,
    ):
        self.uow_factory = uow_factory
        self.generator = generator
        self.max_input_tokens = max_input_tokens

    async def execute(self, document_id: UUID) -> bool:
        """Generate the quiz for a document. Returns True if it was applied."""
        async with self.uow_factory() as uow:
            document = await uow.documents.get(document_id)
            if document is None:
                logger.warning(f"document {document_id} not found")
                return False

            if document.status != DocumentStatus.READY:
                logger.warning(f"document {document_id} not READY: {document.status}")
                return False

            quiz = await uow.quizzes.get_for_document(document_id)
            if quiz is None:
                logger.warning(f"no quiz row for {document_id}")
                return False

            chunks = await uow.chunks.list_for_document(document_id)
            if not chunks:
                logger.warning(f"no chunks for {document_id}")
                quiz.mark_failed("document has no chunks")
                await uow.quizzes.save(quiz)
                await uow.commit()
                return False

            sample = sample_chunks(chunks, self.max_input_tokens)
            questions = await self._generate(document.title, [sample])

            if questions is None:
                quiz.mark_failed("quiz generation failed")
            else:
                try:
                    quiz.apply_questions(questions)
                except ValueError as e:
                    logger.warning(f"generated quiz failed validation: {e}")
                    quiz.mark_failed(str(e))

            await uow.quizzes.save(quiz)
            await uow.commit()
            return quiz.status == QuizStatus.READY

    async def _generate(self, title: str, chunks: list[str]) -> list[QuizQuestion] | None:
        for attempt in range(1, QUIZ_ATTEMPTS + 1):
            try:
                return await self.generator.generate(title, chunks)
            except ValueError as e:
                logger.warning(f"quiz generator returned invalid output (attempt {attempt}): {e}")
            except Exception as e:
                logger.exception(f"quiz generator failed: {e}")
                return None
        return None
