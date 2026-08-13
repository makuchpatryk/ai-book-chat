"""Liveness/readiness endpoint — checks the API's two hard dependencies."""

import logging
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import DbSession, RedisClient

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

Status = Literal["ok", "error"]


class HealthResponse(BaseModel):
    status: Status
    database: Status
    redis: Status


@router.get("/health", response_model=HealthResponse)
async def health(response: Response, db: DbSession, redis: RedisClient) -> HealthResponse:
    database: Status = "ok"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("health check: database unreachable")
        database = "error"

    redis_status: Status = "ok"
    try:
        await redis.ping()
    except Exception:
        logger.exception("health check: redis unreachable")
        redis_status = "error"

    overall: Status = "ok" if database == "ok" and redis_status == "ok" else "error"
    if overall == "error":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(status=overall, database=database, redis=redis_status)
