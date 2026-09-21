"""Document entity — an uploaded PDF and its processing state."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.domain.values.overview import DocumentOverview, OverviewStatus
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
    author: str | None = None
    summary: str | None = None
    language: str | None = None
    doc_type: str | None = None
    topics: list[str] = field(default_factory=list)
    description_sections: list[dict[str, str]] = field(default_factory=list)
    overview_status: OverviewStatus | None = None
    cover_mime: str | None = None

    @property
    def has_cover(self) -> bool:
        """True if document has a cover image."""
        return self.cover_mime is not None

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
            # The DB hands back aware datetimes; the clock hands out naive UTC.
            updated_at = self.updated_at
            if updated_at.tzinfo is not None:
                updated_at = updated_at.astimezone(UTC).replace(tzinfo=None)
            age = now - updated_at
            if age < stuck_after:
                return RetryVerdict(can_retry=False, reason="still_processing")
            return RetryVerdict(can_retry=True, reason="stuck")

        if self.status == DocumentStatus.FAILED:
            return RetryVerdict(can_retry=True, reason="failed")

        return RetryVerdict(can_retry=False, reason="unknown")

    def mark_ready(
        self, page_count: int, title: str, strategy: str, author: str | None = None
    ) -> None:
        """Mark document as ready after parsing and embedding."""
        self.status = DocumentStatus.READY
        self.page_count = page_count
        self.title = title
        self.chunking_strategy = strategy
        self.author = author
        self.error_message = None
        self.updated_at = datetime.utcnow()

    def mark_queued(self) -> None:
        """Back to PENDING for another ingestion run; restarts the stuck timer."""
        self.status = DocumentStatus.PENDING
        self.error_message = None
        self.updated_at = datetime.utcnow()

    def mark_failed(self, reason: str) -> None:
        """Mark document as failed with a truncated error message."""
        self.status = DocumentStatus.FAILED
        self.error_message = reason[:1000]
        self.updated_at = datetime.utcnow()

    def mark_overview_pending(self, now: datetime) -> None:
        """Mark overview as pending, ready to generate."""
        self.overview_status = OverviewStatus.PENDING
        self.updated_at = now

    def apply_overview(self, overview: DocumentOverview) -> None:
        """Apply generated overview to document."""
        self.summary = overview.summary
        self.language = overview.language
        self.doc_type = overview.doc_type
        self.topics = overview.topics
        self.description_sections = [
            {"heading": s.heading, "body": s.body} for s in overview.sections
        ]
        self.overview_status = OverviewStatus.READY
        self.updated_at = datetime.utcnow()

    def mark_overview_failed(self) -> None:
        """Mark overview generation as failed."""
        self.overview_status = OverviewStatus.FAILED
        self.updated_at = datetime.utcnow()

    def clear_derived(self) -> None:
        """Reset overview on retry path (re-ingestion)."""
        self.overview_status = None
        self.summary = None
        self.language = None
        self.doc_type = None
        self.topics = []
        self.description_sections = []
