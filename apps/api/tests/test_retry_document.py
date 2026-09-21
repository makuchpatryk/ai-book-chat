"""RetryDocument: resets to PENDING and commits before enqueueing."""

from datetime import datetime, timedelta
from uuid import UUID

import pytest

from app.application.usecases.documents.retry_document import RetryDocument
from app.domain.errors import DocumentStillProcessing
from app.domain.values.status import DocumentStatus
from fakes import FakeUowFactory, FixedClock, make_document

pytestmark = pytest.mark.unit

STUCK_AFTER = timedelta(minutes=30)


class CommitCheckingQueue:
    """Records how many commits had happened when each enqueue arrived."""

    def __init__(self, factory: FakeUowFactory) -> None:
        self.factory = factory
        self.commits_at_enqueue: list[int] = []

    async def enqueue(self, document_id: UUID) -> None:
        self.commits_at_enqueue.append(self.factory.uow.commits)


async def test_failed_document_goes_back_to_pending_before_enqueue() -> None:
    document = make_document(status=DocumentStatus.FAILED, error_message="boom")
    factory = FakeUowFactory([document])
    queue = CommitCheckingQueue(factory)
    use_case = RetryDocument(factory, queue, FixedClock(datetime.utcnow()), STUCK_AFTER)  # type: ignore[arg-type]

    result = await use_case.execute(document.id)

    assert result.status == DocumentStatus.PENDING
    assert result.error_message is None
    assert queue.commits_at_enqueue == [1]


async def test_second_retry_of_a_stuck_document_is_rejected() -> None:
    now = datetime.utcnow()
    document = make_document(
        status=DocumentStatus.PARSING, updated_at=now - timedelta(minutes=40)
    )
    factory = FakeUowFactory([document])
    queue = CommitCheckingQueue(factory)
    use_case = RetryDocument(factory, queue, FixedClock(now), STUCK_AFTER)  # type: ignore[arg-type]

    await use_case.execute(document.id)
    with pytest.raises(DocumentStillProcessing):
        await use_case.execute(document.id)

    assert len(queue.commits_at_enqueue) == 1
