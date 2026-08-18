"""Pure relevance guard logic — determine if retrieved chunks meet quality threshold."""

from dataclasses import dataclass

from app.domain.values.policies import RetrievalPolicy
from app.domain.values.retrieval import ScoredChunk


@dataclass
class RetrievalOutcome:
    """Result of retrieval guard and cut."""

    chunks: list[ScoredChunk]
    grounded: bool
    reason: str | None


def guard_and_cut(
    scored_chunks: list[ScoredChunk],
    policy: RetrievalPolicy,
) -> RetrievalOutcome:
    """Apply guard logic: filter by score/distance, sort, cut to top-N.

    Returns ungrounded (empty) if guard fires:
    - no_chunks: no candidates found
    - no_relevant_chunks: all candidates filtered out by score threshold
    - rerank_degraded_no_match: reranker failed and all candidates filtered by distance
    """
    if not scored_chunks:
        return RetrievalOutcome(chunks=[], grounded=False, reason="no_chunks")

    # Separate scored and degraded (distance-based) chunks
    scored = [c for c in scored_chunks if c.score is not None]
    degraded = [c for c in scored_chunks if c.score is None]

    if scored:
        # Filter by min_score threshold
        filtered = [c for c in scored if c.score >= policy.min_score]

        if not filtered:
            return RetrievalOutcome(chunks=[], grounded=False, reason="no_relevant_chunks")

        # Sort by score descending
        filtered.sort(key=lambda c: c.score or 0, reverse=True)

        # Top-N cut
        result = filtered[: policy.top_n]
        return RetrievalOutcome(chunks=result, grounded=True, reason=None)

    else:
        # Reranker degraded: filter by distance instead
        filtered = [c for c in degraded if c.chunk.distance <= policy.max_distance]

        if not filtered:
            return RetrievalOutcome(chunks=[], grounded=False, reason="rerank_degraded_no_match")

        # Top-N cut
        result = filtered[: policy.top_n]
        return RetrievalOutcome(chunks=result, grounded=True, reason=None)
