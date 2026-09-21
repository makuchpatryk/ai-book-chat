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


# 3 h: CPU-only embedding runs ~2.5 s per chunk, so a big book takes well over 30 min.
@shared_task(
    name="app.interfaces.worker.tasks.process_document", acks_late=True, time_limit=3 * 3600
)
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


@shared_task(name="app.interfaces.worker.tasks.generate_overview", acks_late=True, time_limit=300)
def generate_overview(document_id: str) -> bool:
    """Generate document overview. Never raises — status is persisted."""
    return asyncio.run(_generate_overview(UUID(document_id)))


async def _generate_overview(document_id: UUID) -> bool:
    """Async overview generation entrypoint."""
    from app.interfaces.worker.composition import get_generate_overview

    use_case = get_generate_overview()

    try:
        success = await use_case.execute(document_id)
        outcome = "success" if success else "failed"
        logger.info(f"document {document_id} overview generation: {outcome}")
        return success
    except Exception as e:
        logger.exception(f"document {document_id} overview generation error: {e}")
        return False
