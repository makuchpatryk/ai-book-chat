"""Ports for data persistence."""

from typing import Protocol
from uuid import UUID

from app.domain.entities import Chunk, Conversation, Document, Message, Section
from app.domain.values.messages import Turn
from app.domain.values.retrieval import RetrievedChunk


class DocumentRepository(Protocol):
    """Persistence port for documents."""

    async def get(self, document_id: UUID) -> Document | None:
        """Get document by ID."""
        ...

    async def get_with_sections(self, document_id: UUID) -> tuple[Document, list[Section]] | None:
        """Get document with its sections."""
        ...

    async def find_by_hash(self, content_hash: str) -> Document | None:
        """Find document by content hash."""
        ...

    async def list_newest_first(self) -> list[Document]:
        """List all documents, newest first."""
        ...

    async def add(self, document: Document) -> None:
        """Add a new document."""
        ...

    async def save(self, document: Document) -> None:
        """Persist changes to a document."""
        ...

    async def delete(self, document_id: UUID) -> bool:
        """Delete document by ID. Returns True if deleted."""
        ...

    async def clear_derived(self, document_id: UUID) -> None:
        """Delete all sections and chunks for a document."""
        ...


class SectionRepository(Protocol):
    """Persistence port for sections."""

    async def add(self, section: Section) -> None:
        """Add a new section."""
        ...

    async def add_many(self, sections: list[Section]) -> None:
        """Add multiple sections."""
        ...


class ChunkRepository(Protocol):
    """Persistence port for chunks."""

    async def search_similar(
        self, document_id: UUID, vector: list[float], limit: int
    ) -> list[RetrievedChunk]:
        """Search for similar chunks by vector."""
        ...

    async def replace_for_document(
        self,
        document_id: UUID,
        sections: list[Section],
        chunks: list[Chunk],
    ) -> None:
        """Replace all sections and chunks for a document."""
        ...

    async def add_many(self, chunks: list[Chunk]) -> None:
        """Add multiple chunks."""
        ...


class ConversationRepository(Protocol):
    """Persistence port for conversations."""

    async def get(self, conversation_id: UUID) -> Conversation | None:
        """Get conversation by ID."""
        ...

    async def list_for_document(self, document_id: UUID) -> list[Conversation]:
        """List all conversations for a document."""
        ...

    async def add(self, conversation: Conversation) -> None:
        """Add a new conversation."""
        ...

    async def delete(self, conversation_id: UUID) -> bool:
        """Delete conversation by ID. Returns True if deleted."""
        ...


class MessageRepository(Protocol):
    """Persistence port for messages."""

    async def recent_turns(self, conversation_id: UUID, limit: int) -> list[Turn]:
        """Get recent message turns (role, content) for a conversation."""
        ...

    async def next_order_index(self, conversation_id: UUID) -> int:
        """Get the next order_index for a message in a conversation."""
        ...

    async def list_with_citations(self, conversation_id: UUID) -> list[Message]:
        """List all messages in a conversation with their citations."""
        ...

    async def add(self, message: Message) -> None:
        """Add a new message."""
        ...

    async def save(self, message: Message) -> None:
        """Persist changes to a message."""
        ...
