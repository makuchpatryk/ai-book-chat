"""Unit tests for TypeSafeReranker (stubbed SDK client)."""

from types import SimpleNamespace

import pytest

from app.infrastructure.llm import typesafe_reranker
from app.infrastructure.llm.typesafe_reranker import TypeSafeReranker

pytestmark = pytest.mark.unit


class StubClient:
    """Scores a passage by the number in its text; raises on 'boom'."""

    calls: list[dict[str, object]] = []
    inits: list[dict[str, object]] = []

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.inits.append(kwargs)

    async def __aenter__(self) -> "StubClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def system_one(self, state: dict[str, str], questions: dict[str, object]):  # noqa: ANN201
        self.calls.append({"state": state, "questions": questions})
        if state["passage"] == "boom":
            raise RuntimeError("service down")
        level = float(state["passage"])
        return SimpleNamespace(scores={"relevance": SimpleNamespace(score=level)})


@pytest.fixture(autouse=True)
def stub_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    StubClient.calls = []
    StubClient.inits = []
    monkeypatch.setattr(typesafe_reranker, "AsyncTypeSafeClient", StubClient)


async def test_levels_map_onto_zero_to_ten_in_input_order() -> None:
    reranker = TypeSafeReranker("key")

    scores = await reranker.score("what is x?", ["0", "1.5", "3", "2"])

    assert scores == [0, 5, 10, 7]


async def test_state_carries_question_and_passage() -> None:
    await TypeSafeReranker("key").score("what is x?", ["3"])

    assert StubClient.calls[0]["state"] == {"question": "what is x?", "passage": "3"}


async def test_out_of_range_score_is_clamped() -> None:
    assert await TypeSafeReranker("key").score("q", ["4.5"]) == [10]


async def test_no_passages_makes_no_calls() -> None:
    assert await TypeSafeReranker("key").score("q", []) == []
    assert StubClient.calls == []


async def test_one_failed_call_fails_the_whole_rerank() -> None:
    with pytest.raises(RuntimeError):
        await TypeSafeReranker("key").score("q", ["3", "boom", "1"])


async def test_base_url_and_model_reach_the_client() -> None:
    reranker = TypeSafeReranker(
        "key", model="jev-1.13", base_url="https://openrouter.ai/api"
    )
    await reranker.score("q", ["3"])

    assert StubClient.inits == [
        {"api_key": "key", "model": "jev-1.13", "base_url": "https://openrouter.ai/api"}
    ]
