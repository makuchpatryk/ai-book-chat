"""Celery tasks (async via asyncio.run)."""

import asyncio
import logging
from uuid import UUID

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="app.interfaces.worker.tasks.ping")
def ping() -> str:
    """Round-trip check: API can enqueue, worker executes, result comes back."""
    logger.info("ping task executed")
    return "pong"


@shared_task(name="app.interfaces.worker.tasks.process_document", acks_late=True, time_limit=1800)
def process_document(document_id: str) -> str:
    """Ingest an uploaded PDF. Returns the document's final status."""
    return asyncio.run(_ingest(UUID(document_id)))


async def _ingest(document_id: UUID) -> str:
    """Async ingestion entrypoint."""
    from app.interfaces.worker.composition import get_ingest_document

    use_case = get_ingest_document()

    try:
        document = await use_case.execute(document_id)
        logger.info(f"document {document_id} ingestion complete: {document.status}")
        return document.status.value
    except Exception as e:
        logger.exception(f"document {document_id} ingestion failed: {e}")
        raise
