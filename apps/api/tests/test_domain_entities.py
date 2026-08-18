"""Unit tests for domain entities (no infrastructure, marked unit)."""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from app.domain.entities.conversation import Conversation
from app.domain.entities.document import Document, RetryVerdict
from app.domain.values.status import DocumentStatus


pytestmark = pytest.mark.unit


class TestDocumentRetryEligibility:
    """Test Document.retry_eligibility across all statuses."""

    def test_ready_document_not_eligible(self) -> None:
        """READY document cannot be retried."""
        doc = Document(
            id=uuid4(),
            filename="test.pdf",
            title="Test",
            status=DocumentStatus.READY,
            file_path="/uploads/test.pdf",
            content_hash="abc123",
        )

        verdict = doc.retry_eligibility(datetime.utcnow(), timedelta(minutes=30))

        assert verdict.can_retry is False
        assert verdict.reason == "already_processed"

    def test_failed_document_eligible(self) -> None:
        """FAILED document can be retried."""
        doc = Document(
            id=uuid4(),
            filename="test.pdf",
            title="Test",
            status=DocumentStatus.FAILED,
            file_path="/uploads/test.pdf",
            content_hash="abc123",
            error_message="Parse failed",
        )

        verdict = doc.retry_eligibility(datetime.utcnow(), timedelta(minutes=30))

        assert verdict.can_retry is True
        assert verdict.reason == "failed"

    def test_pending_fresh_not_eligible(self) -> None:
        """PENDING document < stuck_after is still processing."""
        now = datetime.utcnow()
        doc = Document(
            id=uuid4(),
            filename="test.pdf",
            title="Test",
            status=DocumentStatus.PENDING,
            file_path="/uploads/test.pdf",
            content_hash="abc123",
            updated_at=now,
        )

        verdict = doc.retry_eligibility(now + timedelta(minutes=10), timedelta(minutes=30))

        assert verdict.can_retry is False
        assert verdict.reason == "still_processing"

    def test_parsing_stuck_eligible(self) -> None:
        """PARSING document > stuck_after is eligible for retry."""
        now = datetime.utcnow()
        doc = Document(
            id=uuid4(),
            filename="test.pdf",
            title="Test",
            status=DocumentStatus.PARSING,
            file_path="/uploads/test.pdf",
            content_hash="abc123",
            updated_at=now,
        )

        verdict = doc.retry_eligibility(now + timedelta(minutes=40), timedelta(minutes=30))

        assert verdict.can_retry is True
        assert verdict.reason == "stuck"

    def test_embedding_stuck_eligible(self) -> None:
        """EMBEDDING document > stuck_after is eligible for retry."""
        now = datetime.utcnow()
        doc = Document(
            id=uuid4(),
            filename="test.pdf",
            title="Test",
            status=DocumentStatus.EMBEDDING,
            file_path="/uploads/test.pdf",
            content_hash="abc123",
            updated_at=now,
        )

        verdict = doc.retry_eligibility(now + timedelta(minutes=45), timedelta(minutes=30))

        assert verdict.can_retry is True
        assert verdict.reason == "stuck"


class TestDocumentMarkReady:
    """Test Document.mark_ready behavior."""

    def test_mark_ready_updates_fields(self) -> None:
        """mark_ready updates status, page_count, title, and strategy."""
        doc = Document(
            id=uuid4(),
            filename="test.pdf",
            title="Original Title",
            status=DocumentStatus.PARSING,
            file_path="/uploads/test.pdf",
            content_hash="abc123",
        )

        doc.mark_ready(page_count=42, title="Final Title", strategy="outline")

        assert doc.status == DocumentStatus.READY
        assert doc.page_count == 42
        assert doc.title == "Final Title"
        assert doc.chunking_strategy == "outline"


class TestDocumentMarkFailed:
    """Test Document.mark_failed behavior."""

    def test_mark_failed_truncates_message(self) -> None:
        """mark_failed truncates error message to 1000 chars."""
        doc = Document(
            id=uuid4(),
            filename="test.pdf",
            title="Test",
            status=DocumentStatus.PARSING,
            file_path="/uploads/test.pdf",
            content_hash="abc123",
        )
        long_error = "x" * 2000

        doc.mark_failed(long_error)

        assert doc.status == DocumentStatus.FAILED
        assert len(doc.error_message or "") == 1000
        assert doc.error_message == "x" * 1000


class TestConversationDeriveTitle:
    """Test Conversation.derive_title behavior."""

    def test_short_text_unchanged(self) -> None:
        """Text shorter than max_length is returned as-is."""
        text = "What is machine learning?"

        title = Conversation.derive_title(text)

        assert title == text

    def test_long_text_trimmed_at_word_boundary(self) -> None:
        """Text longer than max_length is trimmed at word boundary."""
        text = "What is machine learning and how does it work in practice?"

        title = Conversation.derive_title(text, max_length=30)

        assert len(title) <= 30 + 1  # +1 for the ellipsis
        assert title.endswith("…")
        assert " " not in title.split("…")[0].split()[-1]  # Last word before ellipsis is complete

    def test_empty_text(self) -> None:
        """Empty text returns empty string."""
        title = Conversation.derive_title("")

        assert title == ""

    def test_whitespace_stripped(self) -> None:
        """Leading/trailing whitespace is stripped."""
        text = "  Hello world  "

        title = Conversation.derive_title(text)

        assert title == "Hello world"

    def test_max_length_default_is_60(self) -> None:
        """Default max_length is 60 characters."""
        text = "A" * 70

        title = Conversation.derive_title(text)

        assert len(title) <= 61  # 60 + ellipsis
