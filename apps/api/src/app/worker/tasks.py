"""Celery tasks.

Phase 1 ships only a connectivity smoke task; ingestion tasks land in Phase 2.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="app.worker.tasks.ping")
def ping() -> str:
    """Round-trip check: API can enqueue, worker executes, result comes back."""
    logger.info("ping task executed")
    return "pong"
