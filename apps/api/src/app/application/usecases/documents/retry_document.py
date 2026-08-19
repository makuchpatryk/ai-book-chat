"""Retry ingestion of a document."""

from datetime import timedelta
from uuid import UUID

from app.domain.entities import Document
from app.domain.errors import DocumentAlreadyProcessed, DocumentNotFound, DocumentStillProcessing
from app.domain.ports.storage import Clock, IngestionQueue
from app.domain.ports.unit_of_work import UnitOfWorkFactory


class RetryDocument:
    """Use case: retry ingestion of a failed or stuck document."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        queue: IngestionQueue,
        clock: Clock,
        stuck_after: timedelta,
    ):
        self.uow_factory = uow_factory
        self.queue = queue
        self.clock = clock
        self.stuck_after = stuck_after

    async def execute(self, document_id: UUID) -> Document:
        """Retry a document, or raise if not retryable."""
        async with self.uow_factory() as uow:
            document = await uow.documents.get(document_id)
            if document is None:
                raise DocumentNotFound()

            # Check if retryable
            now = self.clock.now()
            verdict = document.retry_eligibility(now, self.stuck_after)

            if not verdict.can_retry:
                if verdict.reason == "still_processing":
                    raise DocumentStillProcessing()
                elif verdict.reason == "already_processed":
                    raise DocumentAlreadyProcessed()
                else:
                    raise DocumentNotFound()

            # Enqueue for re-ingestion
            await self.queue.enqueue(document.id)

            # Save document state (queue enqueue is best-effort)
            await uow.documents.save(document)
            await uow.commit()

            return document
