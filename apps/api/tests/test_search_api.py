"""Search API endpoint tests."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document, DocumentStatus, Section


@pytest.mark.asyncio
async def test_search_404_unknown_document(client) -> None:
    """Search on unknown document returns 404."""
    doc_id = uuid.uuid4()
    response = await client.post(f"/documents/{doc_id}/search", json={"query": "test"})

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_search_409_on_pending_document(client, sync_session) -> None:
    """Search on PENDING document returns 409."""
    doc = Document(
        id=uuid.uuid4(),
        filename="test.pdf",
        title="Test",
        file_path="/tmp/test.pdf",
        status=DocumentStatus.PENDING,
        content_hash="0" * 64,
    )
    sync_session.add(doc)
    sync_session.commit()

    response = await client.post(f"/documents/{doc.id}/search", json={"query": "test"})

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_search_200_ready_document_empty_result(client, sync_session) -> None:
    """Search on READY document with no chunks returns 200 with empty results."""
    doc = Document(
        id=uuid.uuid4(),
        filename="test.pdf",
        title="Test",
        file_path="/tmp/test.pdf",
        status=DocumentStatus.READY,
        page_count=1,
        content_hash="0" * 64,
    )
    sync_session.add(doc)
    sync_session.commit()

    response = await client.post(f"/documents/{doc.id}/search", json={"query": "test"})

    assert response.status_code == 200
    data = response.json()
    assert data["results"] == []
    assert data["grounded"] is False
    assert data["reason"] == "no_chunks"


@pytest.mark.asyncio
async def test_search_reranker_degrade_applies_distance_filter(
    app_session: AsyncSession, settings
) -> None:
    """When re-ranker fails, distance filter applies and filters far chunks."""
    from app.retrieval.pipeline import search

    doc = Document(
        id=uuid.uuid4(),
        filename="test.pdf",
        title="Test",
        file_path="/tmp/test.pdf",
        status=DocumentStatus.READY,
        page_count=1,
        content_hash=uuid.uuid4().hex,
    )
    app_session.add(doc)
    await app_session.flush()

    section = Section(
        id=uuid.uuid4(),
        document_id=doc.id,
        title="Test",
        order_index=0,
        start_page=1,
        end_page=1,
    )
    app_session.add(section)
    await app_session.flush()

    chunk = Chunk(
        id=uuid.uuid4(),
        document_id=doc.id,
        section_id=section.id,
        content="Test content",
        page_start=1,
        page_end=1,
        token_count=10,
        order_index=0,
        embedding=[0.0] * 768,
    )
    app_session.add(chunk)
    await app_session.commit()

    class FailingReranker:
        def score(self, query, candidates):
            raise Exception("Reranker failed")

    outcome = await search(
        app_session,
        doc.id,
        "test query",
        settings=settings,
        reranker=FailingReranker(),
    )

    assert outcome.grounded is False
    assert outcome.reason == "rerank_degraded_no_match"
