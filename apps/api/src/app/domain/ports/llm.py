"""Ports for LLM capabilities."""

from collections.abc import AsyncIterator
from typing import Protocol

from app.domain.values.messages import Turn
from app.domain.values.overview import DocumentOverview
from app.domain.values.quiz import QuizQuestion


class GenerationEvent(Protocol):
    """A single event from the answer generator."""

    pass


class AnswerGenerator(Protocol):
    """Port for generating answers via an LLM."""

    def stream(self, system: str, turns: list[Turn]) -> AsyncIterator[str]:
        """Stream generation tokens."""
        ...


class QueryRewriter(Protocol):
    """Port for rewriting user queries."""

    async def rewrite(self, question: str, history: list[Turn]) -> str:
        """Rewrite a question based on conversation history."""
        ...


class Reranker(Protocol):
    """Port for re-ranking retrieved passages."""

    async def score(self, query: str, passages: list[str]) -> list[int]:
        """Score passages for relevance to query."""
        ...


class Embedder(Protocol):
    """Port for embedding text into vectors."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts into vectors."""
        ...


class DocumentDescriber(Protocol):
    """Port for generating document descriptions."""

    async def describe(
        self,
        title: str,
        author: str | None,
        section_titles: list[str],
        sample_text: str,
    ) -> DocumentOverview:
        """Generate a document overview from sampled text."""
        ...


class QuizGenerator(Protocol):
    """Port for generating a multiple-choice quiz from a document's chunks."""

    async def generate(self, title: str, chunks: list[str]) -> list[QuizQuestion]:
        """Generate exactly 10 multiple-choice questions grounded in the given chunks."""
        ...
