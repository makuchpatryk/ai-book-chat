"""Sync database session layer — used by Celery tasks and Alembic.

Celery's prefork pool forks after the engine may already exist, so the engine is
disposed on worker process init (see `app.worker.celery_app`) to avoid sharing
connections across processes.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

settings = get_settings()

sync_engine = create_engine(settings.sync_database_url, pool_pre_ping=True)

SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for a unit of work inside a Celery task."""
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
