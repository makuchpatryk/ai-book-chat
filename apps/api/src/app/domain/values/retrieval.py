"""Retrieval-related value objects."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Citation:
    """A source citation for an answer."""

    chunk_id: UUID
    page_start: int
    page_end: int
    score: int | None
    section_title: str | None
    snippet: str


@dataclass(frozen=True)
class RetrievedChunk:
    """A chunk returned from vector search."""

    chunk_id: UUID
    distance: float
    content: str
    page_start: int
    page_end: int
    section_title: str | None


@dataclass(frozen=True)
class ScoredChunk:
    """A chunk with a re-rank score."""

    chunk: RetrievedChunk
    score: int | None
