"""Section entity — a logical division within a document."""

from dataclasses import dataclass
from uuid import UUID


@dataclass
class Section:
    """A section of a document (extracted from outline or detected via headings)."""

    id: UUID
    document_id: UUID
    title: str
    order_index: int
    start_page: int
    end_page: int
