"""Reranker tests."""

from unittest.mock import MagicMock, patch

import pytest

from app.retrieval.rerank import (
    AnthropicReranker,
    FakeReranker,
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
