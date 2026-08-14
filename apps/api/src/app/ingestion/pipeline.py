"""The ingestion status machine — the only module here that touches the database.

PENDING -> PARSING -> EMBEDDING -> READY, or FAILED with a readable reason.
Nothing is written until the embeddings come back, so the usual failure modes
commit nothing; the failure handler still deletes explicitly, because a retry
(Phase 6) must never find half a document.
"""

import logging
import time
import uuid
from pathlib import Path

from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Chunk, Document, DocumentStatus, Section
from app.ingestion.chunking import ChunkSpec, chunk_document
from app.ingestion.embeddings import Embedder
from app.ingestion.extract import EmptyDocumentError, extract_pdf
from app.ingestion.sections import SectionSpec, detect_sections

logger = logging.getLogger(__name__)

ERROR_MESSAGE_MAX_CHARS = 1000


class DocumentNotFoundError(LookupError):
    """The row disappeared between enqueue and execution."""


def process_document(session: Session, document_id: uuid.UUID, embedder: Embedder) -> str:
    """Run the pipeline for one document; returns its final status.

    Failures are recorded on the document rather than raised: the row is the
    record of truth the API reads, and a raised exception would only make Celery
    redeliver a task that will fail identically.
    """
    document = session.get(Document, document_id)
    if document is None:
        raise DocumentNotFoundError(f"document {document_id} does not exist")

    settings = get_settings()
    started = time.monotonic()

    try:
        _set_status(session, document, DocumentStatus.PARSING)

        parse_started = time.monotonic()
        extracted = extract_pdf(Path(document.file_path))
        sections, strategy = detect_sections(extracted)
        parse_seconds = time.monotonic() - parse_started

        chunk_started = time.monotonic()
        chunks = chunk_document(
            extracted.pages,
            sections,
            size=settings.chunk_target_tokens,
            overlap_ratio=settings.chunk_overlap_ratio,
        )
        chunk_seconds = time.monotonic() - chunk_started
        if not chunks:
            raise EmptyDocumentError("no chunks could be built from the extracted text")

        total_tokens = sum(chunk.token_count for chunk in chunks)
        logger.info(
            "document parsed",
            extra={
                "document_id": str(document_id),
                "page_count": extracted.page_count,
                "strategy": strategy.value,
                "section_count": len(sections),
                "chunk_count": len(chunks),
                "total_tokens": total_tokens,
                "parse_seconds": round(parse_seconds, 2),
                "chunk_seconds": round(chunk_seconds, 2),
            },
        )

        _set_status(session, document, DocumentStatus.EMBEDDING)

        embed_started = time.monotonic()
        vectors = embedder.embed([chunk.content for chunk in chunks])
        embed_seconds = time.monotonic() - embed_started
        if len(vectors) != len(chunks):
            raise ValueError(f"embedder returned {len(vectors)} vectors for {len(chunks)} chunks")

        _persist(session, document, sections, chunks, vectors)

        document.title = extracted.title
        document.page_count = extracted.page_count
        document.chunking_strategy = strategy.value
        document.status = DocumentStatus.READY
        document.error_message = None
        session.commit()

        logger.info(
            "document ready",
            extra={
                "document_id": str(document_id),
                "embed_seconds": round(embed_seconds, 2),
                "total_seconds": round(time.monotonic() - started, 2),
            },
        )
        return DocumentStatus.READY.value

    except Exception as exc:
        logger.exception("document processing failed", extra={"document_id": str(document_id)})
        _fail(session, document_id, exc)
        return DocumentStatus.FAILED.value


def _set_status(session: Session, document: Document, status: DocumentStatus) -> None:
    document.status = status
    session.commit()


def _persist(
    session: Session,
    document: Document,
    sections: list[SectionSpec],
    chunks: list[ChunkSpec],
    vectors: list[list[float]],
) -> None:
    """Insert sections and chunks in one transaction, ids generated up front."""
    section_ids = {section.order_index: uuid.uuid4() for section in sections}

    session.execute(
        insert(Section),
        [
            {
                "id": section_ids[section.order_index],
                "document_id": document.id,
                "title": section.title,
                "order_index": section.order_index,
                "start_page": section.start_page,
                "end_page": section.end_page,
            }
            for section in sections
        ],
    )
    session.execute(
        insert(Chunk),
        [
            {
                "id": uuid.uuid4(),
                "document_id": document.id,
                "section_id": section_ids[chunk.section_order_index],
                "content": chunk.content,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "token_count": chunk.token_count,
                "order_index": chunk.order_index,
                "embedding": vector,
            }
            for chunk, vector in zip(chunks, vectors, strict=True)
        ],
    )


def _fail(session: Session, document_id: uuid.UUID, exc: Exception) -> None:
    """Roll back, then record the failure and remove anything already written."""
    session.rollback()

    document = session.get(Document, document_id)
    if document is None:
        return

    session.execute(delete(Chunk).where(Chunk.document_id == document_id))
    session.execute(delete(Section).where(Section.document_id == document_id))
    document.status = DocumentStatus.FAILED
    document.error_message = f"{type(exc).__name__}: {exc}"[:ERROR_MESSAGE_MAX_CHARS]
    session.commit()
