"""Clock adapter for getting current time."""

from datetime import datetime

from app.domain.ports.storage import Clock


class SystemClock(Clock):
    """System clock implementation."""

    def now(self) -> datetime:
        """Get current UTC datetime."""
        return datetime.utcnow()
