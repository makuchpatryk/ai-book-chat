from fastapi import APIRouter

from app.api.routes import documents, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(documents.router)

__all__ = ["api_router"]
