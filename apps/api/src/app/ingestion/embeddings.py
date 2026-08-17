"""Embedding backends.

`Embedder` is the seam: the pipeline never talks to Ollama directly, so tests
run offline against `FakeEmbedder` and the live path is opt-in.
"""

import hashlib
import logging
import math
import random
from typing import Protocol

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 6


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:
        """One vector per input text, in the same order."""
        ...


class OllamaEmbedder:
    """Local Ollama embeddings over HTTP — no key, no per-token cost.

    Embedding is the one stage a CPU-only box handles comfortably: short inputs
    and no token generation, unlike the chat and re-rank calls.

    The width check is not paranoia. `nomic-embed-text` is 768-dimensional and
    `chunks.embedding` is a fixed-width column — pointing this at another local
    model is a migration, not a config change.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        dimensions: int,
        batch_size: int = 32,
        timeout: float = 120.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dimensions = dimensions
        self._batch_size = batch_size
        self._timeout = timeout

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch_vectors = self._embed_batch(texts[start : start + self._batch_size])
            # Checked on the first batch rather than after the whole book: only
            # the model knows its width, and it has to match the column.
            if batch_vectors and len(batch_vectors[0]) != self._dimensions:
                raise ValueError(
                    f"{self._model} returned {len(batch_vectors[0])}-dimensional vectors, "
                    f"expected {self._dimensions}; set EMBEDDING_DIMENSIONS to the model's "
                    f"width and migrate the chunks.embedding column to match"
                )
            vectors.extend(batch_vectors)
        return vectors

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
        wait=wait_exponential_jitter(initial=1, max=30),
        stop=stop_after_attempt(MAX_ATTEMPTS),
        reraise=True,
    )
    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        response = httpx.post(
            f"{self._base_url}/api/embed",
            json={"model": self._model, "input": batch},
            timeout=self._timeout,
        )
        response.raise_for_status()
        # `/api/embed` answers in request order, one vector per input.
        return [[float(value) for value in row] for row in response.json()["embeddings"]]


class FakeEmbedder:
    """Deterministic offline stand-in: same text in, same unit vector out.

    Nearest-neighbour results are meaningless, but every shape assertion the
    pipeline and the database make still holds, and `calls` lets tests prove no
    second embedding run happened.
    """

    def __init__(self, dimensions: int = 768) -> None:
        # Defaults to the width of `chunks.embedding`, so a bare `FakeEmbedder()`
        # produces vectors the column will accept.
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
    """Local Ollama embeddings; refuses to build if it cannot fit the column."""
    settings = settings or get_settings()
    _require_column_width(settings)

    return OllamaEmbedder(
        base_url=settings.ollama_base_url,
        model=settings.ollama_embedding_model,
        dimensions=settings.embedding_dimensions,
        batch_size=settings.embedding_batch_size,
    )


def _require_column_width(settings: Settings) -> None:
    """Raise unless the configured width is the one `chunks.embedding` holds.

    `chunks.embedding` is a fixed-width `Vector`, so a model with a different
    dimension has to be a migration, not a config change. Failing here beats a
    `DataError` thousands of chunks into a re-ingest.

    This only catches a configured width the column cannot hold; the model's real
    width is unknown until it answers, so the embedder checks that on the first
    batch.
    """
    # Imported lazily: the vector width lives with the model, and this keeps the
    # ingestion module importable without the ORM.
    from app.db.models.chunk import EMBEDDING_DIMENSIONS as COLUMN_DIMENSIONS

    if settings.embedding_dimensions != COLUMN_DIMENSIONS:
        raise ValueError(
            f"EMBEDDING_DIMENSIONS={settings.embedding_dimensions} does not match the "
            f"chunks.embedding column ({COLUMN_DIMENSIONS}); migrate the column first"
        )
