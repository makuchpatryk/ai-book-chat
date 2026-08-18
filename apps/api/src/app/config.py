"""Re-export from new location for backwards compatibility during Step 1."""

from app.infrastructure.config.settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]
