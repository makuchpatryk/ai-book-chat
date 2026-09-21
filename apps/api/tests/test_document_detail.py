"""GET /documents/{id} reports the real chunk count."""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Section
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from fakes import make_chunk, make_document

pytestmark = pytest.mark.integration


async def test_chunk_count_counts_chunks_not_sections(
    app_session: AsyncSession, client: AsyncClient
) -> None:
    uow = SqlAlchemyUnitOfWork(app_session)
    document = make_document(content_hash=uuid4().hex)
    await uow.documents.add(document)
    section = Section(
        id=uuid4(), document_id=document.id, title="Only section", order_index=0,
        start_page=1, end_page=9,
    )
    await uow.sections.add_many([section])
    chunks = [make_chunk(document.id, i) for i in range(3)]
    for chunk in chunks:
        chunk.section_id = section.id
        chunk.embedding = [0.1] * 768
    await uow.chunks.add_many(chunks)
    await uow.commit()

    response = await client.get(f"/documents/{document.id}")

    assert response.status_code == 200
    assert response.json()["chunk_count"] == 3
    assert len(response.json()["sections"]) == 1
