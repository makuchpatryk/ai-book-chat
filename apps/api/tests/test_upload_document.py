"""UploadDocument: streamed save, PDF header check, size limit, hash-based dedupe."""

import hashlib
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.application.usecases.documents.upload_document import UploadDocument
from app.domain.errors import DuplicateUpload, FileTooLarge, NotAPdf
from app.domain.values.status import DocumentStatus
from app.infrastructure.storage.local_files import LocalFileStorage
from fakes import FakeQueue, FakeUowFactory, make_document

PDF = b"%PDF-1.7\n" + b"x" * 100


async def stream(*chunks: bytes) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


def build(tmp_path: Path, documents: list | None = None, max_mb: int = 1):
    factory = FakeUowFactory(documents or [])
    queue = FakeQueue()
    storage = LocalFileStorage(tmp_path)
    return UploadDocument(factory, storage, queue, max_mb), factory, queue


@pytest.mark.unit
class TestUploadDocument:
    async def test_new_pdf_is_stored_hashed_and_enqueued(self, tmp_path: Path) -> None:
        use_case, factory, queue = build(tmp_path)

        document = await use_case.execute("book.pdf", stream(PDF[:3], PDF[3:]))

        assert document is not None
        assert document.content_hash == hashlib.sha256(PDF).hexdigest()
        assert Path(document.file_path).read_bytes() == PDF
        assert queue.ingest_requests == [document.id]
        assert factory.uow.documents.store[document.id] is document

    async def test_non_pdf_bytes_rejected_and_nothing_left_on_disk(self, tmp_path: Path) -> None:
        use_case, _, queue = build(tmp_path)

        with pytest.raises(NotAPdf):
            await use_case.execute("fake.pdf", stream(b"<html>not a pdf</html>"))

        assert list(tmp_path.iterdir()) == []
        assert queue.ingest_requests == []

    async def test_too_short_to_hold_header_rejected(self, tmp_path: Path) -> None:
        use_case, _, _ = build(tmp_path)

        with pytest.raises(NotAPdf):
            await use_case.execute("tiny.pdf", stream(b"%PD"))

        assert list(tmp_path.iterdir()) == []

    async def test_oversized_upload_rejected_and_removed(self, tmp_path: Path) -> None:
        use_case, _, _ = build(tmp_path, max_mb=1)
        megabyte = b"x" * (1024 * 1024)

        with pytest.raises(FileTooLarge):
            await use_case.execute("big.pdf", stream(b"%PDF-", megabyte))

        assert list(tmp_path.iterdir()) == []

    async def test_duplicate_of_ready_document_conflicts_and_drops_new_copy(
        self, tmp_path: Path
    ) -> None:
        existing = make_document(content_hash=hashlib.sha256(PDF).hexdigest())
        use_case, _, queue = build(tmp_path, [existing])

        with pytest.raises(DuplicateUpload):
            await use_case.execute("again.pdf", stream(PDF))

        assert list(tmp_path.iterdir()) == []
        assert queue.ingest_requests == []

    async def test_duplicate_of_failed_document_is_re_enqueued(self, tmp_path: Path) -> None:
        existing = make_document(
            content_hash=hashlib.sha256(PDF).hexdigest(), status=DocumentStatus.FAILED
        )
        use_case, _, queue = build(tmp_path, [existing])

        document = await use_case.execute("again.pdf", stream(PDF))

        assert document is existing
        assert queue.ingest_requests == [existing.id]
        assert list(tmp_path.iterdir()) == []


@pytest.mark.integration
async def test_http_upload_of_non_pdf_is_422(client: AsyncClient) -> None:
    response = await client.post(
        "/documents", files={"file": ("fake.pdf", b"GIF89a....", "application/pdf")}
    )

    assert response.status_code == 422
    assert "not a valid PDF" in response.json()["detail"]
