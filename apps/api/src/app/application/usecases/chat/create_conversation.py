"""Create a new conversation."""

from datetime import datetime
from uuid import UUID, uuid4

from app.domain.entities import Conversation
from app.domain.ports.unit_of_work import UnitOfWorkFactory


class CreateConversation:
    """Use case: create a new conversation for a document."""

    def __init__(self, uow_factory: UnitOfWorkFactory):
        self.uow_factory = uow_factory

    async def execute(self, document_id: UUID) -> Conversation | None:
        """Create and return a new conversation."""
        async with self.uow_factory() as uow:
            # Verify document exists
            document = await uow.documents.get(document_id)
            if document is None:
                return None

            # Create conversation
            conversation = Conversation(
                id=uuid4(),
                document_id=document_id,
                title=None,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

            await uow.conversations.add(conversation)
            await uow.commit()

            return conversation
