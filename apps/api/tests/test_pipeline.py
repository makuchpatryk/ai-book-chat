"""The pipeline against a real Postgres, with the deterministic fake embedder."""

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

import factories
from app.db.models import Chunk, Document, DocumentStatus, Section
from app.ingestion.embeddings import FakeEmbedder
from app.ingestion.pipeline import DocumentNotFoundError, process_document


class BoomEmbedder:
    """Fails the way a provider outage would: after parsing, before any write."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding provider exploded")


def _insert_document(session: Session, path: Path) -> Document:
    document = Document(
        filename=path.name,
        title=path.stem,
        file_path=str(path),
        content_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
        status=DocumentStatus.PENDING,
    )
    session.add(document)
    session.commit()
    return document


def _chunks(session: Session, document: Document) -> list[Chunk]:
    return list(
        session.scalars(
            sa.select(Chunk).where(Chunk.document_id == document.id).order_by(Chunk.order_index)
        )
    )


def _sections(session: Session, document: Document) -> list[Section]:
    return list(
        session.scalars(
            sa.select(Section)
            .where(Section.document_id == document.id)
            .order_by(Section.order_index)
        )
    )


def test_happy_path_reaches_ready(sync_session: Session, tmp_path: Path) -> None:
    path = factories.book_pdf(tmp_path / "book.pdf", chapters=3, pages_per=2)
    document = _insert_document(sync_session, path)

    assert process_document(sync_session, document.id, FakeEmbedder()) == "READY"

    sync_session.refresh(document)
    assert document.status is DocumentStatus.READY
    assert document.page_count == 6
    assert document.chunking_strategy == "outline"
    assert document.title == "The Test Book"
    assert document.error_message is None

    sections = _sections(sync_session, document)
    assert [section.title for section in sections] == ["Chapter 1", "Chapter 2", "Chapter 3"]

    chunks = _chunks(sync_session, document)
    assert chunks
    assert [chunk.order_index for chunk in chunks] == list(range(len(chunks)))
    section_ids = {section.id for section in sections}
    for chunk in chunks:
        assert len(chunk.embedding) == 1536
        assert chunk.section_id in section_ids
        assert 1 <= chunk.page_start <= chunk.page_end <= 6


def test_ready_chunks_are_searchable_by_cosine_distance(
    sync_session: Session, tmp_path: Path
) -> None:
    path = factories.book_pdf(tmp_path / "book.pdf")
    document = _insert_document(sync_session, path)
    process_document(sync_session, document.id, FakeEmbedder())

    target = _chunks(sync_session, document)[2]
    nearest = sync_session.scalars(
        sa.select(Chunk)
        .where(Chunk.document_id == document.id)
        .order_by(Chunk.embedding.cosine_distance(list(target.embedding)))
        .limit(1)
    ).one()

    assert nearest.id == target.id


def test_failed_embedding_leaves_no_rows_behind(sync_session: Session, tmp_path: Path) -> None:
    path = factories.book_pdf(tmp_path / "book.pdf")
    document = _insert_document(sync_session, path)

    assert process_document(sync_session, document.id, BoomEmbedder()) == "FAILED"

    sync_session.refresh(document)
    assert document.status is DocumentStatus.FAILED
    assert "embedding provider exploded" in (document.error_message or "")
    assert _chunks(sync_session, document) == []
    assert _sections(sync_session, document) == []


def test_scanned_pdf_fails_with_a_readable_reason(sync_session: Session, tmp_path: Path) -> None:
    path = factories.scanned_pdf(tmp_path / "scan.pdf")
    document = _insert_document(sync_session, path)

    assert process_document(sync_session, document.id, FakeEmbedder()) == "FAILED"

    sync_session.refresh(document)
    assert document.status is DocumentStatus.FAILED
    assert "scanned" in (document.error_message or "")
    assert _chunks(sync_session, document) == []
    assert _sections(sync_session, document) == []


def test_unknown_document_id_raises(sync_session: Session) -> None:
    with pytest.raises(DocumentNotFoundError):
        process_document(sync_session, uuid4(), FakeEmbedder())
