"""Document entity — an uploaded PDF and its processing state."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID

from app.domain.values.status import DocumentStatus


@dataclass
class RetryVerdict:
    """Result of checking if a document can be retried."""

    can_retry: bool
    reason: str


@dataclass
class Document:
    """An uploaded PDF and its processing state."""

    id: UUID
    filename: str
    title: str
    status: DocumentStatus
    file_path: str
    content_hash: str
    page_count: int | None = None
    error_message: str | None = None
    chunking_strategy: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def retry_eligibility(self, now: datetime, stuck_after: timedelta) -> RetryVerdict:
        """Determine if document can be retried.

        READY → already_processed
        PENDING/PARSING/EMBEDDING and fresh → still_processing
        PENDING/PARSING/EMBEDDING and stuck → can retry
        FAILED → can retry
        """
        if self.status == DocumentStatus.READY:
            return RetryVerdict(can_retry=False, reason="already_processed")

        if self.status in (DocumentStatus.PENDING, DocumentStatus.PARSING, DocumentStatus.EMBEDDING):
            age = now - self.updated_at
            if age < stuck_after:
                return RetryVerdict(can_retry=False, reason="still_processing")
            return RetryVerdict(can_retry=True, reason="stuck")

        if self.status == DocumentStatus.FAILED:
            return RetryVerdict(can_retry=True, reason="failed")

        return RetryVerdict(can_retry=False, reason="unknown")

    def mark_ready(self, page_count: int, title: str, strategy: str) -> None:
        """Mark document as ready after parsing and embedding."""
        self.status = DocumentStatus.READY
        self.page_count = page_count
        self.title = title
        self.chunking_strategy = strategy
        self.updated_at = datetime.utcnow()

    def mark_failed(self, reason: str) -> None:
        """Mark document as failed with a truncated error message."""
        self.status = DocumentStatus.FAILED
        self.error_message = reason[:1000]
        self.updated_at = datetime.utcnow()
