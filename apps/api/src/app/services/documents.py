"""Upload handling and document reads.

The upload path streams to disk while hashing, so a 50 MB cap costs 50 MB of
disk and never 50 MB of memory. Processing itself happens in the Celery task —
the response returns as soon as the row exists.
"""

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.db.models import Chunk, Document, DocumentStatus, Section
from app.worker.tasks import process_document

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"
READ_CHUNK_BYTES = 1024 * 1024


async def create_document(
    session: AsyncSession, upload: UploadFile, settings: Settings
) -> tuple[Document, bool]:
    """Store an upload and enqueue processing.

    Returns the document and whether it is new; an identical file (same SHA-256)
    returns the existing row instead of embedding the same book twice.
    """
    filename = upload.filename or "upload.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="only PDF files are supported",
        )

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    document_id = uuid4()
    path = settings.upload_dir / f"{document_id}.pdf"
    content_hash = await _save_and_hash(upload, path, settings.max_upload_mb)

    existing = await session.scalar(select(Document).where(Document.content_hash == content_hash))
    if existing is not None:
        path.unlink(missing_ok=True)
        if existing.status is DocumentStatus.FAILED:
            # Same bytes, previously broken: reuse the row so the id is stable
            # and give it another run rather than stacking up duplicates.
            existing.status = DocumentStatus.PENDING
            existing.error_message = None
            await session.commit()
            process_document.delay(str(existing.id))
        # NB: "filename" is a reserved LogRecord attribute — logging raises on it.
        logger.info(
            "duplicate upload", extra={"document_id": str(existing.id), "upload_filename": filename}
        )
        return existing, False

    document = Document(
        id=document_id,
        filename=filename,
        # Replaced with the PDF's metadata title once the worker has parsed it.
        title=Path(filename).stem,
        status=DocumentStatus.PENDING,
        file_path=str(path),
        content_hash=content_hash,
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)

    process_document.delay(str(document.id))
    logger.info(
        "document uploaded",
        extra={"document_id": str(document.id), "upload_filename": filename},
    )
    return document, True


async def _save_and_hash(upload: UploadFile, path: Path, max_upload_mb: int) -> str:
    """Stream the upload to `path`, returning its SHA-256.

    Aborts (and cleans up) on oversize input or a missing PDF header, so a bad
    upload never leaves a file behind.
    """
    max_bytes = max_upload_mb * 1024 * 1024
    digest = hashlib.sha256()
    written = 0
    header = b""

    try:
        with path.open("wb") as target:
            while chunk := await upload.read(READ_CHUNK_BYTES):
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"file exceeds the {max_upload_mb} MB limit",
                    )
                if len(header) < len(PDF_MAGIC):
                    header += chunk[: len(PDF_MAGIC) - len(header)]
                digest.update(chunk)
                target.write(chunk)

        if not header.startswith(PDF_MAGIC):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="file is not a valid PDF (missing %PDF- header)",
            )
    except Exception:
        path.unlink(missing_ok=True)
        raise

    return digest.hexdigest()


async def list_documents(session: AsyncSession) -> list[Document]:
    result = await session.scalars(select(Document).order_by(Document.created_at.desc()))
    return list(result)


async def get_document(session: AsyncSession, document_id: UUID) -> Document | None:
    """Fetch a document by ID. None if unknown."""
    return await session.scalar(select(Document).where(Document.id == document_id))


async def get_document_detail(
    session: AsyncSession, document_id: UUID
) -> tuple[Document, int] | None:
    """The document with its sections, plus its chunk count. None if unknown."""
    document = await session.scalar(
        select(Document).options(selectinload(Document.sections)).where(Document.id == document_id)
    )
    if document is None:
        return None

    chunk_count = await session.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.document_id == document_id)
    )
    return document, chunk_count or 0


async def delete_document(session: AsyncSession, document_id: UUID) -> bool:
    """Delete a document and cascade to chunks, sections, conversations, messages, and sources.

    Returns whether a row was removed. Unlinks the PDF file after commit.
    """
    document = await session.scalar(select(Document).where(Document.id == document_id))
    if document is None:
        return False

    file_path = document.file_path

    stmt = delete(Document).where(Document.id == document_id)
    await session.execute(stmt)
    await session.commit()

    try:
        Path(file_path).unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"failed to unlink {file_path}: {e}")

    return True


async def retry_document(session: AsyncSession, document_id: UUID, settings: Settings) -> Document:
    """Move a document back to PENDING and re-enqueue processing.

    Raises HTTPException with appropriate status codes for ineligible states:
    - READY: 409 "already processed"
    - PENDING|PARSING|EMBEDDING and recent: 409 "still processing"
    - PENDING|PARSING|EMBEDDING and stale: clears chunks/sections, resets to PENDING
    - FAILED: resets to PENDING
    - File missing: 409 "original file is gone"
    """
    document = await session.scalar(select(Document).where(Document.id == document_id))
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")

    if document.status == DocumentStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="document is already processed"
        )

    if document.status in (DocumentStatus.PENDING, DocumentStatus.PARSING, DocumentStatus.EMBEDDING):
        age_minutes = (datetime.now(timezone.utc) - document.updated_at).total_seconds() / 60
        if age_minutes < settings.stuck_after_minutes:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="document is still processing"
            )

    if not Path(document.file_path).exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="original file is missing; re-upload it",
        )

    await session.execute(delete(Chunk).where(Chunk.document_id == document_id))
    await session.execute(delete(Section).where(Section.document_id == document_id))

    document.status = DocumentStatus.PENDING
    document.error_message = None
    await session.commit()
    await session.refresh(document)

    process_document.delay(str(document.id))
    logger.info("document retry enqueued", extra={"document_id": str(document.id)})

    return document
