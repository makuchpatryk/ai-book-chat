"""Unit tests for domain relevance service (no infrastructure, marked unit)."""

import pytest
from uuid import uuid4

from app.domain.services.relevance import guard_and_cut, RetrievalOutcome
from app.domain.values.policies import RetrievalPolicy
from app.domain.values.retrieval import RetrievedChunk, ScoredChunk

pytestmark = pytest.mark.unit


def make_scored_chunk(idx: int, distance: float, score: int | None = None) -> ScoredChunk:
    """Helper to create a scored chunk."""
    chunk = RetrievedChunk(
        chunk_id=uuid4(),
        distance=distance,
        content=f"Chunk {idx}",
        page_start=idx,
        page_end=idx,
        section_title="Section",
    )
    return ScoredChunk(chunk=chunk, score=score)


class TestGuardAndCutEmpty:
    """Test guard_and_cut with empty input."""

    def test_empty_chunks(self) -> None:
        """Empty chunk list returns no_chunks reason."""
        policy = RetrievalPolicy(top_k=30, min_score=5, max_distance=0.75, top_n=8)

        outcome = guard_and_cut([], policy)

        assert outcome.grounded is False
        assert outcome.reason == "no_chunks"
        assert len(outcome.chunks) == 0


class TestGuardAndCutScoredChunks:
    """Test guard_and_cut with re-ranked (scored) chunks."""

    def test_min_score_filter(self) -> None:
        """Chunks below min_score are filtered out."""
        chunks = [
            make_scored_chunk(0, 0.1, score=10),
            make_scored_chunk(1, 0.2, score=3),  # Below threshold
            make_scored_chunk(2, 0.3, score=8),
        ]
        policy = RetrievalPolicy(top_k=30, min_score=5, max_distance=0.75, top_n=8)

        outcome = guard_and_cut(chunks, policy)

        assert outcome.grounded is True
        assert outcome.reason is None
        assert len(outcome.chunks) == 2
        # Should be sorted by score descending
        assert outcome.chunks[0].score == 10
        assert outcome.chunks[1].score == 8

    def test_all_filtered_no_relevant_chunks(self) -> None:
        """All chunks filtered by min_score returns no_relevant_chunks."""
        chunks = [
            make_scored_chunk(0, 0.1, score=2),
            make_scored_chunk(1, 0.2, score=1),
        ]
        policy = RetrievalPolicy(top_k=30, min_score=5, max_distance=0.75, top_n=8)

        outcome = guard_and_cut(chunks, policy)

        assert outcome.grounded is False
        assert outcome.reason == "no_relevant_chunks"
        assert len(outcome.chunks) == 0

    def test_top_n_cut(self) -> None:
        """Results are cut to top_n."""
        chunks = [
            make_scored_chunk(0, 0.1, score=10),
            make_scored_chunk(1, 0.2, score=9),
            make_scored_chunk(2, 0.3, score=8),
        ]
        policy = RetrievalPolicy(top_k=30, min_score=5, max_distance=0.75, top_n=2)

        outcome = guard_and_cut(chunks, policy)

        assert len(outcome.chunks) == 2
        assert outcome.chunks[0].score == 10
        assert outcome.chunks[1].score == 9

    def test_sorted_by_score_descending(self) -> None:
        """Results are sorted by score descending."""
        chunks = [
            make_scored_chunk(0, 0.1, score=5),
            make_scored_chunk(1, 0.2, score=15),
            make_scored_chunk(2, 0.3, score=10),
        ]
        policy = RetrievalPolicy(top_k=30, min_score=1, max_distance=0.75, top_n=8)

        outcome = guard_and_cut(chunks, policy)

        assert outcome.chunks[0].score == 15
        assert outcome.chunks[1].score == 10
        assert outcome.chunks[2].score == 5


class TestGuardAndCutDegradedChunks:
    """Test guard_and_cut with degraded (distance-based, no score) chunks."""

    def test_distance_filter(self) -> None:
        """Chunks above max_distance are filtered out."""
        chunks = [
            make_scored_chunk(0, 0.5),  # score=None
            make_scored_chunk(1, 0.8),  # Above threshold
            make_scored_chunk(2, 0.6),
        ]
        policy = RetrievalPolicy(top_k=30, min_score=5, max_distance=0.75, top_n=8)

        outcome = guard_and_cut(chunks, policy)

        assert outcome.grounded is True
        assert outcome.reason is None
        assert len(outcome.chunks) == 2

    def test_all_filtered_rerank_degraded_no_match(self) -> None:
        """All chunks filtered by distance returns rerank_degraded_no_match."""
        chunks = [
            make_scored_chunk(0, 0.8),
            make_scored_chunk(1, 0.9),
        ]
        policy = RetrievalPolicy(top_k=30, min_score=5, max_distance=0.75, top_n=8)

        outcome = guard_and_cut(chunks, policy)

        assert outcome.grounded is False
        assert outcome.reason == "rerank_degraded_no_match"
        assert len(outcome.chunks) == 0

    def test_degraded_top_n_cut(self) -> None:
        """Degraded results are also cut to top_n (first N by distance order)."""
        chunks = [
            make_scored_chunk(0, 0.3),
            make_scored_chunk(1, 0.4),
            make_scored_chunk(2, 0.5),
        ]
        policy = RetrievalPolicy(top_k=30, min_score=5, max_distance=0.75, top_n=2)

        outcome = guard_and_cut(chunks, policy)

        assert len(outcome.chunks) == 2


class TestGuardAndCutMixed:
    """Test edge cases and mixed scenarios."""

    def test_single_chunk_below_threshold(self) -> None:
        """Single chunk below threshold is filtered."""
        chunks = [make_scored_chunk(0, 0.1, score=2)]
        policy = RetrievalPolicy(top_k=30, min_score=5, max_distance=0.75, top_n=8)

        outcome = guard_and_cut(chunks, policy)

        assert outcome.grounded is False
        assert outcome.reason == "no_relevant_chunks"

    def test_single_chunk_above_threshold(self) -> None:
        """Single chunk above threshold passes."""
        chunks = [make_scored_chunk(0, 0.1, score=10)]
        policy = RetrievalPolicy(top_k=30, min_score=5, max_distance=0.75, top_n=8)

        outcome = guard_and_cut(chunks, policy)

        assert outcome.grounded is True
        assert outcome.reason is None
        assert len(outcome.chunks) == 1

    def test_chunk_exactly_at_min_score(self) -> None:
        """Chunk exactly at min_score passes."""
        chunks = [make_scored_chunk(0, 0.1, score=5)]
        policy = RetrievalPolicy(top_k=30, min_score=5, max_distance=0.75, top_n=8)

        outcome = guard_and_cut(chunks, policy)

        assert outcome.grounded is True
        assert len(outcome.chunks) == 1

    def test_chunk_exactly_at_max_distance(self) -> None:
        """Degraded chunk exactly at max_distance passes."""
        chunks = [make_scored_chunk(0, 0.75)]
        policy = RetrievalPolicy(top_k=30, min_score=5, max_distance=0.75, top_n=8)

        outcome = guard_and_cut(chunks, policy)

        assert outcome.grounded is True
        assert len(outcome.chunks) == 1
