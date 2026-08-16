from typing import Any

import httpx
import pytest
from huggingface_hub.errors import HfHubHTTPError
from openai import RateLimitError
from tenacity import wait_none

from app.config import Settings
from app.ingestion.embeddings import (
    MAX_ATTEMPTS,
    FakeEmbedder,
    HFEmbedder,
    OpenAIEmbedder,
    build_embedder,
)


class _StubEmbeddings:
    def __init__(self, dimensions: int = 1536, errors: list[Exception] | None = None) -> None:
        self.dimensions = dimensions
        self.errors = errors or []
        self.batch_sizes: list[int] = []

    def create(self, *, model: str, input: list[str], dimensions: int) -> Any:
        self.batch_sizes.append(len(input))
        if self.errors:
            raise self.errors.pop(0)
        # Returned out of order on purpose: the caller must sort by index.
        items = [
            type("Item", (), {"index": index, "embedding": [float(index)] * dimensions})
            for index in reversed(range(len(input)))
        ]
        return type("Response", (), {"data": items})


class _StubClient:
    def __init__(self, embeddings: _StubEmbeddings) -> None:
        self.embeddings = embeddings


def _rate_limit_error() -> RateLimitError:
    request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    return RateLimitError("slow down", response=httpx.Response(429, request=request), body=None)


@pytest.fixture
def no_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the retry behaviour, drop the backoff sleeps."""
    monkeypatch.setattr(OpenAIEmbedder._embed_batch.retry, "wait", wait_none())


def _embedder(stub: _StubEmbeddings, batch_size: int = 100) -> OpenAIEmbedder:
    return OpenAIEmbedder(
        client=_StubClient(stub),  # type: ignore[arg-type]
        model="text-embedding-3-small",
        dimensions=stub.dimensions,
        batch_size=batch_size,
    )


def test_fake_embedder_is_deterministic_and_correctly_sized() -> None:
    embedder = FakeEmbedder(dimensions=1536)

    first = embedder.embed(["alpha", "beta"])
    second = embedder.embed(["alpha"])

    assert [len(vector) for vector in first] == [1536, 1536]
    assert first[0] == second[0]
    assert first[0] != first[1]
    assert embedder.calls == 2
    assert embedder.embedded_texts == 3


def test_openai_embedder_splits_inputs_into_batches() -> None:
    stub = _StubEmbeddings(dimensions=4)
    vectors = _embedder(stub).embed([f"text {index}" for index in range(250)])

    assert stub.batch_sizes == [100, 100, 50]
    assert len(vectors) == 250
    # Sorted back into input order despite the stub returning them reversed.
    assert vectors[0] == [0.0] * 4
    assert vectors[1] == [1.0] * 4


def test_openai_embedder_retries_a_rate_limit(no_retry_wait: None) -> None:
    stub = _StubEmbeddings(dimensions=4, errors=[_rate_limit_error()])

    vectors = _embedder(stub).embed(["only one"])

    assert len(stub.batch_sizes) == 2
    assert len(vectors) == 1


def test_openai_embedder_gives_up_after_max_attempts(no_retry_wait: None) -> None:
    stub = _StubEmbeddings(dimensions=4, errors=[_rate_limit_error() for _ in range(MAX_ATTEMPTS)])

    with pytest.raises(RateLimitError):
        _embedder(stub).embed(["only one"])

    assert len(stub.batch_sizes) == MAX_ATTEMPTS


def test_build_embedder_falls_back_to_the_fake_without_a_key() -> None:
    assert isinstance(build_embedder(Settings(openai_api_key=None)), FakeEmbedder)
    assert isinstance(build_embedder(Settings(openai_api_key="sk-test")), OpenAIEmbedder)


class _StubInferenceClient:
    def __init__(self, dimensions: int = 4, errors: list[Exception] | None = None) -> None:
        self.dimensions = dimensions
        self.errors = errors or []
        self.batches: list[list[str]] = []

    def feature_extraction(
        self, *, text: list[str], model: str, normalize: bool, **kwargs: Any
    ) -> list[list[float]]:
        self.batches.append(text)
        if self.errors:
            raise self.errors.pop(0)
        return [[float(offset)] * self.dimensions for offset in range(len(text))]


def _hf_http_error(status: int) -> HfHubHTTPError:
    """A real `huggingface_hub` error: it carries its status on `.response`, not itself."""
    request = httpx.Request("POST", "https://router.huggingface.co/models/e5")
    return HfHubHTTPError("nope", response=httpx.Response(status, request=request))


@pytest.fixture
def no_hf_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the retry behaviour, drop the backoff sleeps."""
    monkeypatch.setattr(HFEmbedder._embed_batch.retry, "wait", wait_none())


def _hf_embedder(stub: _StubInferenceClient, **kwargs: Any) -> HFEmbedder:
    kwargs.setdefault("dimensions", stub.dimensions)
    return HFEmbedder(client=stub, model="intfloat/multilingual-e5", **kwargs)


def test_hf_embedder_batches_and_preserves_order() -> None:
    stub = _StubInferenceClient()
    vectors = _hf_embedder(stub, batch_size=2).embed(["a", "b", "c"])

    assert [len(batch) for batch in stub.batches] == [2, 1]
    assert vectors == [[0.0] * 4, [1.0] * 4, [0.0] * 4]


def test_hf_embedder_applies_the_passage_prefix() -> None:
    stub = _StubInferenceClient()

    _hf_embedder(stub, passage_prefix="passage: ").embed(["chapter one"])

    assert stub.batches == [["passage: chapter one"]]


def test_hf_embedder_sends_no_prefix_by_default() -> None:
    stub = _StubInferenceClient()

    _hf_embedder(stub).embed(["chapter one"])

    assert stub.batches == [["chapter one"]]


def test_hf_embedder_rejects_vectors_the_column_cannot_hold() -> None:
    # The model answers 1024-wide while the column holds 1536: the failure the
    # build-time guard cannot see, because only the model knows its width.
    stub = _StubInferenceClient(dimensions=1024)
    embedder = _hf_embedder(stub, dimensions=1536, batch_size=1)

    with pytest.raises(ValueError, match="1024-dimensional"):
        embedder.embed(["a", "b", "c"])

    # Failed on the first batch, not after embedding the whole document.
    assert len(stub.batches) == 1


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 422])
def test_hf_embedder_does_not_retry_a_fatal_status(status: int, no_hf_retry_wait: None) -> None:
    stub = _StubInferenceClient(errors=[_hf_http_error(status) for _ in range(MAX_ATTEMPTS)])

    with pytest.raises(HfHubHTTPError):
        _hf_embedder(stub).embed(["a"])

    assert len(stub.batches) == 1


def test_hf_embedder_retries_a_transient_failure(no_hf_retry_wait: None) -> None:
    stub = _StubInferenceClient(errors=[_hf_http_error(503), httpx.ConnectError("boom")])

    vectors = _hf_embedder(stub).embed(["a"])

    assert len(stub.batches) == 3
    assert vectors == [[0.0] * 4]


def test_build_embedder_refuses_a_dimension_the_column_cannot_hold() -> None:
    settings = Settings(
        embedding_provider="huggingface", embedding_dimensions=1024, hf_token="hf_x"
    )

    with pytest.raises(ValueError, match="chunks.embedding column"):
        build_embedder(settings)


def test_build_embedder_falls_back_to_the_fake_without_an_hf_token() -> None:
    settings = Settings(embedding_provider="huggingface", hf_token=None, llm_api_key=None)

    assert isinstance(build_embedder(settings), FakeEmbedder)
