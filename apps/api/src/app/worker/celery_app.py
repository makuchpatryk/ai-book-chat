"""Celery application — entrypoint for the worker process.

Run with: celery -A app.worker.celery_app worker -l info
"""

import logging
from typing import Any

from celery import Celery
from celery.signals import worker_process_init

from app.config import get_settings
from app.db.sync_session import sync_engine
from app.logging import setup_logging

logger = logging.getLogger(__name__)

settings = get_settings()

celery_app = Celery(
    "ai_book_chat",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    result_expires=3600,
    # Celery otherwise replaces sys.stdout with a proxy that logs through the
    # root logger — which is where our own StreamHandler writes, so every
    # in-task log line is swallowed by the recursion guard.
    worker_redirect_stdouts=False,
)

celery_app.autodiscover_tasks(["app.worker"])


@worker_process_init.connect
def init_worker_process(**_: Any) -> None:
    """Each forked child gets its own connections — never share a pool across forks."""
    setup_logging(settings.log_level)
    sync_engine.dispose()
    logger.info("celery worker process ready")
