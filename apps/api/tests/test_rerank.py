"""Reranker tests."""

from types import SimpleNamespace
from typing import Any

import pytest
from tenacity import wait_none

from app.config import Settings
from app.retrieval.rerank import (
    FakeReranker,
    LLMReranker,
    RerankCandidate,
    build_reranker,
)


def test_fake_reranker_scores_by_term_overlap() -> None:
    """FakeReranker scores based on query word frequency in content."""
    reranker = FakeReranker()
    candidates = [
        RerankCandidate(index=0, content="apple banana cherry"),
        RerankCandidate(index=1, content="apple apple banana"),
        RerankCandidate(index=2, content="date elderberry fig"),
    ]
    scores = reranker.score("apple banana", candidates)

    assert len(scores) == 3
    # Candidates 0 and 1 have both words; candidate 2 has neither
    assert scores[0] > 0
    assert scores[1] > scores[0]  # More overlaps
    assert scores[2] == 0


def test_fake_reranker_is_deterministic() -> None:
    """Same input always produces same scores."""
    reranker = FakeReranker()
    candidates = [
        RerankCandidate(index=0, content="test content"),
        RerankCandidate(index=1, content="other data"),
    ]
    scores1 = reranker.score("test", candidates)
    scores2 = reranker.score("test", candidates)

    assert scores1 == scores2


class _FakeCompletions:
    """Endpoint stand-in: scripted responses, or an error keyed to a call index."""

    def __init__(self, contents: list[str], errors: list[Exception | None] | None = None) -> None:
        self._contents = contents
        self._errors = errors or []
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        index = len(self.calls) - 1
        if index < len(self._errors) and self._errors[index] is not None:
            raise self._errors[index]  # type: ignore[misc]
        content = self._contents[min(index, len(self._contents) - 1)]
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=9000, completion_tokens=120),
        )


class _StatusError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


def _llm_reranker(
    contents: list[str], errors: list[Exception | None] | None = None
) -> tuple[LLMReranker, _FakeCompletions]:
    completions = _FakeCompletions(contents, errors)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return LLMReranker(client, "openai/gpt-oss-120b", 2048), completions


_TWO_CANDIDATES = [
    RerankCandidate(index=0, content="good match"),
    RerankCandidate(index=1, content="weak match"),
]


@pytest.fixture
def no_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the retry behaviour, drop the backoff sleeps."""
    monkeypatch.setattr(LLMReranker._score_impl.retry, "wait", wait_none())  # type: ignore[attr-defined]


_CLEAN_JSON = '{"passages": [{"index": 0, "score": 8}, {"index": 1, "score": 5}]}'


def test_llm_reranker_parses_clean_json() -> None:
    reranker, _ = _llm_reranker([_CLEAN_JSON])

    assert reranker.score("query", _TWO_CANDIDATES) == [8, 5]


def test_llm_reranker_parses_fenced_json() -> None:
    reranker, _ = _llm_reranker(
        ['Sure:\n```json\n{"passages": [{"index": 0, "score": 2}, {"index": 1, "score": 9}]}\n```']
    )

    assert reranker.score("query", _TWO_CANDIDATES) == [2, 9]


def test_llm_reranker_parses_json_behind_a_reasoning_block() -> None:
    reranker, _ = _llm_reranker(
        [
            "<think>passage 0 is off topic</think>\n"
            '{"passages": [{"index": 0, "score": 0}, {"index": 1, "score": 7}]}'
        ]
    )

    assert reranker.score("query", _TWO_CANDIDATES) == [0, 7]


def test_llm_reranker_rejects_a_mismatched_index_set(no_retry_wait: None) -> None:
    reranker, _ = _llm_reranker(['{"passages": [{"index": 0, "score": 8}]}'])

    with pytest.raises(ValueError):
        reranker.score("query", _TWO_CANDIDATES)


def test_llm_reranker_retries_once_without_response_format(no_retry_wait: None) -> None:
    reranker, completions = _llm_reranker(
        [_CLEAN_JSON],
        errors=[_StatusError(400, "response_format is not supported by this provider")],
    )

    assert reranker.score("query", _TWO_CANDIDATES) == [8, 5]
    assert "response_format" in completions.calls[0]
    assert "response_format" not in completions.calls[1]

    # The fallback is remembered, so the next call does not rediscover it.
    assert reranker.score("query", _TWO_CANDIDATES) == [8, 5]
    assert "response_format" not in completions.calls[2]


def test_llm_reranker_does_not_retry_a_billing_failure(no_retry_wait: None) -> None:
    reranker, completions = _llm_reranker([""], errors=[_StatusError(402, "out of credits")] * 6)

    with pytest.raises(_StatusError):
        reranker.score("query", _TWO_CANDIDATES)

    assert len(completions.calls) == 1


def test_llm_reranker_retries_a_transient_failure(no_retry_wait: None) -> None:
    reranker, completions = _llm_reranker(
        [_CLEAN_JSON],
        errors=[_StatusError(503, "service unavailable")],
    )

    assert reranker.score("query", _TWO_CANDIDATES) == [8, 5]
    assert len(completions.calls) == 2


def test_build_reranker_returns_the_real_adapter_with_a_token() -> None:
    assert isinstance(build_reranker(Settings(llm_token="tok")), LLMReranker)


def test_build_reranker_falls_back_to_the_fake_without_a_token() -> None:
    assert isinstance(build_reranker(Settings(llm_token=None)), FakeReranker)
