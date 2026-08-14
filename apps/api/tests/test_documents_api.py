"""Upload / list / detail against the real database, with the queue stubbed out."""

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.orm import Session

import factories
from app.config import Settings, get_settings
from app.ingestion.embeddings import FakeEmbedder
from app.ingestion.pipeline import process_document


def _upload(path: Path, filename: str | None = None) -> dict[str, tuple[str, bytes, str]]:
    return {"file": (filename or path.name, path.read_bytes(), "application/pdf")}


async def test_upload_returns_201_and_enqueues(
    client: AsyncClient, sync_session: Session, enqueued: list[str], tmp_path: Path
) -> None:
    path = factories.book_pdf(tmp_path / "book.pdf")

    response = await client.post("/documents", files=_upload(path))

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PENDING"
    assert body["filename"] == "book.pdf"
    assert body["title"] == "book"
    assert body["page_count"] is None
    assert enqueued == [body["id"]]


async def test_reupload_returns_the_same_document(
    client: AsyncClient, sync_session: Session, enqueued: list[str], tmp_path: Path
) -> None:
    path = factories.book_pdf(tmp_path / "book.pdf")

    first = await client.post("/documents", files=_upload(path))
    second = await client.post("/documents", files=_upload(path, filename="same-book.pdf"))

    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    # No second processing run: the book is already embedded (or on its way).
    assert enqueued == [first.json()["id"]]


async def test_non_pdf_upload_is_rejected(
    client: AsyncClient, sync_session: Session, enqueued: list[str], tmp_path: Path
) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("not a pdf")

    response = await client.post("/documents", files={"file": ("notes.txt", path.read_bytes())})

    assert response.status_code == 415
    assert enqueued == []


async def test_pdf_without_the_magic_header_is_rejected(
    client: AsyncClient, sync_session: Session, enqueued: list[str], settings: Settings
) -> None:
    response = await client.post(
        "/documents", files={"file": ("book.pdf", b"definitely not a pdf", "application/pdf")}
    )

    assert response.status_code == 422
    assert list(settings.upload_dir.glob("*.pdf")) == []


async def test_oversized_upload_is_rejected_and_leaves_no_file(
    app: FastAPI, client: AsyncClient, sync_session: Session, enqueued: list[str], tmp_path: Path
) -> None:
    # A 1 MB cap with a 2 MB body exercises the same streamed check as the real
    # 50 MB one, without pushing 51 MB through the test transport.
    small_cap = Settings(upload_dir=tmp_path / "uploads", max_upload_mb=1)
    app.dependency_overrides[get_settings] = lambda: small_cap

    response = await client.post(
        "/documents",
        files={"file": ("big.pdf", b"%PDF-" + b"x" * (2 * 1024 * 1024), "application/pdf")},
    )

    assert response.status_code == 413
    assert list(small_cap.upload_dir.glob("*.pdf")) == []
    assert enqueued == []


async def test_list_is_newest_first(
    client: AsyncClient, sync_session: Session, enqueued: list[str], tmp_path: Path
) -> None:
    older = await client.post("/documents", files=_upload(factories.plain_pdf(tmp_path / "a.pdf")))
    newer = await client.post("/documents", files=_upload(factories.book_pdf(tmp_path / "b.pdf")))

    response = await client.get("/documents")

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()]
    assert ids.index(newer.json()["id"]) < ids.index(older.json()["id"])


async def test_detail_includes_sections_and_chunk_count(
    client: AsyncClient, sync_session: Session, enqueued: list[str], tmp_path: Path
) -> None:
    upload = await client.post("/documents", files=_upload(factories.book_pdf(tmp_path / "b.pdf")))
    document_id = UUID(upload.json()["id"])
    # Stand in for the worker the `enqueued` fixture intercepted.
    process_document(sync_session, document_id, FakeEmbedder())

    response = await client.get(f"/documents/{document_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "READY"
    assert body["page_count"] == 6
    assert body["chunk_count"] > 0
    assert [section["title"] for section in body["sections"]] == [
        "Chapter 1",
        "Chapter 2",
        "Chapter 3",
    ]


@pytest.mark.parametrize("document_id", [str(uuid4())])
async def test_detail_404s_for_an_unknown_id(client: AsyncClient, document_id: str) -> None:
    response = await client.get(f"/documents/{document_id}")

    assert response.status_code == 404
