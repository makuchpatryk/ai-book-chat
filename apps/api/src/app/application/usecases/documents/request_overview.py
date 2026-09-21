"""Use case: request overview generation for a document."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.domain.errors import DocumentNotFound, DocumentNotReady, OverviewAlreadyPending
from app.domain.ports.storage import Clock, IngestionQueue
from app.domain.ports.unit_of_work import UnitOfWorkFactory
from app.domain.values.overview import OverviewStatus
from app.domain.values.status import DocumentStatus

logger = logging.getLogger(__name__)

# If overview is pending and older than this, allow re-request
PENDING_TIMEOUT = timedelta(minutes=10)


def _as_naive_utc(value: datetime) -> datetime:
    """The DB hands back aware datetimes; the clock hands out naive UTC."""
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


class RequestOverview:
    """Use case: request overview generation, with dedup for recent pending."""

    def __init__(self, uow_factory: UnitOfWorkFactory, queue: IngestionQueue, clock: Clock):
        self.uow_factory = uow_factory
        self.queue = queue
        self.clock = clock

    async def execute(self, document_id: UUID) -> None:
        """Request overview generation. Raises if doc not found/ready or already pending."""
        async with self.uow_factory() as uow:
            document = await uow.documents.get(document_id)
            if document is None:
                raise DocumentNotFound()

            if document.status != DocumentStatus.READY:
                raise DocumentNotReady(activity="overview generation")

            now = self.clock.now()
            fresh = now - _as_naive_utc(document.updated_at) < PENDING_TIMEOUT
            if document.overview_status == OverviewStatus.PENDING and fresh:
                raise OverviewAlreadyPending()

            document.mark_overview_pending(now)
            await uow.documents.save(document)
            await uow.commit()

        try:
            await self.queue.enqueue_overview(document_id)
        except Exception as e:
            logger.error(f"failed to enqueue overview for {document_id}: {e}")
