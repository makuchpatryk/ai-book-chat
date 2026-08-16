"""Orchestrate the retrieval pipeline: embed, search, re-rank, guard."""

import logging
from dataclasses import dataclass
from uuid import UUID

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.ingestion.embeddings import Embedder, build_embedder
from app.retrieval.rerank import RerankCandidate, Reranker, build_reranker
from app.retrieval.search import Candidate, vector_search

logger = logging.getLogger(__name__)


@dataclass
class SearchOutcome:
    """Result of the retrieval pipeline."""

    results: list[tuple[Candidate, int | None]]
    grounded: bool
    reranked: bool
    reason: str | None
    candidate_count: int


async def search(
    session: AsyncSession,
    document_id: UUID,
    query: str,
    settings: Settings | None = None,
    embedder: Embedder | None = None,
    reranker: Reranker | None = None,
) -> SearchOutcome:
    """Run the full retrieval pipeline.

    Steps:
    1. Embed query
    2. Vector search
    3. Re-rank (with degrade on failure)
    4. Guard and cut
    """
    settings = settings or get_settings()
    embedder = embedder or build_embedder(settings)
    reranker = reranker or build_reranker(settings)

    # 1. Embed query
    query_vectors = await anyio.to_thread.run_sync(embedder.embed, [query])
    query_vector = query_vectors[0]

    # 2. Vector search
    candidates = await vector_search(session, document_id, query_vector, settings.retrieval_top_k)

    if not candidates:
        return SearchOutcome(
            results=[],
            grounded=False,
            reranked=False,
            reason="no_chunks",
            candidate_count=0,
        )

    # 3. Re-rank (or degrade)
    rerank_candidates = [
        RerankCandidate(index=i, content=c.chunk.content) for i, c in enumerate(candidates)
    ]
    scores: list[int] | None = None
    reranked = True
    try:
        scores = await anyio.to_thread.run_sync(reranker.score, query, rerank_candidates)
    except Exception as exc:
        logger.warning(
            "rerank degraded",
            extra={"document_id": str(document_id), "exception_type": type(exc).__name__},
        )
        reranked = False

    # 4. Guard and cut
    results_with_scores: list[tuple[Candidate, int | None]] = []

    if scores:
        for i, candidate in enumerate(candidates):
            score = scores[i]
            results_with_scores.append((candidate, score))

        # Filter by min_score threshold
        min_score = settings.rerank_min_score
        results_with_scores = [
            (c, s) for c, s in results_with_scores
            if s is not None and s >= min_score
        ]
        # Sort by score descending
        results_with_scores.sort(key=lambda x: x[1] or 0, reverse=True)

        if not results_with_scores:
            all_scores = [(c, scores[i]) for i, c in enumerate(candidates)]
            top_score = max((s for _, s in all_scores if s), default=0)
            logger.info(
                "grounded false guard fired",
                extra={"document_id": str(document_id), "top_score": top_score},
            )
            return SearchOutcome(
                results=[],
                grounded=False,
                reranked=True,
                reason="no_relevant_chunks",
                candidate_count=len(candidates),
            )
    else:
        # Re-ranker degraded: filter by distance instead
        results_with_scores = [
            (c, None) for c in candidates
            if c.distance <= settings.retrieval_max_distance
        ]
        if not results_with_scores:
            logger.info(
                "rerank degrade guard fired",
                extra={"document_id": str(document_id)},
            )
            return SearchOutcome(
                results=[],
                grounded=False,
                reranked=False,
                reason="rerank_degraded_no_match",
                candidate_count=len(candidates),
            )

    # Top-N cut
    results_with_scores = results_with_scores[: settings.rerank_top_n]

    return SearchOutcome(
        results=results_with_scores,
        grounded=True,
        reranked=reranked,
        reason=None,
        candidate_count=len(candidates),
    )
