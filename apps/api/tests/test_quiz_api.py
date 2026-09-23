"""Quiz persistence + HTTP endpoints against the docker-compose Postgres."""

from datetime import datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.usecases.documents.regenerate_quiz import RegenerateQuiz
from app.application.usecases.documents.request_quiz import RequestQuiz
from app.domain.entities import Document
from app.domain.values.quiz import QuizStatus
from app.domain.values.status import DocumentStatus
from app.infrastructure.db.repositories import SqlDocumentRepository, SqlQuizRepository
from app.infrastructure.db.session import AsyncSessionLocal
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWorkFactory
from app.interfaces.http.composition import get_regenerate_quiz, get_request_quiz
from fakes import FakeQueue, FixedClock, make_document, make_quiz, make_quiz_questions

pytestmark = pytest.mark.integration

NOW_CLOCK = FixedClock(datetime(2026, 9, 23, 12, 0, 0))


async def insert(session: AsyncSession, **overrides: object) -> Document:
    doc = make_document(content_hash=uuid4().hex, **overrides)
    repo = SqlDocumentRepository(session)
    await repo.add(doc)
    await session.commit()
    return doc


@pytest.fixture
def queue(app: FastAPI) -> FakeQueue:
    """Keep the real Celery broker (and the running worker) out of the test."""
    queue = FakeQueue()
    app.dependency_overrides[get_request_quiz] = lambda: RequestQuiz(
        SqlAlchemyUnitOfWorkFactory(AsyncSessionLocal), queue, NOW_CLOCK
    )
    app.dependency_overrides[get_regenerate_quiz] = lambda: RegenerateQuiz(
        SqlAlchemyUnitOfWorkFactory(AsyncSessionLocal), queue
    )
    return queue


async def test_repository_round_trips_a_ready_quiz(app_session: AsyncSession) -> None:
    doc = await insert(app_session)
    quiz = make_quiz(
        document_id=doc.id, status=QuizStatus.READY, questions=make_quiz_questions()
    )
    repo = SqlQuizRepository(app_session)
    await repo.save(quiz)
    await app_session.commit()
    app_session.expunge_all()

    loaded = await SqlQuizRepository(app_session).get_for_document(doc.id)

    assert loaded is not None
    assert loaded.status.value == quiz.status.value
    assert len(loaded.questions) == 10
    assert loaded.questions[0].question == "Question 0?"
    assert loaded.questions[0].correct_option == "A"


async def test_save_upserts_the_single_row_per_document(app_session: AsyncSession) -> None:
    doc = await insert(app_session)
    repo = SqlQuizRepository(app_session)
    quiz = make_quiz(document_id=doc.id)
    await repo.save(quiz)
    await app_session.commit()

    quiz.apply_questions(make_quiz_questions())
    await repo.save(quiz)
    await app_session.commit()
    app_session.expunge_all()

    loaded = await SqlQuizRepository(app_session).get_for_document(doc.id)
    assert loaded is not None
    assert len(loaded.questions) == 10


class TestRequestQuizEndpoint:
    async def test_first_request_enqueues_and_returns_202(
        self, client: AsyncClient, app_session: AsyncSession, queue: FakeQueue
    ) -> None:
        doc = await insert(app_session)

        response = await client.post(f"/documents/{doc.id}/quiz")

        assert response.status_code == 202
        assert response.json()["status"] == "pending"
        assert queue.quiz_requests == [doc.id]

    async def test_second_request_while_pending_is_a_cache_hit_200(
        self, client: AsyncClient, app_session: AsyncSession, queue: FakeQueue
    ) -> None:
        doc = await insert(app_session)

        await client.post(f"/documents/{doc.id}/quiz")
        second = await client.post(f"/documents/{doc.id}/quiz")

        assert second.status_code == 200
        assert len(queue.quiz_requests) == 1

    async def test_ready_quiz_is_a_cache_hit_200(
        self, client: AsyncClient, app_session: AsyncSession, queue: FakeQueue
    ) -> None:
        doc = await insert(app_session)
        quiz = make_quiz(
            document_id=doc.id, status=QuizStatus.READY, questions=make_quiz_questions()
        )
        await SqlQuizRepository(app_session).save(quiz)
        await app_session.commit()

        response = await client.post(f"/documents/{doc.id}/quiz")

        assert response.status_code == 200
        assert response.json()["status"] == "ready"
        assert len(response.json()["questions"]) == 10
        assert queue.quiz_requests == []

    async def test_unknown_document_is_404(self, client: AsyncClient, queue: FakeQueue) -> None:
        response = await client.post(f"/documents/{uuid4()}/quiz")

        assert response.status_code == 404

    async def test_document_not_ready_is_409(
        self, client: AsyncClient, app_session: AsyncSession, queue: FakeQueue
    ) -> None:
        doc = await insert(app_session, status=DocumentStatus.PARSING)

        response = await client.post(f"/documents/{doc.id}/quiz")

        assert response.status_code == 409
        assert queue.quiz_requests == []


class TestRegenerateQuizEndpoint:
    async def test_accepts_and_resets_to_pending(
        self, client: AsyncClient, app_session: AsyncSession, queue: FakeQueue
    ) -> None:
        doc = await insert(app_session)
        quiz = make_quiz(
            document_id=doc.id, status=QuizStatus.READY, questions=make_quiz_questions()
        )
        await SqlQuizRepository(app_session).save(quiz)
        await app_session.commit()

        response = await client.post(f"/documents/{doc.id}/quiz/regenerate")

        assert response.status_code == 202
        assert response.json()["status"] == "pending"
        assert response.json()["questions"] == []
        assert queue.quiz_requests == [doc.id]

    async def test_unknown_document_is_404(self, client: AsyncClient, queue: FakeQueue) -> None:
        response = await client.post(f"/documents/{uuid4()}/quiz/regenerate")

        assert response.status_code == 404

    async def test_document_not_ready_is_409(
        self, client: AsyncClient, app_session: AsyncSession, queue: FakeQueue
    ) -> None:
        doc = await insert(app_session, status=DocumentStatus.EMBEDDING)

        response = await client.post(f"/documents/{doc.id}/quiz/regenerate")

        assert response.status_code == 409
        assert queue.quiz_requests == []


class TestGetQuizEndpoint:
    async def test_returns_the_quiz(self, client: AsyncClient, app_session: AsyncSession) -> None:
        doc = await insert(app_session)
        quiz = make_quiz(
            document_id=doc.id, status=QuizStatus.READY, questions=make_quiz_questions()
        )
        await SqlQuizRepository(app_session).save(quiz)
        await app_session.commit()

        response = await client.get(f"/documents/{doc.id}/quiz")

        assert response.status_code == 200
        assert response.json()["status"] == "ready"
        assert len(response.json()["questions"]) == 10

    async def test_no_quiz_yet_is_404(self, client: AsyncClient, app_session: AsyncSession) -> None:
        doc = await insert(app_session)

        response = await client.get(f"/documents/{doc.id}/quiz")

        assert response.status_code == 404

    async def test_unknown_document_is_404(self, client: AsyncClient) -> None:
        response = await client.get(f"/documents/{uuid4()}/quiz")

        assert response.status_code == 404
