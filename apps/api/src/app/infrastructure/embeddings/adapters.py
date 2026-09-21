"""Embedding adapter implementations."""

import httpx

from app.domain.ports.llm import Embedder
from app.infrastructure.config.settings import Settings

SECONDS_PER_TEXT = 30.0


class OllamaEmbedder(Embedder):
    """Ollama-based async embedder."""

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url
        self.model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts using Ollama, in one request."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": texts},
                # CPU-only Ollama needs seconds per text; scale with the batch.
                timeout=SECONDS_PER_TEXT * max(1, len(texts)),
            )
            response.raise_for_status()
            embeddings: list[list[float]] = response.json()["embeddings"]
            return embeddings


class FakeEmbedder(Embedder):
    """Fake embedder for testing (returns zeros)."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return zero vectors."""
        return [[0.0] * 768 for _ in texts]


def build_embedder(settings: Settings) -> Embedder:
    """Build embedder based on settings."""
    try:
        return OllamaEmbedder(settings.ollama_base_url, settings.ollama_embedding_model)
    except Exception:
        return FakeEmbedder()
