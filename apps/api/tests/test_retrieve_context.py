"""RetrieveContext reports whether the reranker ran and how many candidates it saw."""

from uuid import UUID, uuid4

import pytest

from app.application.usecases.chat.retrieve_context import RetrieveContext
from app.domain.values.policies import RetrievalPolicy
from app.domain.values.retrieval import RetrievedChunk

pytestmark = pytest.mark.unit

POLICY = RetrievalPolicy(top_k=5, min_score=5, max_distance=0.75, top_n=1)
CANDIDATES = [
    RetrievedChunk(
        chunk_id=uuid4(), distance=0.1 * i, content=f"c{i}", page_start=i, page_end=i,
        section_title=None,
    )
    for i in range(1, 4)
]


class Chunks:
    async def search_similar(
        self, document_id: UUID, vector: list[float], limit: int
    ) -> list[RetrievedChunk]:
        return CANDIDATES


class Uow:
    chunks = Chunks()


class Embedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] for _ in texts]


class Reranker:
    def __init__(self, fail: bool) -> None:
        self.fail = fail

    async def score(self, query: str, passages: list[str]) -> list[int]:
        if self.fail:
            raise RuntimeError("rerank 500")
        return [9 for _ in passages]


async def retrieve(fail: bool):  # type: ignore[no-untyped-def]
    context = RetrieveContext(Uow(), Embedder(), Reranker(fail), POLICY)  # type: ignore[arg-type]
    return await context.retrieve(uuid4(), "query")


async def test_reranked_result_counts_candidates_before_the_cut() -> None:
    result = await retrieve(fail=False)

    assert result.reranked is True
    assert result.candidate_count == 3
    assert len(result.scored_chunks) == 1


async def test_reranker_failure_is_reported() -> None:
    result = await retrieve(fail=True)

    assert result.reranked is False
    assert result.candidate_count == 3
