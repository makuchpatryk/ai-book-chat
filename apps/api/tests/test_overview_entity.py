"""Unit tests for Document overview state transitions."""

from datetime import datetime

import pytest

from app.domain.values.overview import OverviewStatus
from app.domain.values.status import DocumentStatus
from fakes import make_document, make_overview

pytestmark = pytest.mark.unit


def test_new_document_has_no_overview() -> None:
    doc = make_document()

    assert doc.overview_status is None
    assert doc.topics == []
    assert doc.description_sections == []
    assert doc.has_cover is False


def test_has_cover_follows_cover_mime() -> None:
    assert make_document(cover_mime="image/jpeg").has_cover is True


def test_mark_overview_pending_stamps_updated_at() -> None:
    doc = make_document()
    now = datetime(2026, 1, 1, 12, 0)

    doc.mark_overview_pending(now)

    assert doc.overview_status == OverviewStatus.PENDING
    assert doc.updated_at == now


def test_apply_overview_copies_every_field() -> None:
    doc = make_document(overview_status=OverviewStatus.PENDING)

    doc.apply_overview(make_overview())

    assert doc.overview_status == OverviewStatus.READY
    assert doc.summary == "Short summary."
    assert doc.language == "en"
    assert doc.doc_type == "Book"
    assert doc.topics == ["a", "b", "c"]
    assert doc.description_sections[0] == {"heading": "H0", "body": "B0"}


def test_mark_overview_failed_leaves_document_status_alone() -> None:
    doc = make_document()

    doc.mark_overview_failed()

    assert doc.overview_status == OverviewStatus.FAILED
    assert doc.status == DocumentStatus.READY


def test_clear_derived_resets_overview_but_keeps_cover() -> None:
    doc = make_document(cover_mime="image/jpeg")
    doc.apply_overview(make_overview())

    doc.clear_derived()

    assert doc.overview_status is None
    assert doc.summary is None
    assert doc.topics == []
    assert doc.description_sections == []
    assert doc.has_cover is True


def test_mark_ready_records_author() -> None:
    doc = make_document(status=DocumentStatus.EMBEDDING)

    doc.mark_ready(10, "Title", "outline", author="Jane")

    assert doc.author == "Jane"
    assert doc.status == DocumentStatus.READY
