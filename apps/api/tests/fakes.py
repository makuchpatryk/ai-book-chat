"""In-memory fakes for unit-testing use cases without infrastructure."""

from datetime import datetime
from types import TracebackType
from uuid import UUID, uuid4

from app.domain.entities import Chunk, Document, Section
from app.domain.ports.storage import CoverImage
from app.domain.values.overview import DocumentOverview, OverviewSection
from app.domain.values.status import DocumentStatus


def make_document(**overrides: object) -> Document:
    fields: dict[str, object] = {
        "id": uuid4(),
        "filename": "book.pdf",
        "title": "A Book",
        "status": DocumentStatus.READY,
        "file_path": "/uploads/book.pdf",
        "content_hash": "hash",
    }
    fields.update(overrides)
    return Document(**fields)  # type: ignore[arg-type]


def make_chunk(document_id: UUID, index: int, tokens: int = 100) -> Chunk:
    return Chunk(
        id=uuid4(),
        document_id=document_id,
        section_id=uuid4(),
        content=f"chunk-{index}",
        page_start=index,
        page_end=index,
        token_count=tokens,
        order_index=index,
    )


def make_overview() -> DocumentOverview:
    return DocumentOverview(
        summary="Short summary.",
        language="en",
        doc_type="Book",
        topics=["a", "b", "c"],
        sections=[OverviewSection(heading=f"H{i}", body=f"B{i}") for i in range(3)],
    )


class FakeDocuments:
    def __init__(self, documents: list[Document]) -> None:
        self.store = {d.id: d for d in documents}
        self.covers: dict[UUID, tuple[bytes, str]] = {}
        self.sections: list[Section] = []
        self.saved: list[Document] = []

    async def get(self, document_id: UUID) -> Document | None:
        return self.store.get(document_id)

    async def get_with_sections(self, document_id: UUID) -> tuple[Document, list[Section]] | None:
        document = self.store.get(document_id)
        return (document, self.sections) if document else None

    async def save(self, document: Document) -> None:
        self.saved.append(document)
        self.store[document.id] = document

    async def add(self, document: Document) -> None:
        self.store[document.id] = document

    async def find_by_hash(self, content_hash: str) -> Document | None:
        return next((d for d in self.store.values() if d.content_hash == content_hash), None)

    async def get_cover(self, document_id: UUID) -> tuple[bytes, str] | None:
        return self.covers.get(document_id)

    async def set_cover(self, document_id: UUID, data: bytes, mime: str) -> None:
        self.covers[document_id] = (data, mime)


class FakeChunks:
    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks

    async def list_for_document(self, document_id: UUID) -> list[Chunk]:
        return [c for c in self.chunks if c.document_id == document_id]


class FakeUow:
    def __init__(self, documents: FakeDocuments, chunks: FakeChunks) -> None:
        self.documents = documents
        self.chunks = chunks
        self.commits = 0

    async def __aenter__(self) -> "FakeUow":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1


class FakeUowFactory:
    def __init__(self, documents: list[Document], chunks: list[Chunk] | None = None) -> None:
        self.uow = FakeUow(FakeDocuments(documents), FakeChunks(chunks or []))

    def __call__(self) -> FakeUow:
        return self.uow


class FakeQueue:
    def __init__(self, fail: bool = False) -> None:
        self.overview_requests: list[UUID] = []
        self.ingest_requests: list[UUID] = []
        self.fail = fail

    async def enqueue(self, document_id: UUID) -> None:
        self.ingest_requests.append(document_id)

    async def enqueue_overview(self, document_id: UUID) -> None:
        if self.fail:
            raise RuntimeError("broker down")
        self.overview_requests.append(document_id)


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class FakeExtractor:
    def __init__(self, cover: CoverImage | None = None, raises: bool = False) -> None:
        self.cover = cover
        self.raises = raises
        self.render_calls = 0

    def render_cover(self, file_path: str, width_px: int) -> CoverImage | None:
        self.render_calls += 1
        if self.raises:
            raise RuntimeError("corrupt pdf")
        return self.cover


class ScriptedDescriber:
    """Returns / raises the queued outcomes in order, then repeats the last one."""

    def __init__(self, *outcomes: DocumentOverview | Exception) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, object]] = []

    async def describe(
        self,
        title: str,
        author: str | None,
        section_titles: list[str],
        sample_text: str,
    ) -> DocumentOverview:
        self.calls.append(
            {"title": title, "author": author, "sections": section_titles, "sample": sample_text}
        )
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
