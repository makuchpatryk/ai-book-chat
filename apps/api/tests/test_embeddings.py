"""Embedding backends."""

from typing import Any

import httpx
import pytest
from tenacity import wait_none

from app.config import Settings
from app.ingestion.embeddings import (
    FakeEmbedder,
    OllamaEmbedder,
    build_embedder,
)


class _StubOllama:
    """Stands in for the `/api/embed` endpoint, recording what it was sent."""

    def __init__(self, dimensions: int = 768, errors: list[Exception] | None = None) -> None:
        self.dimensions = dimensions
        self.errors = errors or []
        self.batches: list[list[str]] = []

    def post(self, url: str, *, json: dict[str, Any], timeout: float) -> Any:
        self.batches.append(json["input"])
        if self.errors:
            raise self.errors.pop(0)
        vectors = [[float(index)] * self.dimensions for index in range(len(json["input"]))]
        return type(
            "Response",
            (),
            {"raise_for_status": lambda self: None, "json": lambda self: {"embeddings": vectors}},
        )()


def _ollama_embedder(
    stub: _StubOllama, monkeypatch: pytest.MonkeyPatch, **kwargs: Any
) -> OllamaEmbedder:
    monkeypatch.setattr(httpx, "post", stub.post)
    return OllamaEmbedder(
        base_url=kwargs.pop("base_url", "http://ollama:11434"),
        model=kwargs.pop("model", "nomic-embed-text"),
        dimensions=kwargs.pop("dimensions", 768),
        **kwargs,
    )


def test_ollama_embedder_batches_and_keeps_order(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = _StubOllama()

    vectors = _ollama_embedder(stub, monkeypatch, batch_size=2).embed(["a", "b", "c"])

    assert stub.batches == [["a", "b"], ["c"]]
    assert [vector[0] for vector in vectors] == [0.0, 1.0, 0.0]


def test_ollama_embedder_rejects_vectors_the_column_cannot_hold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 1024-wide model against the 768-wide column: only the model knows its
    # width, so the build-time guard cannot catch this one.
    stub = _StubOllama(dimensions=1024)
    embedder = _ollama_embedder(stub, monkeypatch, batch_size=1)

    with pytest.raises(ValueError, match="1024-dimensional"):
        embedder.embed(["a", "b", "c"])

    # Failed on the first batch, not after embedding the whole document.
    assert len(stub.batches) == 1


def test_ollama_embedder_retries_a_transient_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(OllamaEmbedder._embed_batch.retry, "wait", wait_none())
    stub = _StubOllama(errors=[httpx.ConnectError("boom")])

    vectors = _ollama_embedder(stub, monkeypatch).embed(["a"])

    assert len(stub.batches) == 2
    assert len(vectors[0]) == 768


def test_build_embedder_needs_no_key() -> None:
    assert isinstance(build_embedder(Settings(llm_token=None)), OllamaEmbedder)


def test_build_embedder_refuses_a_dimension_the_column_cannot_hold() -> None:
    settings = Settings(embedding_dimensions=1024)

    with pytest.raises(ValueError, match="chunks.embedding column"):
        build_embedder(settings)


def test_fake_embedder_is_deterministic_and_the_column_width() -> None:
    embedder = FakeEmbedder()

    first = embedder.embed(["chapter one", "chapter two"])
    second = embedder.embed(["chapter one"])

    assert [len(vector) for vector in first] == [768, 768]
    assert first[0] == second[0]
    assert embedder.calls == 2
    assert embedder.embedded_texts == 3
