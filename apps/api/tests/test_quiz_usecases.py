"""Unit tests for the quiz use cases (fakes, no infrastructure)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.application.usecases.documents.generate_quiz import GenerateQuiz
from app.application.usecases.documents.regenerate_quiz import RegenerateQuiz
from app.application.usecases.documents.request_quiz import RequestQuiz
from app.domain.errors import DocumentNotFound, DocumentNotReady
from app.domain.values.quiz import QuizStatus
from app.domain.values.status import DocumentStatus
from fakes import (
    FakeQueue,
    FakeUowFactory,
    FixedClock,
    ScriptedQuizGenerator,
    make_chunk,
    make_document,
    make_quiz,
    make_quiz_questions,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 23, 12, 0, 0)


class TestRequestQuiz:
    def build(
        self, *docs: object, quizzes: list[object] | None = None, queue: FakeQueue | None = None
    ) -> tuple[RequestQuiz, FakeUowFactory, FakeQueue]:
        factory = FakeUowFactory(list(docs), quizzes=quizzes)  # type: ignore[arg-type]
        queue = queue or FakeQueue()
        uc = RequestQuiz(factory, queue, FixedClock(NOW))  # type: ignore[arg-type]
        return uc, factory, queue

    async def test_unknown_document(self) -> None:
        uc, _, _ = self.build()

        with pytest.raises(DocumentNotFound):
            await uc.execute(make_document().id)

    async def test_document_must_be_ready(self) -> None:
        doc = make_document(status=DocumentStatus.EMBEDDING)
        uc, _, queue = self.build(doc)

        with pytest.raises(DocumentNotReady):
            await uc.execute(doc.id)
        assert queue.quiz_requests == []

    async def test_no_existing_quiz_creates_and_enqueues(self) -> None:
        doc = make_document()
        uc, factory, queue = self.build(doc)

        quiz, enqueued = await uc.execute(doc.id)

        assert enqueued is True
        assert quiz.status == QuizStatus.PENDING
        assert queue.quiz_requests == [doc.id]
        assert factory.uow.commits == 1

    async def test_ready_quiz_is_cache_hit_no_enqueue(self) -> None:
        doc = make_document()
        quiz = make_quiz(
            document_id=doc.id, status=QuizStatus.READY, questions=make_quiz_questions()
        )
        uc, _, queue = self.build(doc, quizzes=[quiz])

        result, enqueued = await uc.execute(doc.id)

        assert enqueued is False
        assert result.status == QuizStatus.READY
        assert queue.quiz_requests == []

    async def test_fresh_pending_is_not_re_enqueued(self) -> None:
        doc = make_document()
        quiz = make_quiz(
            document_id=doc.id, status=QuizStatus.PENDING, updated_at=NOW - timedelta(minutes=1)
        )
        uc, _, queue = self.build(doc, quizzes=[quiz])

        result, enqueued = await uc.execute(doc.id)

        assert enqueued is False
        assert result.status == QuizStatus.PENDING
        assert queue.quiz_requests == []

    async def test_stale_pending_is_re_enqueued(self) -> None:
        doc = make_document()
        quiz = make_quiz(
            document_id=doc.id, status=QuizStatus.PENDING, updated_at=NOW - timedelta(minutes=30)
        )
        uc, _, queue = self.build(doc, quizzes=[quiz])

        result, enqueued = await uc.execute(doc.id)

        assert enqueued is True
        assert result.status == QuizStatus.PENDING
        assert queue.quiz_requests == [doc.id]

    async def test_timezone_aware_updated_at_from_the_database(self) -> None:
        doc = make_document()
        quiz = make_quiz(
            document_id=doc.id,
            status=QuizStatus.PENDING,
            updated_at=(NOW - timedelta(minutes=1)).replace(tzinfo=UTC),
        )
        uc, _, queue = self.build(doc, quizzes=[quiz])

        _, enqueued = await uc.execute(doc.id)

        assert enqueued is False
        assert queue.quiz_requests == []

    async def test_failed_quiz_is_re_enqueued(self) -> None:
        doc = make_document()
        quiz = make_quiz(document_id=doc.id, status=QuizStatus.FAILED, error_message="boom")
        uc, _, queue = self.build(doc, quizzes=[quiz])

        result, enqueued = await uc.execute(doc.id)

        assert enqueued is True
        assert result.status == QuizStatus.PENDING
        assert queue.quiz_requests == [doc.id]

    async def test_enqueue_failure_is_swallowed(self) -> None:
        doc = make_document()
        uc, factory, _ = self.build(doc, queue=FakeQueue(fail=True))

        quiz, enqueued = await uc.execute(doc.id)

        assert enqueued is True
        assert quiz.status == QuizStatus.PENDING
        assert factory.uow.commits == 1


class TestRegenerateQuiz:
    def build(
        self, *docs: object, quizzes: list[object] | None = None, queue: FakeQueue | None = None
    ) -> tuple[RegenerateQuiz, FakeUowFactory, FakeQueue]:
        factory = FakeUowFactory(list(docs), quizzes=quizzes)  # type: ignore[arg-type]
        queue = queue or FakeQueue()
        uc = RegenerateQuiz(factory, queue)  # type: ignore[arg-type]
        return uc, factory, queue

    async def test_unknown_document(self) -> None:
        uc, _, _ = self.build()

        with pytest.raises(DocumentNotFound):
            await uc.execute(make_document().id)

    async def test_document_must_be_ready(self) -> None:
        doc = make_document(status=DocumentStatus.PARSING)
        uc, _, queue = self.build(doc)

        with pytest.raises(DocumentNotReady):
            await uc.execute(doc.id)
        assert queue.quiz_requests == []

    async def test_no_existing_quiz_creates_pending_and_enqueues(self) -> None:
        doc = make_document()
        uc, factory, queue = self.build(doc)

        quiz = await uc.execute(doc.id)

        assert quiz.status == QuizStatus.PENDING
        assert queue.quiz_requests == [doc.id]
        assert factory.uow.commits == 1

    async def test_ready_quiz_is_always_reset_and_re_enqueued(self) -> None:
        doc = make_document()
        quiz = make_quiz(
            document_id=doc.id, status=QuizStatus.READY, questions=make_quiz_questions()
        )
        uc, _, queue = self.build(doc, quizzes=[quiz])

        result = await uc.execute(doc.id)

        assert result.status == QuizStatus.PENDING
        assert result.questions == []
        assert queue.quiz_requests == [doc.id]

    async def test_fresh_pending_quiz_is_still_re_enqueued(self) -> None:
        doc = make_document()
        quiz = make_quiz(document_id=doc.id, status=QuizStatus.PENDING)
        uc, _, queue = self.build(doc, quizzes=[quiz])

        await uc.execute(doc.id)

        assert queue.quiz_requests == [doc.id]


class TestGenerateQuiz:
    def build(
        self,
        factory: FakeUowFactory,
        generator: ScriptedQuizGenerator,
        max_tokens: int = 1000,
    ) -> GenerateQuiz:
        return GenerateQuiz(factory, generator, max_tokens)  # type: ignore[arg-type]

    async def test_success_applies_questions_and_commits(self) -> None:
        doc = make_document()
        quiz = make_quiz(document_id=doc.id, status=QuizStatus.PENDING)
        factory = FakeUowFactory([doc], [make_chunk(doc.id, i) for i in range(3)], quizzes=[quiz])
        generator = ScriptedQuizGenerator(make_quiz_questions())

        ok = await self.build(factory, generator).execute(doc.id)

        assert ok is True
        assert quiz.status == QuizStatus.READY
        assert len(quiz.questions) == 10
        assert factory.uow.commits == 1

    async def test_invalid_output_is_retried_once(self) -> None:
        doc = make_document()
        quiz = make_quiz(document_id=doc.id, status=QuizStatus.PENDING)
        factory = FakeUowFactory([doc], [make_chunk(doc.id, 0)], quizzes=[quiz])
        generator = ScriptedQuizGenerator(ValueError("bad json"), make_quiz_questions())

        ok = await self.build(factory, generator).execute(doc.id)

        assert ok is True
        assert len(generator.calls) == 2

    async def test_invalid_output_twice_marks_failed(self) -> None:
        doc = make_document()
        quiz = make_quiz(document_id=doc.id, status=QuizStatus.PENDING)
        factory = FakeUowFactory([doc], [make_chunk(doc.id, 0)], quizzes=[quiz])
        generator = ScriptedQuizGenerator(ValueError("bad json"))

        ok = await self.build(factory, generator).execute(doc.id)

        assert ok is False
        assert len(generator.calls) == 2
        assert quiz.status == QuizStatus.FAILED

    async def test_unexpected_error_marks_failed_without_retry(self) -> None:
        doc = make_document()
        quiz = make_quiz(document_id=doc.id, status=QuizStatus.PENDING)
        factory = FakeUowFactory([doc], [make_chunk(doc.id, 0)], quizzes=[quiz])
        generator = ScriptedQuizGenerator(RuntimeError("rate limited"))

        ok = await self.build(factory, generator).execute(doc.id)

        assert ok is False
        assert len(generator.calls) == 1
        assert quiz.status == QuizStatus.FAILED

    async def test_wrong_question_count_marks_failed_without_raising(self) -> None:
        doc = make_document()
        quiz = make_quiz(document_id=doc.id, status=QuizStatus.PENDING)
        factory = FakeUowFactory([doc], [make_chunk(doc.id, 0)], quizzes=[quiz])
        generator = ScriptedQuizGenerator(make_quiz_questions(5))

        ok = await self.build(factory, generator).execute(doc.id)

        assert ok is False
        assert quiz.status == QuizStatus.FAILED

    async def test_unknown_document_is_noop(self) -> None:
        factory = FakeUowFactory([])
        generator = ScriptedQuizGenerator(make_quiz_questions())

        assert await self.build(factory, generator).execute(make_document().id) is False
        assert generator.calls == []

    @pytest.mark.parametrize("status", [DocumentStatus.PENDING, DocumentStatus.FAILED])
    async def test_not_ready_document_is_noop(self, status: DocumentStatus) -> None:
        doc = make_document(status=status)
        factory = FakeUowFactory([doc], [make_chunk(doc.id, 0)])
        generator = ScriptedQuizGenerator(make_quiz_questions())

        assert await self.build(factory, generator).execute(doc.id) is False
        assert generator.calls == []

    async def test_no_quiz_row_is_noop(self) -> None:
        doc = make_document()
        factory = FakeUowFactory([doc], [make_chunk(doc.id, 0)])
        generator = ScriptedQuizGenerator(make_quiz_questions())

        assert await self.build(factory, generator).execute(doc.id) is False
        assert generator.calls == []

    async def test_no_chunks_marks_failed(self) -> None:
        doc = make_document()
        quiz = make_quiz(document_id=doc.id, status=QuizStatus.PENDING)
        factory = FakeUowFactory([doc], quizzes=[quiz])
        generator = ScriptedQuizGenerator(make_quiz_questions())

        assert await self.build(factory, generator).execute(doc.id) is False
        assert quiz.status == QuizStatus.FAILED
        assert generator.calls == []
