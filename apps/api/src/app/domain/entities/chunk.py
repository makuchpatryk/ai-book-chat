"""Chunk entity — a piece of a document."""

from dataclasses import dataclass
from uuid import UUID


@dataclass
class Chunk:
    """A text chunk extracted from a document section."""

    id: UUID
    document_id: UUID
    section_id: UUID
    content: str
    page_start: int
    page_end: int
    token_count: int
    order_index: int
