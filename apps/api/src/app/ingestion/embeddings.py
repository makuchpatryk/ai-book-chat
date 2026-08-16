"""Embedding backends.

`Embedder` is the seam: the pipeline never imports OpenAI directly, so tests run
offline against `FakeEmbedder` and the live path is opt-in.
"""

import hashlib
import logging
import math
import random
from typing import Any, Protocol

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


class HFEmbedder:
    """Hugging Face feature-extraction embeddings via `InferenceClient`.

    Not the OpenAI-compatible router: its `/v1` surface is chat-only, so
    embeddings go through the task API instead.

    Asymmetric models (the e5 family, `multilingual-e5-large-instruct`) want
    `"query: "` on queries and `"passage: "` on documents; getting that wrong
    degrades recall quietly rather than failing. `Embedder` has a single
    `embed()` for both sides, so this instance applies the passage prefix —
    wiring the query side is part of the embeddings cutover, which also has to
    deal with the vector column's dimension.
    """

    def __init__(
        self,
        client: Any,
        model: str,
        batch_size: int = 32,
        query_prompt_name: str | None = None,
        passage_prefix: str | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._batch_size = batch_size
        self._query_prompt_name = query_prompt_name
        self._passage_prefix = passage_prefix

    def embed(self, texts: list[str]) -> list[list[float]]:
        prefixed = [f"{self._passage_prefix}{text}" if self._passage_prefix else text
                    for text in texts]
        vectors: list[list[float]] = []
        for start in range(0, len(prefixed), self._batch_size):
            vectors.extend(self._embed_batch(prefixed[start : start + self._batch_size]))
        return vectors

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential_jitter(initial=1, max=30),
        stop=stop_after_attempt(MAX_ATTEMPTS),
        reraise=True,
    )
    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        extra: dict[str, Any] = {}
        if self._query_prompt_name:
            # Models shipping a sentence-transformers prompts dict take the
            # prefix by name instead of inline.
            extra["prompt_name"] = self._query_prompt_name
        response = self._client.feature_extraction(
            text=batch, model=self._model, normalize=True, **extra
        )
        # `feature_extraction` returns a numpy array; the pgvector column wants
        # plain floats, and the response is in request order.
        return [[float(value) for value in row] for row in response]


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

    if settings.embedding_provider.lower() == "huggingface":
        return _build_hf_embedder(settings)

    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY unset — using FakeEmbedder; search results will be noise")
        return FakeEmbedder(settings.embedding_dimensions)

    return OpenAIEmbedder(
        client=OpenAI(api_key=settings.openai_api_key),
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        batch_size=settings.embedding_batch_size,
    )


def _build_hf_embedder(settings: Settings) -> Embedder:
    """Hugging Face embedder, refusing to build if it cannot fit the column.

    `chunks.embedding` is a fixed-width `Vector`, so a model with a different
    dimension has to be a migration, not a config change. Failing here beats a
    `DataError` thousands of chunks into a re-ingest.
    """
    # Imported lazily: the vector width lives with the model, and this keeps the
    # ingestion module importable without the ORM.
    from app.db.models.chunk import EMBEDDING_DIMENSIONS as COLUMN_DIMENSIONS

    if settings.embedding_dimensions != COLUMN_DIMENSIONS:
        raise ValueError(
            f"EMBEDDING_DIMENSIONS={settings.embedding_dimensions} does not match the "
            f"chunks.embedding column ({COLUMN_DIMENSIONS}); migrate the column first"
        )

    token = settings.hf_token or settings.llm_api_key
    if not token:
        logger.warning("HF_TOKEN unset — using FakeEmbedder; search results will be noise")
        return FakeEmbedder(settings.embedding_dimensions)

    try:
        from huggingface_hub import InferenceClient
    except ImportError:
        logger.error("huggingface_hub not installed; falling back to FakeEmbedder")
        return FakeEmbedder(settings.embedding_dimensions)

    return HFEmbedder(
        client=InferenceClient(api_key=token, bill_to=settings.hf_bill_to),
        model=settings.hf_embedding_model,
        batch_size=settings.embedding_batch_size,
        passage_prefix=settings.hf_embedding_passage_prefix,
    )
