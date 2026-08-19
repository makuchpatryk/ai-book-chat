"""Upload a document."""

from collections.abc import AsyncIterator
from uuid import uuid4

from app.domain.entities import Document
from app.domain.errors import DuplicateUpload, FileTooLarge, NotAPdf, UnsupportedFileType
from app.domain.ports.storage import FileStorage, IngestionQueue
from app.domain.ports.unit_of_work import UnitOfWorkFactory
from app.domain.values.status import DocumentStatus


class UploadDocument:
    """Use case: upload and enqueue a document for ingestion."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        file_storage: FileStorage,
        queue: IngestionQueue,
        max_upload_mb: int,
    ):
        self.uow_factory = uow_factory
        self.file_storage = file_storage
        self.queue = queue
        self.max_upload_mb = max_upload_mb

    async def execute(
        self, filename: str, content_hash: str, chunks: AsyncIterator[bytes]
    ) -> Document | None:
        """Upload document, checking for duplicates and re-enqueuing failed ones."""
        # Validate filename
        if not filename.lower().endswith(".pdf"):
            raise UnsupportedFileType()

        async with self.uow_factory() as uow:
            # Check for duplicate by hash
            existing = await uow.documents.find_by_hash(content_hash)

            if existing:
                if existing.status == DocumentStatus.FAILED:
                    # Re-enqueue a FAILED duplicate
                    await self.queue.enqueue(existing.id)
                    return existing
                else:
                    # Already processed or processing
                    raise DuplicateUpload()

            # Create new document
            doc_id = uuid4()
            key = f"{doc_id}.pdf"

            # Save file (this validates size and magic bytes)
            try:
                stored_file = await self.file_storage.save(
                    key, chunks, self.max_upload_mb * 1024 * 1024
                )
            except ValueError as e:
                if "exceeds" in str(e):
                    raise FileTooLarge(self.max_upload_mb)
                raise

            # Validate PDF magic bytes
            if not stored_file.sha256:  # placeholder validation
                raise NotAPdf()

            # Create document entity
            document = Document(
                id=doc_id,
                filename=filename,
                title=filename,  # temp title, updated after parsing
                status=DocumentStatus.PENDING,
                file_path=stored_file.path,
                content_hash=content_hash,
                page_count=None,
                error_message=None,
            )

            # Persist and enqueue
            await uow.documents.add(document)
            await uow.commit()
            await self.queue.enqueue(document.id)

            return document
