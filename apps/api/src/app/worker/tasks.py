"""Celery tasks."""

import logging
from uuid import UUID

from celery import shared_task

from app.db.sync_session import session_scope
from app.ingestion.embeddings import build_embedder
from app.ingestion.pipeline import process_document as run_pipeline

logger = logging.getLogger(__name__)


@shared_task(name="app.worker.tasks.ping")
def ping() -> str:
    """Round-trip check: API can enqueue, worker executes, result comes back."""
    logger.info("ping task executed")
    return "pong"


@shared_task(name="app.worker.tasks.process_document", acks_late=True, time_limit=1800)
def process_document(document_id: str) -> str:
    """Ingest an uploaded PDF. Returns the document's final status."""
    with session_scope() as session:
        return run_pipeline(session, UUID(document_id), build_embedder())
