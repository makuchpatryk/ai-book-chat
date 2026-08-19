"""Retrieval context: embed → search → rerank → guard."""

from dataclasses import dataclass
from uuid import UUID

from app.domain.ports.llm import Embedder, Reranker
from app.domain.ports.unit_of_work import UnitOfWork
from app.domain.services.relevance import guard_and_cut
from app.domain.values.policies import RetrievalPolicy
from app.domain.values.retrieval import Citation, RetrievedChunk, ScoredChunk


@dataclass
class RetrievalResult:
    """Result of a retrieval attempt."""

    citations: list[Citation]
    scored_chunks: list[ScoredChunk]  # Full scored chunks with all metadata
    grounded: bool
    reason: str  # "no_chunks", "no_relevant_chunks", "rerank_degraded_no_match", or ""


class RetrieveContext:
    """Orchestrates retrieval: embed → search → rerank → guard."""

    def __init__(
        self,
        uow: UnitOfWork,
        embedder: Embedder,
        reranker: Reranker,
        policy: RetrievalPolicy,
    ):
        self.uow = uow
        self.embedder = embedder
        self.reranker = reranker
        self.policy = policy

    async def retrieve(
        self, document_id: UUID, query: str
    ) -> RetrievalResult:
        """Retrieve and rank chunks for a query. Returns citations and grounded status."""
        # Step 1: Embed the query
        query_vector = await self.embedder.embed([query])
        if not query_vector:
            return RetrievalResult(
                citations=[], scored_chunks=[], grounded=False, reason="no_chunks"
            )

        # Step 2: Search for similar chunks
        chunks = await self.uow.chunks.search_similar(
            document_id, query_vector[0], limit=self.policy.top_k * 2
        )
        if not chunks:
            return RetrievalResult(
                citations=[], scored_chunks=[], grounded=False, reason="no_chunks"
            )

        # Step 3: Rerank (best-effort; degradation is acceptable)
        passages = [chunk.content for chunk in chunks]
        try:
            scores = await self.reranker.score(query, passages)
            scored = [
                (chunk, float(scores[i]))
                for i, chunk in enumerate(chunks)
            ]
        except Exception:
            # Fall back to inverse distance scoring
            scored = [
                (chunk, 1.0 - min(chunk.distance, 1.0))
                for chunk in chunks
            ]

        # Step 4: Guard and cut (pure logic)
        scored_chunks = [
            ScoredChunk(
                chunk=RetrievedChunk(
                    chunk_id=chunk.chunk_id,
                    distance=chunk.distance,
                    content=chunk.content,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    section_title=chunk.section_title,
                ),
                score=int(score * 100) if score else 0,
            )
            for chunk, score in scored
        ]

        outcome = guard_and_cut(scored_chunks, self.policy)
        if not outcome.chunks:
            return RetrievalResult(
                citations=[],
                scored_chunks=[],
                grounded=False,
                reason=outcome.reason or "",
            )

        # Convert scored chunks to citations
        citations = [
            Citation(
                chunk_id=scored.chunk.chunk_id,
                page_start=scored.chunk.page_start,
                page_end=scored.chunk.page_end,
                score=scored.score,
                section_title=scored.chunk.section_title,
                snippet=scored.chunk.content[:240],
            )
            for scored in outcome.chunks
        ]
        return RetrievalResult(
            citations=citations,
            scored_chunks=outcome.chunks,
            grounded=True,
            reason="",
        )
