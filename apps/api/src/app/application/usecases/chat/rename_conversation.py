"""Rename a conversation."""

from uuid import UUID

from app.domain.entities import Conversation
from app.domain.ports.unit_of_work import UnitOfWorkFactory


class RenameConversation:
    """Use case: set a user-chosen title on a conversation."""

    def __init__(self, uow_factory: UnitOfWorkFactory):
        self.uow_factory = uow_factory

    async def execute(self, conversation_id: UUID, title: str) -> Conversation | None:
        """Rename conversation. Returns None if not found."""
        async with self.uow_factory() as uow:
            conversation = await uow.conversations.rename(conversation_id, title)
            if conversation is not None:
                await uow.commit()
            return conversation
