"""FastAPI application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import api_router
from app.config import get_settings
from app.infrastructure.db.session import engine
from app.logging import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(settings.log_level)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    logger.info("api starting", extra={"upload_dir": str(settings.upload_dir)})
    logger.debug("database target", extra={"database_url": settings.database_url})
    yield
    await engine.dispose()
    logger.info("api stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="PDF RAG Chat API", version="0.1.0", lifespan=lifespan)

    # The Vite dev server proxies /api, so CORS only matters when the frontend
    # is pointed straight at :8000.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)
    return app


app = create_app()
