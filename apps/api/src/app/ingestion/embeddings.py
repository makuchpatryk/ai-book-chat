"""Embedding backends.

`Embedder` is the seam: the pipeline never imports OpenAI directly, so tests run
offline against `FakeEmbedder` and the live path is opt-in.
"""

import hashlib
import logging
import math
import random
from typing import Protocol

from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 6
_RETRYABLE = (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:
        """One vector per input text, in the same order."""
        ...


class OpenAIEmbedder:
    """Batched OpenAI embeddings with backoff on the transient failures."""

    def __init__(
        self,
        client: OpenAI,
        model: str,
        dimensions: int,
        batch_size: int = 100,
    ) -> None:
        self._client = client
        self._model = model
        self._dimensions = dimensions
        self._batch_size = batch_size

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            vectors.extend(self._embed_batch(texts[start : start + self._batch_size]))
        return vectors

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        wait=wait_exponential_jitter(initial=1, max=30),
        stop=stop_after_attempt(MAX_ATTEMPTS),
        reraise=True,
    )
    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(
            model=self._model, input=batch, dimensions=self._dimensions
        )
        # The API does not promise ordered `data`, only an `index` on each item.
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]


class FakeEmbedder:
    """Deterministic offline stand-in: same text in, same unit vector out.

    Nearest-neighbour results are meaningless, but every shape assertion the
    pipeline and the database make still holds, and `calls` lets tests prove no
    second embedding run happened.
    """

    def __init__(self, dimensions: int = 1536) -> None:
        self.dimensions = dimensions
        self.calls = 0
        self.embedded_texts = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        self.embedded_texts += len(texts)
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        seed = hashlib.sha256(text.encode("utf-8")).hexdigest()
        rng = random.Random(seed)
        values = [rng.gauss(0.0, 1.0) for _ in range(self.dimensions)]
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]


def build_embedder(settings: Settings | None = None) -> Embedder:
    """Real embedder when a key is configured, deterministic fake otherwise."""
    settings = settings or get_settings()
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY unset — using FakeEmbedder; search results will be noise")
        return FakeEmbedder(settings.embedding_dimensions)

    return OpenAIEmbedder(
        client=OpenAI(api_key=settings.openai_api_key),
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        batch_size=settings.embedding_batch_size,
    )
