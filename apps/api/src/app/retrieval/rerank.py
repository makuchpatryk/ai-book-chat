"""LLM re-ranking of retrieved chunks.

Adapter pattern: single Reranker interface, multiple provider implementations.
Supports Anthropic, Mistral, Ollama, and deterministic offline fallback.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 6

SCORING_PROMPT = """You score passages from a single book for relevance to a reader's question.
For each numbered passage return an integer 0-10:
  0-2  unrelated to the question
  3-5  same topic, does not answer the question
  6-8  contains part of the answer
  9-10 directly answers the question
Judge only the passage text. Never infer content that is not present.
Return one score per passage, in the order given."""


@dataclass
class RerankCandidate:
    """A chunk to be re-ranked."""

    index: int
    content: str


class ScoredPassage(BaseModel):
    index: int
    score: int


class RerankScores(BaseModel):
    passages: list[ScoredPassage]


class Reranker(Protocol):
    """Common interface for LLM re-ranking providers."""

    def score(self, query: str, candidates: list[RerankCandidate]) -> list[int]:
        """Return scores 0-10 for each candidate, in the same order."""
        ...


class FakeReranker:
    """Deterministic offline re-ranker: scores by term overlap."""

    def score(self, query: str, candidates: list[RerankCandidate]) -> list[int]:
        """Score candidates by how many query words appear in content."""
        query_words = set(re.findall(r"\w+", query.lower()))
        scores: list[int] = []
        for candidate in candidates:
            content_words = re.findall(r"\w+", candidate.content.lower())
            overlap = sum(content_words.count(word) for word in query_words)
            score = min(10, max(0, overlap))
            scores.append(score)
        return scores


class AnthropicReranker:
    """Anthropic Claude re-ranker with retry and logging."""

    def __init__(self, client: Any, model: str, max_tokens: int) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    def score(self, query: str, candidates: list[RerankCandidate]) -> list[int]:
        """Score all candidates in one call; raises on failure."""
        numbered_passages = "\n".join(
            f"[{c.index}] {c.content[:1200]}" for c in candidates
        )
        result = self._score_impl(query, numbered_passages)

        scores_by_index = {p.index: p.score for p in result["scores"].passages}
        expected_indices = {c.index for c in candidates}
        if set(scores_by_index.keys()) != expected_indices:
            raise ValueError(
                f"response indices {set(scores_by_index.keys())} != expected {expected_indices}"
            )

        scores = [scores_by_index[c.index] for c in candidates]
        logger.info(
            "rerank scores",
            extra={
                "passage_count": len(candidates),
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
                "provider": "anthropic",
            },
        )
        return scores

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential_jitter(initial=1, max=30),
        stop=stop_after_attempt(MAX_ATTEMPTS),
        reraise=True,
    )
    def _score_impl(self, query: str, numbered_passages: str) -> dict[str, Any]:
        """Call Claude with the re-rank prompt."""
        message = self._client.messages.parse(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": f"{query}\n\n{numbered_passages}",
                }
            ],
            system=SCORING_PROMPT,
            output_format=RerankScores,
        )
        return {
            "scores": message.parsed,
            "input_tokens": message.usage.input_tokens,
            "output_tokens": message.usage.output_tokens,
        }


class MistralReranker:
    """Mistral API re-ranker with retry and logging."""

    def __init__(self, client: Any, model: str, max_tokens: int) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    def score(self, query: str, candidates: list[RerankCandidate]) -> list[int]:
        """Score all candidates via Mistral."""
        numbered_passages = "\n".join(
            f"[{c.index}] {c.content[:1200]}" for c in candidates
        )
        result = self._score_impl(query, numbered_passages)

        scores_by_index = {p.index: p.score for p in result["scores"].passages}
        expected_indices = {c.index for c in candidates}
        if set(scores_by_index.keys()) != expected_indices:
            raise ValueError(
                f"response indices {set(scores_by_index.keys())} != expected {expected_indices}"
            )

        scores = [scores_by_index[c.index] for c in candidates]
        logger.info(
            "rerank scores",
            extra={
                "passage_count": len(candidates),
                "input_tokens": result.get("input_tokens", 0),
                "output_tokens": result.get("output_tokens", 0),
                "provider": "mistral",
            },
        )
        return scores

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential_jitter(initial=1, max=30),
        stop=stop_after_attempt(MAX_ATTEMPTS),
        reraise=True,
    )
    def _score_impl(self, query: str, numbered_passages: str) -> dict[str, Any]:
        """Call Mistral with the re-rank prompt."""
        message = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": f"{query}\n\n{numbered_passages}",
                }
            ],
        )
        # Parse JSON response from Mistral
        response_text = message.content[0].text
        try:
            parsed = json.loads(response_text)
            scores_list = [
                ScoredPassage(index=p["index"], score=p["score"])
                for p in parsed.get("passages", [])
            ]
            return {
                "scores": RerankScores(passages=scores_list),
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
            }
        except (json.JSONDecodeError, KeyError) as e:
            raise ValueError(f"Failed to parse Mistral response: {e}") from e


class OllamaReranker:
    """Local Ollama re-ranker (via HTTP endpoint)."""

    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._session = None

    def score(self, query: str, candidates: list[RerankCandidate]) -> list[int]:
        """Score via local Ollama instance."""
        import httpx

        numbered_passages = "\n".join(
            f"[{c.index}] {c.content[:1200]}" for c in candidates
        )
        prompt = f"{SCORING_PROMPT}\n\n{query}\n\n{numbered_passages}"

        try:
            response = httpx.post(
                f"{self._base_url}/api/generate",
                json={"model": self._model, "prompt": prompt, "stream": False},
                timeout=60.0,
            )
            response.raise_for_status()
            result = response.json()
            response_text = result.get("response", "")

            parsed = json.loads(response_text)
            scores_list = [
                ScoredPassage(index=p["index"], score=p["score"])
                for p in parsed.get("passages", [])
            ]
            scores_by_index = {p.index: p.score for p in scores_list}
            expected_indices = {c.index for c in candidates}
            if set(scores_by_index.keys()) != expected_indices:
                raise ValueError(
                    f"response indices {set(scores_by_index.keys())} != expected {expected_indices}"
                )
            return [scores_by_index[c.index] for c in candidates]
        except Exception as e:
            logger.warning(f"Ollama request failed: {e}")
            raise


def build_reranker(settings: Settings | None = None) -> Reranker:
    """Build re-ranker based on configured provider and API key."""
    settings = settings or get_settings()

    provider = settings.rerank_provider.lower()
    api_key = settings.llm_api_key

    # Ollama doesn't need an API key (local)
    if provider == "ollama":
        return OllamaReranker(
            base_url=settings.ollama_base_url, model=settings.rerank_model
        )

    # Fallback to FakeReranker if no key is set for other providers
    if not api_key:
        logger.warning(
            "LLM_API_KEY unset — using FakeReranker; results will be unranked"
        )
        return FakeReranker()

    # Anthropic
    if provider == "anthropic":
        try:
            from anthropic import Anthropic

            return AnthropicReranker(
                client=Anthropic(api_key=api_key),
                model=settings.rerank_model,
                max_tokens=settings.rerank_max_tokens,
            )
        except ImportError:
            logger.error("anthropic package not installed; falling back to FakeReranker")
            return FakeReranker()

    # Mistral
    elif provider == "mistral":
        try:
            from mistralai import Mistral  # type: ignore[import-not-found]

            return MistralReranker(
                client=Mistral(api_key=api_key),
                model=settings.rerank_model,
                max_tokens=settings.rerank_max_tokens,
            )
        except ImportError:
            logger.error("mistralai package not installed; falling back to FakeReranker")
            return FakeReranker()

    # Unknown provider
    else:
        logger.warning(f"Unknown provider '{provider}'; falling back to FakeReranker")
        return FakeReranker()
