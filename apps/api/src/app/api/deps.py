"""Shared FastAPI dependencies."""

from collections.abc import AsyncIterator
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.session import get_session


async def get_redis() -> AsyncIterator[aioredis.Redis]:
    settings = get_settings()
    client: aioredis.Redis = aioredis.from_url(  # type: ignore[no-untyped-call]
        settings.redis_url, decode_responses=True
    )
    try:
        yield client
    finally:
        await client.aclose()


DbSession = Annotated[AsyncSession, Depends(get_session)]
RedisClient = Annotated[aioredis.Redis, Depends(get_redis)]
AppSettings = Annotated[Settings, Depends(get_settings)]
