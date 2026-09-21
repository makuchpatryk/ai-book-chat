"""IngestDocument commits embedding progress after every batch."""

from uuid import UUID

import pytest

from app.application.usecases.ingestion.ingest_document import IngestDocument
from app.domain.entities import Chunk, Document, Section
from app.domain.ports.storage import ExtractedPdf, PageText
from app.domain.values.status import DocumentStatus
from fakes import FakeDocuments, FakeUowFactory, make_document

pytestmark = pytest.mark.unit


class ProgressDocuments(FakeDocuments):
    """Snapshots (status, embedded, total) on every save; entities are mutated in place."""

    def __init__(self, documents: list[Document]) -> None:
        super().__init__(documents)
        self.progress: list[tuple[DocumentStatus, int | None, int | None]] = []

    async def save(self, document: Document) -> None:
        await super().save(document)
        self.progress.append((document.status, document.embedded_chunks, document.total_chunks))

    async def clear_derived(self, document_id: UUID) -> None:
        return None


class Sink:
    async def add_many(self, items: list[Section] | list[Chunk]) -> None:
        return None


class Extractor:
    def extract(self, file_path: str, fallback_title: str | None = None) -> ExtractedPdf:
        pages = [PageText(page_number=i, text="word " * 40) for i in range(1, 4)]
        return ExtractedPdf(page_count=3, title="Book", pages=pages, lines=[], outline=[])

    def render_cover(self, file_path: str, width_px: int) -> None:
        return None


class CharTokens:
    def encode(self, text: str) -> list[int]:
        return [ord(c) for c in text]

    def decode(self, tokens: list[int]) -> str:
        return "".join(chr(t) for t in tokens)


class Embedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] for _ in texts]


async def test_progress_is_saved_after_each_batch() -> None:
    document = make_document(status=DocumentStatus.PENDING)
    factory = FakeUowFactory([document])
    documents = ProgressDocuments([document])
    factory.uow.documents = documents
    factory.uow.sections = Sink()  # type: ignore[attr-defined]
    factory.uow.chunks = Sink()  # type: ignore[assignment]
    use_case = IngestDocument(
        factory,  # type: ignore[arg-type]
        Extractor(),  # type: ignore[arg-type]
        CharTokens(),  # type: ignore[arg-type]
        Embedder(),
        embedding_batch_size=4,
        chunk_target_tokens=100,
        chunk_overlap_ratio=0.0,
    )

    result = await use_case.execute(document.id)

    assert result.status == DocumentStatus.READY
    total = result.total_chunks
    assert total is not None and total > 4  # several batches
    embedding = [
        (done, t) for status, done, t in documents.progress if status == DocumentStatus.EMBEDDING
    ]
    expected_steps = [0, *range(4, total, 4), total]
    assert embedding == [(step, total) for step in expected_steps]
    assert result.embedded_chunks == total
