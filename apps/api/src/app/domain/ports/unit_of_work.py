"""Port for transactional unit of work."""

from typing import Protocol

from app.domain.ports.repositories import (
    ChunkRepository,
    ConversationRepository,
    DocumentRepository,
    MessageRepository,
    SectionRepository,
)


class UnitOfWork(Protocol):
    """Transactional boundary owned by use cases."""

    documents: DocumentRepository
    sections: SectionRepository
    chunks: ChunkRepository
    conversations: ConversationRepository
    messages: MessageRepository

    async def __aenter__(self) -> "UnitOfWork":
        """Enter async context."""
        ...

    async def __aexit__(self, *exc: object) -> None:
        """Exit async context, rolling back unless committed."""
        ...

    async def commit(self) -> None:
        """Commit the transaction."""
        ...

    async def rollback(self) -> None:
        """Rollback the transaction."""
        ...


class UnitOfWorkFactory(Protocol):
    """Factory for creating unit of work instances."""

    def __call__(self) -> UnitOfWork:
        """Create a new UnitOfWork instance."""
        ...
