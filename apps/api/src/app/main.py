"""Re-export from new interfaces.http location — Docker/uvicorn reference app.main:app."""

from app.interfaces.http.app import app, create_app

__all__ = ["app", "create_app"]
