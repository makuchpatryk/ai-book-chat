from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient

from app.db.session import get_session


async def test_health_ok(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "redis": "ok"}


async def test_health_db_down(app: FastAPI, client: AsyncClient) -> None:
    class BrokenSession:
        async def execute(self, *args: Any, **kwargs: Any) -> Any:
            raise ConnectionError("simulated database outage")

    async def broken_session() -> AsyncIterator[Any]:
        yield BrokenSession()

    app.dependency_overrides[get_session] = broken_session
    try:
        response = await client.get("/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert body["database"] == "error"
    assert body["redis"] == "ok"
