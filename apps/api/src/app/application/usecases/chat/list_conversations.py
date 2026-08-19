"""List conversations for a document."""

from uuid import UUID

from app.domain.entities import Conversation
from app.domain.ports.unit_of_work import UnitOfWorkFactory


class ListConversations:
    """Use case: list all conversations for a document."""

    def __init__(self, uow_factory: UnitOfWorkFactory):
        self.uow_factory = uow_factory

    async def execute(self, document_id: UUID) -> list[Conversation] | None:
        """List conversations, or None if document doesn't exist."""
        async with self.uow_factory() as uow:
            # Verify document exists
            document = await uow.documents.get(document_id)
            if document is None:
                return None

            # List conversations
            return await uow.conversations.list_for_document(document_id)
