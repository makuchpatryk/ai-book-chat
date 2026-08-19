"""Get document detail with sections."""

from uuid import UUID

from app.domain.entities import Document, Section
from app.domain.ports.unit_of_work import UnitOfWorkFactory


class GetDocumentDetail:
    """Use case: get document with sections."""

    def __init__(self, uow_factory: UnitOfWorkFactory):
        self.uow_factory = uow_factory

    async def execute(self, document_id: UUID) -> tuple[Document, list[Section]] | None:
        """Get document and sections, or None if not found."""
        async with self.uow_factory() as uow:
            return await uow.documents.get_with_sections(document_id)
