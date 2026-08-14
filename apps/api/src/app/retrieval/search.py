"""Vector search over embedded chunks."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.models import Chunk, Section


@dataclass
class Candidate:
    """A chunk and its metadata, ranked by distance."""

    chunk: Chunk
    section_title: str | None
    distance: float


async def vector_search(
    session: AsyncSession, document_id: UUID, query_vector: list[float], limit: int
) -> list[Candidate]:
    """Find nearest chunks in one document by cosine distance.

    Sets LOCAL hnsw.ef_search to 2×k (min 64) for better recall.
    """
    ef_search = max(64, limit * 2)
    await session.execute(text(f"SET LOCAL hnsw.ef_search = {ef_search}"))

    stmt = (
        select(Chunk, Section.title, Chunk.embedding.cosine_distance(query_vector))
        .outerjoin(Section)
        .where(Chunk.document_id == document_id)
        .order_by(Chunk.embedding.cosine_distance(query_vector))
        .limit(limit)
        .options(joinedload(Chunk.section))
    )
    rows = await session.execute(stmt)
    return [
        Candidate(chunk=chunk, section_title=section_title, distance=distance)
        for chunk, section_title, distance in rows
    ]
