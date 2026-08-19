"""Ports for external storage and services."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import NamedTuple, Protocol
from uuid import UUID


class OutlineEntry(NamedTuple):
    """PDF outline entry."""
    level: int
    title: str
    page_number: int


class TextLine(NamedTuple):
    """Text line with font metrics."""
    page_number: int
    text: str
    font_size: float
    span_count: int


class PageText(NamedTuple):
    """Text content from a page."""
    page_number: int
    text: str


@dataclass(frozen=True)
class ExtractedPdf:
    """Result of extracting a PDF."""
    page_count: int
    title: str
    pages: list[PageText]
    lines: list[TextLine]
    outline: list[OutlineEntry]


@dataclass
class StoredFile:
    """Result of storing a file."""

    path: str
    sha256: str
    size: int


class FileStorage(Protocol):
    """Port for storing and retrieving uploaded files."""

    async def save(self, key: str, chunks: AsyncIterator[bytes], max_bytes: int) -> StoredFile:
        """Save file chunks. Raises if size exceeds max_bytes."""
        ...

    async def delete(self, key: str) -> None:
        """Delete a stored file."""
        ...

    async def exists(self, key: str) -> bool:
        """Check if a file exists."""
        ...


class IngestionQueue(Protocol):
    """Port for queueing document ingestion tasks."""

    async def enqueue(self, document_id: UUID) -> None:
        """Enqueue a document for ingestion."""
        ...


class PdfExtractor(Protocol):
    """Port for extracting text from PDFs."""

    def extract(self, file_path: str, fallback_title: str | None = None) -> ExtractedPdf:
        """Extract PDF metadata, text, outline, and line metrics."""
        ...


class TokenCounter(Protocol):
    """Port for counting tokens in text."""

    def encode(self, text: str) -> list[int]:
        """Encode text into tokens."""
        ...

    def decode(self, tokens: list[int]) -> str:
        """Decode tokens back to text."""
        ...

    def count(self, text: str) -> int:
        """Count tokens in text."""
        ...


class Clock(Protocol):
    """Port for getting current time."""

    def now(self) -> datetime:
        """Get current datetime."""
        ...
