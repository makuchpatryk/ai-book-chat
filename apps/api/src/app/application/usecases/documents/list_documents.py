"""List all documents."""

from app.domain.entities import Document
from app.domain.ports.unit_of_work import UnitOfWorkFactory


class ListDocuments:
    """Use case: list all documents."""

    def __init__(self, uow_factory: UnitOfWorkFactory):
        self.uow_factory = uow_factory

    async def execute(self) -> list[Document]:
        """List all documents, newest first."""
        async with self.uow_factory() as uow:
            return await uow.documents.list_newest_first()
