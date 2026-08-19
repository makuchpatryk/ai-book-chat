"""Celery-based ingestion queue adapter."""

from uuid import UUID

from app.domain.ports.storage import IngestionQueue
from app.interfaces.worker.tasks import process_document


class CeleryIngestionQueue(IngestionQueue):
    """Celery-based implementation of IngestionQueue."""

    async def enqueue(self, document_id: UUID) -> None:
        """Enqueue a document for ingestion via Celery."""
        process_document.delay(str(document_id))
