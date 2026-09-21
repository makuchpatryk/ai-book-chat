"""Overview persistence + HTTP endpoints against the docker-compose Postgres."""

from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.usecases.documents.request_overview import RequestOverview
from app.domain.entities import Document
from app.domain.values.overview import OverviewStatus
from app.domain.values.status import DocumentStatus
from app.infrastructure.clock import SystemClock
from app.infrastructure.db.repositories import SqlDocumentRepository
from app.infrastructure.db.session import AsyncSessionLocal, engine
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWorkFactory
from app.interfaces.http.composition import get_request_overview
from fakes import FakeQueue, make_document, make_overview

pytestmark = pytest.mark.integration


async def insert(session: AsyncSession, **overrides: object) -> Document:
    doc = make_document(content_hash=uuid4().hex, **overrides)
    repo = SqlDocumentRepository(session)
    await repo.add(doc)
    await session.commit()
    return doc


async def test_repository_round_trips_every_overview_field(app_session: AsyncSession) -> None:
    doc = await insert(app_session, author="Jane")
    doc.apply_overview(make_overview())
    repo = SqlDocumentRepository(app_session)
    await repo.save(doc)
    await repo.set_cover(doc.id, b"\xff\xd8data", "image/jpeg")
    await app_session.commit()
    app_session.expunge_all()

    loaded = await SqlDocumentRepository(app_session).get(doc.id)

    assert loaded is not None
    assert loaded.author == "Jane"
    assert loaded.summary == "Short summary."
    assert loaded.language == "en"
    assert loaded.doc_type == "Book"
    assert loaded.topics == ["a", "b", "c"]
    assert loaded.description_sections == [{"heading": f"H{i}", "body": f"B{i}"} for i in range(3)]
    assert loaded.overview_status == OverviewStatus.READY
    assert loaded.cover_mime == "image/jpeg"
    assert await repo.get_cover(doc.id) == (b"\xff\xd8data", "image/jpeg")


async def test_saving_a_document_does_not_wipe_its_cover(app_session: AsyncSession) -> None:
    doc = await insert(app_session)
    repo = SqlDocumentRepository(app_session)
    await repo.set_cover(doc.id, b"bytes", "image/jpeg")
    doc.cover_mime = "image/jpeg"
    doc.mark_overview_failed()
    await repo.save(doc)
    await app_session.commit()

    assert await repo.get_cover(doc.id) == (b"bytes", "image/jpeg")


async def test_list_query_does_not_select_cover_bytes(app_session: AsyncSession) -> None:
    doc = await insert(app_session)
    await SqlDocumentRepository(app_session).set_cover(doc.id, b"x" * 1000, "image/jpeg")
    await app_session.commit()
    app_session.expunge_all()
    statements: list[str] = []

    def record(conn, cursor, statement, *args):  # type: ignore[no-untyped-def]  # noqa: ANN001, ANN202
        statements.append(statement)

    sa.event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        await SqlDocumentRepository(app_session).list_newest_first()
    finally:
        sa.event.remove(engine.sync_engine, "before_cursor_execute", record)

    selects = [s for s in statements if "FROM documents" in s]
    assert selects
    assert not any("cover_image" in s for s in selects)


async def test_get_document_returns_description_sections(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    doc = await insert(app_session)
    doc.apply_overview(make_overview())
    await SqlDocumentRepository(app_session).save(doc)
    await app_session.commit()

    response = await client.get(f"/documents/{doc.id}")

    body = response.json()
    assert response.status_code == 200
    assert body["overview_status"] == "ready"
    assert body["summary"] == "Short summary."
    assert body["topics"] == ["a", "b", "c"]
    assert [s["heading"] for s in body["description_sections"]] == ["H0", "H1", "H2"]
    assert body["has_cover"] is False


async def test_list_exposes_overview_fields(client: AsyncClient, app_session: AsyncSession) -> None:
    doc = await insert(app_session, cover_mime="image/jpeg")

    response = await client.get("/documents")

    row = next(d for d in response.json() if d["id"] == str(doc.id))
    assert row["has_cover"] is True
    assert row["overview_status"] is None
    assert "description_sections" not in row


async def test_cover_endpoint(client: AsyncClient, app_session: AsyncSession) -> None:
    doc = await insert(app_session, cover_mime="image/jpeg")
    await SqlDocumentRepository(app_session).set_cover(doc.id, b"\xff\xd8jpeg", "image/jpeg")
    await app_session.commit()

    response = await client.get(f"/documents/{doc.id}/cover")

    assert response.status_code == 200
    assert response.content == b"\xff\xd8jpeg"
    assert response.headers["content-type"] == "image/jpeg"
    assert "max-age" in response.headers["cache-control"]


async def test_cover_endpoint_404s(client: AsyncClient, app_session: AsyncSession) -> None:
    doc = await insert(app_session)

    assert (await client.get(f"/documents/{doc.id}/cover")).status_code == 404
    assert (await client.get(f"/documents/{uuid4()}/cover")).status_code == 404


class TestRegenerate:
    @pytest.fixture
    def queue(self, app: FastAPI) -> FakeQueue:
        """Keep the real Celery broker (and the running worker) out of the test."""
        queue = FakeQueue()
        app.dependency_overrides[get_request_overview] = lambda: RequestOverview(
            SqlAlchemyUnitOfWorkFactory(AsyncSessionLocal), queue, SystemClock()
        )
        return queue

    async def test_accepts_and_marks_pending(
        self, client: AsyncClient, app_session: AsyncSession, queue: FakeQueue
    ) -> None:
        doc = await insert(app_session)

        response = await client.post(f"/documents/{doc.id}/overview/regenerate")

        assert response.status_code == 202
        assert response.json()["overview_status"] == "pending"
        assert queue.overview_requests == [doc.id]

    async def test_second_request_conflicts_while_pending(
        self, client: AsyncClient, app_session: AsyncSession, queue: FakeQueue
    ) -> None:
        doc = await insert(app_session)

        await client.post(f"/documents/{doc.id}/overview/regenerate")
        second = await client.post(f"/documents/{doc.id}/overview/regenerate")

        assert second.status_code == 409
        assert len(queue.overview_requests) == 1

    async def test_unknown_document_is_404(self, client: AsyncClient, queue: FakeQueue) -> None:
        response = await client.post(f"/documents/{uuid4()}/overview/regenerate")

        assert response.status_code == 404

    async def test_document_not_ready_is_409(
        self, client: AsyncClient, app_session: AsyncSession, queue: FakeQueue
    ) -> None:
        doc = await insert(app_session, status=DocumentStatus.PARSING)

        response = await client.post(f"/documents/{doc.id}/overview/regenerate")

        assert response.status_code == 409
        assert queue.overview_requests == []
