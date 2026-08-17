"""Opt-in check against a real local Ollama: `uv run pytest -m live`.

Excluded from the default run (see `addopts` in pyproject.toml) so the suite
stays offline and needs no running Ollama.
"""

import httpx
import pytest

from app.config import get_settings
from app.ingestion.embeddings import OllamaEmbedder, build_embedder

pytestmark = pytest.mark.live


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norms = sum(a * a for a in left) ** 0.5 * sum(b * b for b in right) ** 0.5
    return dot / norms


@pytest.fixture
def embedder() -> OllamaEmbedder:
    settings = get_settings()
    try:
        httpx.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags", timeout=2.0)
    except httpx.HTTPError:
        pytest.skip(f"ollama unreachable at {settings.ollama_base_url}")
    built = build_embedder()
    assert isinstance(built, OllamaEmbedder)
    return built


def test_real_embeddings_have_the_expected_shape_and_semantics(embedder: OllamaEmbedder) -> None:
    settings = get_settings()
    reference, near, unrelated = embedder.embed(
        [
            "The mitochondrion is the powerhouse of the cell.",
            "Mitochondria generate most of the cell's chemical energy.",
            "The 1974 World Cup final was played in Munich.",
        ]
    )

    assert len(reference) == settings.embedding_dimensions
    assert _cosine(reference, near) > _cosine(reference, unrelated)
