"""Delete a conversation."""

from uuid import UUID

from app.domain.ports.unit_of_work import UnitOfWorkFactory


class DeleteConversation:
    """Use case: delete a conversation."""

    def __init__(self, uow_factory: UnitOfWorkFactory):
        self.uow_factory = uow_factory

    async def execute(self, conversation_id: UUID) -> bool:
        """Delete conversation. Returns True if deleted, False if not found."""
        async with self.uow_factory() as uow:
            success = await uow.conversations.delete(conversation_id)
            if success:
                await uow.commit()
            return success
