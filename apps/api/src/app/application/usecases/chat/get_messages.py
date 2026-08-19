"""Get all messages in a conversation."""

from uuid import UUID

from app.domain.entities import Message
from app.domain.ports.unit_of_work import UnitOfWorkFactory


class GetMessages:
    """Use case: get all messages in a conversation."""

    def __init__(self, uow_factory: UnitOfWorkFactory):
        self.uow_factory = uow_factory

    async def execute(self, conversation_id: UUID) -> list[Message] | None:
        """Get messages, or None if conversation doesn't exist."""
        async with self.uow_factory() as uow:
            # Verify conversation exists
            conversation = await uow.conversations.get(conversation_id)
            if conversation is None:
                return None

            # Get messages with citations
            return await uow.messages.list_with_citations(conversation_id)
