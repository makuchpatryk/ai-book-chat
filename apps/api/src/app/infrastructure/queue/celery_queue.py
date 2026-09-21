"""Celery-based ingestion queue adapter."""

from uuid import UUID

from app.domain.ports.storage import IngestionQueue
from app.interfaces.worker.tasks import generate_overview, process_document


class CeleryIngestionQueue(IngestionQueue):
    """Celery-based implementation of IngestionQueue."""

    async def enqueue(self, document_id: UUID) -> None:
        """Enqueue a document for ingestion via Celery."""
        process_document.delay(str(document_id))

    async def enqueue_overview(self, document_id: UUID) -> None:
        """Enqueue overview generation via Celery."""
        generate_overview.delay(str(document_id))
