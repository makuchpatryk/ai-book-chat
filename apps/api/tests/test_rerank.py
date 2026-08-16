"""Reranker tests."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from tenacity import wait_none

from app.config import Settings
from app.retrieval.rerank import (
    AnthropicReranker,
    FakeReranker,
    HFReranker,
    MistralReranker,
    OllamaReranker,
    RerankCandidate,
    RerankScores,
    ScoredPassage,
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


def test_anthropic_reranker_happy_path() -> None:
    """AnthropicReranker calls the API and extracts scores."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.parsed = RerankScores(
        passages=[
            ScoredPassage(index=0, score=8),
            ScoredPassage(index=1, score=5),
        ]
    )
    mock_response.usage.input_tokens = 1000
    mock_response.usage.output_tokens = 100

    mock_client.messages.parse.return_value = mock_response

    reranker = AnthropicReranker(mock_client, "claude-haiku-4-5", 2048)
    candidates = [
        RerankCandidate(index=0, content="good match"),
        RerankCandidate(index=1, content="weak match"),
    ]
    scores = reranker.score("query", candidates)

    assert scores == [8, 5]
    assert mock_client.messages.parse.called


def test_anthropic_reranker_validates_response_indices() -> None:
    """AnthropicReranker raises if response indices don't match input."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    # Response is missing index 1
    mock_response.parsed = RerankScores(passages=[ScoredPassage(index=0, score=8)])
    mock_response.usage.input_tokens = 1000
    mock_response.usage.output_tokens = 100

    mock_client.messages.parse.return_value = mock_response

    reranker = AnthropicReranker(mock_client, "claude-haiku-4-5", 2048)
    candidates = [
        RerankCandidate(index=0, content="match 0"),
        RerankCandidate(index=1, content="match 1"),
    ]

    with pytest.raises(ValueError):
        reranker.score("query", candidates)


def test_anthropic_reranker_logs_usage() -> None:
    """AnthropicReranker logs token usage."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.parsed = RerankScores(
        passages=[
            ScoredPassage(index=0, score=8),
            ScoredPassage(index=1, score=5),
        ]
    )
    mock_response.usage.input_tokens = 1000
    mock_response.usage.output_tokens = 100

    mock_client.messages.parse.return_value = mock_response

    reranker = AnthropicReranker(mock_client, "claude-haiku-4-5", 2048)
    candidates = [
        RerankCandidate(index=0, content="good match"),
        RerankCandidate(index=1, content="weak match"),
    ]
    scores = reranker.score("query", candidates)
    assert scores == [8, 5]


class _FakeCompletions:
    """Router stand-in: scripted responses, or an error keyed to a call index."""

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


def _hf_reranker(
    contents: list[str], errors: list[Exception | None] | None = None
) -> tuple[HFReranker, _FakeCompletions]:
    completions = _FakeCompletions(contents, errors)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return HFReranker(client, "openai/gpt-oss-120b:cheapest", 2048), completions


_TWO_CANDIDATES = [
    RerankCandidate(index=0, content="good match"),
    RerankCandidate(index=1, content="weak match"),
]


