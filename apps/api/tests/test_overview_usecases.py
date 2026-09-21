"""Unit tests for the document overview use cases (fakes, no infrastructure)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.application.usecases.documents.generate_overview import (
    GenerateDocumentOverview,
    sample_chunks,
)
from app.application.usecases.documents.get_cover import GetCover
from app.application.usecases.documents.request_overview import RequestOverview
from app.domain.errors import (
    CoverNotFound,
    DocumentNotFound,
    DocumentNotReady,
    OverviewAlreadyPending,
)
from app.domain.ports.storage import CoverImage
from app.domain.values.overview import OverviewStatus
from app.domain.values.status import DocumentStatus
from fakes import (
    FakeExtractor,
    FakeQueue,
    FakeUowFactory,
    FixedClock,
    ScriptedDescriber,
    make_chunk,
    make_document,
    make_overview,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 21, 12, 0, 0)
COVER = CoverImage(data=b"\xff\xd8jpeg", mime_type="image/jpeg")


def build(
    factory: FakeUowFactory,
    describer: ScriptedDescriber,
    extractor: FakeExtractor | None = None,
    max_tokens: int = 1000,
) -> GenerateDocumentOverview:
    return GenerateDocumentOverview(
        factory,  # type: ignore[arg-type]
        describer,  # type: ignore[arg-type]
        extractor or FakeExtractor(),  # type: ignore[arg-type]
        max_tokens,
    )


class TestSampleChunks:
    def test_empty(self) -> None:
        assert sample_chunks([], 100) == ""

    def test_under_budget_keeps_everything_in_order(self) -> None:
        doc = make_document()
        chunks = [make_chunk(doc.id, i, tokens=10) for i in range(3)]

        text = sample_chunks(chunks, 100)

        assert text.index("chunk-0") < text.index("chunk-1") < text.index("chunk-2")

    def test_over_budget_stays_within_budget(self) -> None:
        doc = make_document()
        chunks = [make_chunk(doc.id, i, tokens=100) for i in range(50)]

        text = sample_chunks(chunks, 500)

        assert text.count("chunk-") <= 5

    def test_over_budget_spreads_across_the_document(self) -> None:
        doc = make_document()
        chunks = [make_chunk(doc.id, i, tokens=100) for i in range(50)]

        text = sample_chunks(chunks, 500)

        assert "chunk-0" in text
        assert any(f"chunk-{i}" in text for i in range(25, 50)), "sample is front-loaded"

    def test_single_oversized_chunk_still_returned(self) -> None:
        doc = make_document()

        text = sample_chunks([make_chunk(doc.id, 0, tokens=10_000)], 100)

        assert text == "chunk-0"


class TestGenerateDocumentOverview:
    async def test_success_applies_overview_and_commits(self) -> None:
        doc = make_document(author="Jane")
        factory = FakeUowFactory([doc], [make_chunk(doc.id, i) for i in range(3)])
        describer = ScriptedDescriber(make_overview())

        ok = await build(factory, describer).execute(doc.id)

        assert ok is True
        assert doc.overview_status == OverviewStatus.READY
        assert doc.summary == "Short summary."
        assert [s["heading"] for s in doc.description_sections] == ["H0", "H1", "H2"]
        assert doc.status == DocumentStatus.READY
        assert factory.uow.commits == 1
        assert describer.calls[0]["author"] == "Jane"

    async def test_invalid_output_is_retried_once(self) -> None:
        doc = make_document()
        factory = FakeUowFactory([doc], [make_chunk(doc.id, 0)])
        describer = ScriptedDescriber(ValueError("bad json"), make_overview())

        ok = await build(factory, describer).execute(doc.id)

        assert ok is True
        assert len(describer.calls) == 2

    async def test_invalid_output_twice_marks_failed_but_keeps_doc_ready(self) -> None:
        doc = make_document()
        factory = FakeUowFactory([doc], [make_chunk(doc.id, 0)])
        describer = ScriptedDescriber(ValueError("bad json"))

        ok = await build(factory, describer).execute(doc.id)

        assert ok is False
        assert len(describer.calls) == 2
        assert doc.overview_status == OverviewStatus.FAILED
        assert doc.status == DocumentStatus.READY
        assert factory.uow.commits == 1

    async def test_unexpected_error_marks_failed_without_retry(self) -> None:
        doc = make_document()
        factory = FakeUowFactory([doc], [make_chunk(doc.id, 0)])
        describer = ScriptedDescriber(RuntimeError("rate limited"))

        ok = await build(factory, describer).execute(doc.id)

        assert ok is False
        assert len(describer.calls) == 1
        assert doc.overview_status == OverviewStatus.FAILED
        assert doc.status == DocumentStatus.READY

    async def test_unknown_document_is_noop(self) -> None:
        factory = FakeUowFactory([])
        describer = ScriptedDescriber(make_overview())
        doc = make_document()

        assert await build(factory, describer).execute(doc.id) is False
        assert describer.calls == []

    @pytest.mark.parametrize("status", [DocumentStatus.PENDING, DocumentStatus.FAILED])
    async def test_not_ready_document_is_noop(self, status: DocumentStatus) -> None:
        doc = make_document(status=status)
        factory = FakeUowFactory([doc], [make_chunk(doc.id, 0)])
        describer = ScriptedDescriber(make_overview())

        assert await build(factory, describer).execute(doc.id) is False
        assert describer.calls == []
        assert doc.overview_status is None

    async def test_no_chunks_marks_failed(self) -> None:
        doc = make_document()
        factory = FakeUowFactory([doc])
        describer = ScriptedDescriber(make_overview())

        assert await build(factory, describer).execute(doc.id) is False
        assert doc.overview_status == OverviewStatus.FAILED
        assert describer.calls == []

    async def test_missing_cover_is_backfilled(self) -> None:
        doc = make_document()
        factory = FakeUowFactory([doc], [make_chunk(doc.id, 0)])

        await build(factory, ScriptedDescriber(make_overview()), FakeExtractor(COVER)).execute(
            doc.id
        )

        assert doc.has_cover
        assert factory.uow.documents.covers[doc.id] == (COVER.data, COVER.mime_type)

    async def test_existing_cover_is_not_rerendered(self) -> None:
        doc = make_document(cover_mime="image/jpeg")
        factory = FakeUowFactory([doc], [make_chunk(doc.id, 0)])
        extractor = FakeExtractor(COVER)

        await build(factory, ScriptedDescriber(make_overview()), extractor).execute(doc.id)

        assert extractor.render_calls == 0

    async def test_cover_failure_does_not_block_overview(self) -> None:
        doc = make_document()
        factory = FakeUowFactory([doc], [make_chunk(doc.id, 0)])

        ok = await build(
            factory, ScriptedDescriber(make_overview()), FakeExtractor(raises=True)
        ).execute(doc.id)

        assert ok is True
        assert not doc.has_cover

    async def test_sample_respects_token_budget(self) -> None:
        doc = make_document()
        chunks = [make_chunk(doc.id, i, tokens=100) for i in range(50)]
        factory = FakeUowFactory([doc], chunks)
        describer = ScriptedDescriber(make_overview())

        await build(factory, describer, max_tokens=300).execute(doc.id)

        assert str(describer.calls[0]["sample"]).count("chunk-") <= 3


class TestRequestOverview:
    def build(
        self, *docs: object, queue: FakeQueue | None = None
    ) -> tuple[RequestOverview, FakeUowFactory, FakeQueue]:
        factory = FakeUowFactory(list(docs))  # type: ignore[arg-type]
        queue = queue or FakeQueue()
        uc = RequestOverview(factory, queue, FixedClock(NOW))  # type: ignore[arg-type]
        return uc, factory, queue

    async def test_marks_pending_commits_and_enqueues(self) -> None:
        doc = make_document()
        uc, factory, queue = self.build(doc)

        await uc.execute(doc.id)

        assert doc.overview_status == OverviewStatus.PENDING
        assert factory.uow.commits == 1
        assert queue.overview_requests == [doc.id]

    async def test_unknown_document(self) -> None:
        uc, _, _ = self.build()

        with pytest.raises(DocumentNotFound):
            await uc.execute(make_document().id)

    async def test_document_must_be_ready(self) -> None:
        doc = make_document(status=DocumentStatus.EMBEDDING)
        uc, _, queue = self.build(doc)

        with pytest.raises(DocumentNotReady):
            await uc.execute(doc.id)
        assert queue.overview_requests == []

    async def test_fresh_pending_is_rejected(self) -> None:
        doc = make_document(
            overview_status=OverviewStatus.PENDING, updated_at=NOW - timedelta(minutes=1)
        )
        uc, _, queue = self.build(doc)

        with pytest.raises(OverviewAlreadyPending):
            await uc.execute(doc.id)
        assert queue.overview_requests == []

    async def test_stale_pending_can_be_requested_again(self) -> None:
        doc = make_document(
            overview_status=OverviewStatus.PENDING, updated_at=NOW - timedelta(minutes=30)
        )
        uc, _, queue = self.build(doc)

        await uc.execute(doc.id)

        assert queue.overview_requests == [doc.id]

    async def test_timezone_aware_updated_at_from_the_database(self) -> None:
        doc = make_document(
            overview_status=OverviewStatus.PENDING,
            updated_at=(NOW - timedelta(minutes=1)).replace(tzinfo=UTC),
        )
        uc, _, _ = self.build(doc)

        with pytest.raises(OverviewAlreadyPending):
            await uc.execute(doc.id)

    @pytest.mark.parametrize("status", [None, OverviewStatus.READY, OverviewStatus.FAILED])
    async def test_non_pending_can_always_be_requested(self, status: OverviewStatus | None) -> None:
        doc = make_document(overview_status=status, updated_at=NOW)
        uc, _, queue = self.build(doc)

        await uc.execute(doc.id)

        assert queue.overview_requests == [doc.id]

    async def test_enqueue_failure_is_swallowed(self) -> None:
        doc = make_document()
        uc, factory, _ = self.build(doc, queue=FakeQueue(fail=True))

        await uc.execute(doc.id)

        assert doc.overview_status == OverviewStatus.PENDING
        assert factory.uow.commits == 1


class TestGetCover:
    async def test_returns_bytes_and_mime(self) -> None:
        doc = make_document(cover_mime="image/jpeg")
        factory = FakeUowFactory([doc])
        factory.uow.documents.covers[doc.id] = (b"abc", "image/jpeg")

        assert await GetCover(factory).execute(doc.id) == (b"abc", "image/jpeg")  # type: ignore[arg-type]

    async def test_unknown_document(self) -> None:
        with pytest.raises(DocumentNotFound):
            await GetCover(FakeUowFactory([])).execute(make_document().id)  # type: ignore[arg-type]

    async def test_document_without_cover(self) -> None:
        doc = make_document()

        with pytest.raises(CoverNotFound):
            await GetCover(FakeUowFactory([doc])).execute(doc.id)  # type: ignore[arg-type]
