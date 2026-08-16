"""Test fixtures.

Tests run on the host against the docker-compose infra published on localhost,
so they use the `.env` (host-facing) URLs, not the in-network ones.
"""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import Document
from app.db.session import AsyncSessionLocal, engine
from app.db.sync_session import SyncSessionLocal
from app.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Real settings, except uploads land in the test's own directory."""
    return Settings(upload_dir=tmp_path / "uploads")


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    application = create_app()
    application.dependency_overrides[get_settings] = lambda: settings
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
    # Each test gets a fresh event loop, and asyncpg connections are bound to the
    # loop that opened them — a pooled connection would blow up in the next test.
    await engine.dispose()


@pytest.fixture
def sync_session() -> Iterator[Session]:
    """A worker-style session over the dev database.

    Documents created while the fixture is active are deleted afterwards (the
    cascades take sections and chunks with them), so a real ingested book in the
    dev database survives a test run untouched.
    """
    session = SyncSessionLocal()
    try:
        before = set(session.scalars(sa.select(Document.id)))
    except sa.exc.OperationalError:
        session.close()
        pytest.skip("postgres unreachable")

    try:
        yield session
    finally:
        session.rollback()
        for document_id in set(session.scalars(sa.select(Document.id))) - before:
            session.execute(sa.delete(Document).where(Document.id == document_id))
        session.commit()
        session.close()


@pytest.fixture
async def app_session() -> AsyncIterator[AsyncSession]:
    """Async database session for async tests (e.g., vector search).

    Cleans up after itself the same way `sync_session` does: documents that
    appeared while the fixture was active are deleted (cascades take sections,
    chunks and conversations with them). Without this a test run leaves rows
    behind that collide with `documents.content_hash` on the next run, and a
    real ingested book in the dev database would accumulate junk beside it.
    """
    async with AsyncSessionLocal() as session:
        before = set(await session.scalars(sa.select(Document.id)))
        try:
            yield session
        finally:
            await session.rollback()
            after = set(await session.scalars(sa.select(Document.id)))
            for document_id in after - before:
                await session.execute(sa.delete(Document).where(Document.id == document_id))
            await session.commit()

    # Same reason as the `client` fixture: asyncpg connections belong to the loop
    # that opened them, and the next test gets a fresh one.
    await engine.dispose()


@pytest.fixture
def enqueued(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Capture Celery hand-offs instead of putting real work on the queue."""
    document_ids: list[str] = []

    class StubTask:
        @staticmethod
        def delay(document_id: str) -> None:
            document_ids.append(document_id)

    monkeypatch.setattr("app.services.documents.process_document", StubTask)
    return document_ids


@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use FakeGenerator and FakeRewriter in chat routes."""
    from app.chat.generate import FakeGenerator
    from app.chat.rewrite import FakeRewriter

    def fake_build_generator(settings):
        return FakeGenerator()

    def fake_build_rewriter(settings):
        return FakeRewriter()

    monkeypatch.setattr("app.api.routes.conversations.build_generator", fake_build_generator)
    monkeypatch.setattr("app.api.routes.conversations.build_rewriter", fake_build_rewriter)
