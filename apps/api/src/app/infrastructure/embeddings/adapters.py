"""Embedding adapter implementations."""

import httpx

from app.domain.ports.llm import Embedder
from app.infrastructure.config.settings import Settings


class OllamaEmbedder(Embedder):
    """Ollama-based async embedder."""

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url
        self.model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts using Ollama."""
        async with httpx.AsyncClient() as client:
            embeddings = []
            for text in texts:
                response = await client.post(
                    f"{self.base_url}/api/embed",
                    json={"model": self.model, "input": text},
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
                embeddings.append(data["embeddings"][0])
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
