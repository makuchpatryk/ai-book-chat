"""Delete a document."""

import logging
from uuid import UUID

from app.domain.ports.storage import FileStorage
from app.domain.ports.unit_of_work import UnitOfWorkFactory

logger = logging.getLogger(__name__)


class DeleteDocument:
    """Use case: delete a document and its file."""

    def __init__(self, uow_factory: UnitOfWorkFactory, file_storage: FileStorage):
        self.uow_factory = uow_factory
        self.file_storage = file_storage

    async def execute(self, document_id: UUID) -> bool:
        """Delete document. Returns True if deleted, False if not found."""
        async with self.uow_factory() as uow:
            # Get document to get file path
            document = await uow.documents.get(document_id)
            if document is None:
                return False

            # Delete from DB
            success = await uow.documents.delete(document_id)
            if not success:
                return False

            await uow.commit()

            # Delete file (best-effort, don't fail if file missing)
            try:
                if document.file_path:
                    await self.file_storage.delete(document.file_path)
            except Exception as e:
                logger.warning(f"failed to delete file {document.file_path}: {e}")

            return True
