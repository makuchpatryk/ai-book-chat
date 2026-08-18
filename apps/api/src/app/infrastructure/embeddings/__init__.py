"""Embedding infrastructure adapters."""

from app.infrastructure.embeddings.adapters import FakeEmbedder, OllamaEmbedder, build_embedder

__all__ = ["FakeEmbedder", "OllamaEmbedder", "build_embedder"]
