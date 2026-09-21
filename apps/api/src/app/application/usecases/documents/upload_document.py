"""Upload a document."""

from collections.abc import AsyncIterator
from uuid import uuid4

from app.domain.entities import Document
from app.domain.errors import DuplicateUpload, FileTooLarge, NotAPdf, UnsupportedFileType
from app.domain.ports.storage import FileStorage, IngestionQueue
from app.domain.ports.unit_of_work import UnitOfWorkFactory
from app.domain.values.status import DocumentStatus

PDF_MAGIC = b"%PDF-"


async def _require_pdf_header(chunks: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    """Pass chunks through, raising NotAPdf unless the stream starts with %PDF-."""
    head = b""
    async for chunk in chunks:
        if len(head) < len(PDF_MAGIC):
            head += chunk[: len(PDF_MAGIC) - len(head)]
            if len(head) >= len(PDF_MAGIC) and head != PDF_MAGIC:
                raise NotAPdf()
        yield chunk
    if head != PDF_MAGIC:
        raise NotAPdf()


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

    async def execute(self, filename: str, chunks: AsyncIterator[bytes]) -> Document | None:
        """Upload document, checking for duplicates and re-enqueuing failed ones."""
        # Validate filename
        if not filename.lower().endswith(".pdf"):
            raise UnsupportedFileType()

        # Stream straight to storage: size limit and hash are enforced while
        # writing, so the upload is never held in memory.
        doc_id = uuid4()
        key = f"{doc_id}.pdf"
        try:
            stored_file = await self.file_storage.save(
                key, _require_pdf_header(chunks), self.max_upload_mb * 1024 * 1024
            )
        except ValueError as e:
            if "exceeds" in str(e):
                raise FileTooLarge(self.max_upload_mb)
            raise

        async with self.uow_factory() as uow:
            # Check for duplicate by hash
            existing = await uow.documents.find_by_hash(stored_file.sha256)

            if existing:
                await self.file_storage.delete(key)
                if existing.status == DocumentStatus.FAILED:
                    # Re-enqueue a FAILED duplicate
                    await self.queue.enqueue(existing.id)
                    return existing
                else:
                    # Already processed or processing
                    raise DuplicateUpload()

            # Create document entity
            document = Document(
                id=doc_id,
                filename=filename,
                title=filename,  # temp title, updated after parsing
                status=DocumentStatus.PENDING,
                file_path=stored_file.path,
                content_hash=stored_file.sha256,
                page_count=None,
                error_message=None,
            )

            # Persist and enqueue
            await uow.documents.add(document)
            await uow.commit()
            await self.queue.enqueue(document.id)

            return document
