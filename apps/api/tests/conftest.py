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

from app.infrastructure.config.settings import Settings, get_settings
from app.infrastructure.db.models import Document
from app.infrastructure.db.session import AsyncSessionLocal, engine
from app.interfaces.http.app import create_app


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
async def app_session() -> AsyncIterator[AsyncSession]:
    """Async database session for async tests (e.g., vector search).

    Cleans up after itself: documents that appeared while the fixture was active
    are deleted (cascades take sections, chunks and conversations with them).
    Without this a test run leaves rows behind that collide on the next run.
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