@pytest.fixture
def no_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the retry behaviour, drop the backoff sleeps."""
    monkeypatch.setattr(HFReranker._score_impl.retry, "wait", wait_none())  # type: ignore[attr-defined]


_CLEAN_JSON = '{"passages": [{"index": 0, "score": 8}, {"index": 1, "score": 5}]}'


def test_hf_reranker_parses_clean_json() -> None:
    reranker, _ = _hf_reranker([_CLEAN_JSON])

    assert reranker.score("query", _TWO_CANDIDATES) == [8, 5]


def test_hf_reranker_parses_fenced_json() -> None:
    reranker, _ = _hf_reranker(
        ['Sure:\n```json\n{"passages": [{"index": 0, "score": 2}, {"index": 1, "score": 9}]}\n```']
    )

    assert reranker.score("query", _TWO_CANDIDATES) == [2, 9]


def test_hf_reranker_parses_json_behind_a_reasoning_block() -> None:
    reranker, _ = _hf_reranker(
        [
            "<think>passage 0 is off topic</think>\n"
            '{"passages": [{"index": 0, "score": 0}, {"index": 1, "score": 7}]}'
        ]
    )

    assert reranker.score("query", _TWO_CANDIDATES) == [0, 7]


def test_hf_reranker_rejects_a_mismatched_index_set(no_retry_wait: None) -> None:
    reranker, _ = _hf_reranker(['{"passages": [{"index": 0, "score": 8}]}'])

    with pytest.raises(ValueError):
        reranker.score("query", _TWO_CANDIDATES)


def test_hf_reranker_retries_once_without_response_format(no_retry_wait: None) -> None:
    reranker, completions = _hf_reranker(
        [_CLEAN_JSON],
        errors=[_StatusError(400, "response_format is not supported by this provider")],
    )

    assert reranker.score("query", _TWO_CANDIDATES) == [8, 5]
    assert "response_format" in completions.calls[0]
    assert "response_format" not in completions.calls[1]

    # The fallback is remembered, so the next call does not rediscover it.
    assert reranker.score("query", _TWO_CANDIDATES) == [8, 5]
    assert "response_format" not in completions.calls[2]


def test_hf_reranker_does_not_retry_a_billing_failure(no_retry_wait: None) -> None:
    reranker, completions = _hf_reranker([""], errors=[_StatusError(402, "out of credits")] * 6)

    with pytest.raises(_StatusError):
        reranker.score("query", _TWO_CANDIDATES)

    assert len(completions.calls) == 1


def test_hf_reranker_retries_a_transient_failure(no_retry_wait: None) -> None:
    reranker, completions = _hf_reranker(
        [_CLEAN_JSON],
        errors=[_StatusError(503, "service unavailable")],
    )

    assert reranker.score("query", _TWO_CANDIDATES) == [8, 5]
    assert len(completions.calls) == 2


def test_build_reranker_uses_huggingface_by_default_with_a_token() -> None:
    assert isinstance(build_reranker(Settings(hf_token="hf_test")), HFReranker)


def test_build_reranker_uses_fake_without_key() -> None:
    """build_reranker returns FakeReranker when LLM_API_KEY is unset."""
    from app.config import Settings

    settings = Settings(llm_api_key=None)
    reranker = build_reranker(settings)

    assert isinstance(reranker, FakeReranker)


def test_build_reranker_uses_anthropic_with_key() -> None:
    """build_reranker returns AnthropicReranker for anthropic provider."""
    from app.config import Settings

    settings = Settings(rerank_provider="anthropic", llm_api_key="sk-test-key")
    with patch("anthropic.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        reranker = build_reranker(settings)

        assert isinstance(reranker, AnthropicReranker)
        mock_anthropic.assert_called_with(api_key="sk-test-key")


@pytest.mark.skipif(
    __import__("importlib.util").util.find_spec("mistralai") is None,
    reason="mistralai not installed",
)
def test_build_reranker_uses_mistral_with_key() -> None:
    """build_reranker returns MistralReranker for mistral provider."""
    from app.config import Settings

    settings = Settings(rerank_provider="mistral", llm_api_key="sk-test-key")
    with patch("mistralai.Mistral") as mock_mistral:
        mock_client = MagicMock()
        mock_mistral.return_value = mock_client

        reranker = build_reranker(settings)

        assert isinstance(reranker, MistralReranker)
        mock_mistral.assert_called_with(api_key="sk-test-key")


def test_build_reranker_uses_ollama_without_key() -> None:
    """build_reranker returns OllamaReranker for ollama (no key needed)."""
    from app.config import Settings

    settings = Settings(
        rerank_provider="ollama",
        ollama_base_url="http://localhost:11434",
    )
    reranker = build_reranker(settings)

    assert isinstance(reranker, OllamaReranker)
