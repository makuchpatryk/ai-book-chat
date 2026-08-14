"""Opt-in check against the real OpenAI API: `uv run pytest -m live`.

Excluded from the default run (see `addopts` in pyproject.toml) so the suite
stays offline and free.
"""

import pytest

from app.config import get_settings
from app.ingestion.embeddings import OpenAIEmbedder, build_embedder

pytestmark = pytest.mark.live


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


@pytest.fixture
def embedder() -> OpenAIEmbedder:
    if not get_settings().openai_api_key:
        pytest.skip("OPENAI_API_KEY not set")
    built = build_embedder()
    assert isinstance(built, OpenAIEmbedder)
    return built


def test_real_embeddings_have_the_expected_shape_and_semantics(embedder: OpenAIEmbedder) -> None:
    settings = get_settings()
    reference, near, unrelated = embedder.embed(
        [
            "The mitochondrion is the powerhouse of the cell.",
            "Mitochondria generate most of the cell's chemical energy.",
            "The 1974 World Cup final was played in Munich.",
        ]
    )

    assert len(reference) == settings.embedding_dimensions
    # Returned vectors are unit-length, so the dot product is the cosine.
    assert _cosine(reference, near) > _cosine(reference, unrelated)
