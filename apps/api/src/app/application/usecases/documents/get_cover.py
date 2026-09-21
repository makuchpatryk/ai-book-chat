"""Use case: retrieve document cover image."""

from uuid import UUID

from app.domain.errors import CoverNotFound, DocumentNotFound
from app.domain.ports.unit_of_work import UnitOfWorkFactory


class GetCover:
    """Use case: get document cover image."""

    def __init__(self, uow_factory: UnitOfWorkFactory):
        self.uow_factory = uow_factory

    async def execute(self, document_id: UUID) -> tuple[bytes, str]:
        """Get cover image and MIME type. Raises CoverNotFound if none."""
        async with self.uow_factory() as uow:
            document = await uow.documents.get(document_id)
            if document is None:
                raise DocumentNotFound()

            cover = await uow.documents.get_cover(document_id)
            if cover is None:
                raise CoverNotFound()

            return cover
