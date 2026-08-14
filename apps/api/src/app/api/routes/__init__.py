from fastapi import APIRouter

from app.api.routes import conversations, documents, health, search

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(documents.router)
api_router.include_router(search.router)
api_router.include_router(conversations.router)

__all__ = ["api_router"]
