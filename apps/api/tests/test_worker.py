import pytest
import redis
from celery.exceptions import TimeoutError as CeleryTimeoutError

from app.config import get_settings
from app.worker.celery_app import celery_app
from app.worker.tasks import ping


def _broker_up() -> bool:
    try:
        redis.Redis.from_url(get_settings().celery_broker_url).ping()
    except Exception:
        return False
    return True


def test_ping_task_runs_locally() -> None:
    """The task body itself, no broker involved."""
    assert ping() == "pong"


def test_ping_task_round_trip() -> None:
    """Enqueue -> worker executes -> result comes back. Needs a running worker."""
    if not _broker_up():
        pytest.skip("redis broker unreachable")

    result = celery_app.send_task("app.worker.tasks.ping")
    try:
        assert result.get(timeout=10) == "pong"
    except CeleryTimeoutError:
        pytest.skip("no celery worker consuming the queue (docker compose up worker)")
    finally:
        result.forget()
