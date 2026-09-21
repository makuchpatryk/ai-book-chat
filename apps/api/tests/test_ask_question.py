"""AskQuestion: citations are persisted with the answer; generator failure ends in AnswerFailed."""

from collections.abc import AsyncIterator
from types import TracebackType
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.usecases.chat.ask_question import AskQuestion
from app.domain.entities import Conversation, Message, Section
from app.domain.events import AnswerCompleted, AnswerEvent, AnswerFailed, SourcesFound
from app.domain.values.messages import Turn
from app.domain.values.policies import ChatPolicy, RetrievalPolicy
from app.domain.values.retrieval import Citation, RetrievedChunk
from app.domain.values.status import MessageRole
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from fakes import make_chunk, make_document

DOCUMENT = make_document()
CONVERSATION = Conversation(id=uuid4(), document_id=DOCUMENT.id)
CHUNK = RetrievedChunk(
    chunk_id=uuid4(),
    distance=0.1,
    content="The whale is white.",
    page_start=12,
    page_end=13,
    section_title="Chapter 1",
)


class FakeMessages:
    def __init__(self) -> None:
        self.added: list[Message] = []

    async def recent_turns(self, conversation_id: UUID, limit: int) -> list[Turn]:
        return []

    async def next_order_index(self, conversation_id: UUID) -> int:
        return len(self.added)

    async def add(self, message: Message) -> None:
        self.added.append(message)


class FakeConversations:
    async def get(self, conversation_id: UUID) -> Conversation | None:
        return CONVERSATION if conversation_id == CONVERSATION.id else None


class FakeDocs:
    async def get(self, document_id: UUID):  # type: ignore[no-untyped-def]
        return DOCUMENT if document_id == DOCUMENT.id else None


class FakeChunkSearch:
    async def search_similar(
        self, document_id: UUID, vector: list[float], limit: int
    ) -> list[RetrievedChunk]:
        return [CHUNK]


class ChatUow:
    def __init__(self, messages: FakeMessages, log: list[str]) -> None:
        self.log = log
        self.conversations = FakeConversations()
        self.documents = FakeDocs()
        self.messages = messages
        self.chunks = FakeChunkSearch()

    async def __aenter__(self) -> "ChatUow":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        self.log.append("rollback")


class Embedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] for _ in texts]


class Reranker:
    async def score(self, query: str, passages: list[str]) -> list[int]:
        return [9 for _ in passages]


class Rewriter:
    async def rewrite(self, question: str, history: list[Turn]) -> str:
        return question


class Generator:
    def __init__(self, fail_after: int | None = None) -> None:
        self.fail_after = fail_after
        self.log: list[str] = []

    def stream(self, system: str, turns: list[Turn]) -> AsyncIterator[str]:
        async def _stream() -> AsyncIterator[str]:
            self.log.append("generate")
            for i, token in enumerate(["Yes ", "[p.12]"]):
                if self.fail_after is not None and i == self.fail_after:
                    raise RuntimeError("LLM 503")
                yield token

        return _stream()


def build(generator: Generator) -> tuple[AskQuestion, FakeMessages]:
    messages = FakeMessages()
    uow = ChatUow(messages, generator.log)
    use_case = AskQuestion(
        uow_factory=lambda: uow,  # type: ignore[arg-type,return-value]
        rewriter=Rewriter(),
        embedder=Embedder(),
        reranker=Reranker(),
        generator=generator,
        retrieval_policy=RetrievalPolicy(top_k=5, min_score=5, max_distance=0.75, top_n=3),
        chat_policy=ChatPolicy(max_tokens=100, history_turns=3, rerank_top_n=3),
    )
    return use_case, messages


async def collect(events: AsyncIterator[AnswerEvent]) -> list[AnswerEvent]:
    return [event async for event in events]


@pytest.mark.unit
class TestAskQuestion:
    async def test_answer_is_saved_with_the_streamed_citations(self) -> None:
        use_case, messages = build(Generator())

        events = await collect(use_case.execute(CONVERSATION.id, "Is the whale white?"))

        sources = next(e for e in events if isinstance(e, SourcesFound))
        assert isinstance(events[-1], AnswerCompleted)
        assistant = messages.added[-1]
        assert assistant.role == MessageRole.ASSISTANT
        assert assistant.content == "Yes [p.12]"
        assert assistant.sources == sources.citations
        assert [c.chunk_id for c in assistant.sources] == [CHUNK.chunk_id]

    async def test_db_transaction_ends_before_generation_starts(self) -> None:
        generator = Generator()
        use_case, _ = build(generator)

        await collect(use_case.execute(CONVERSATION.id, "Is the whale white?"))

        assert generator.log == ["rollback", "generate"]

    async def test_generator_failure_emits_answer_failed(self) -> None:
        use_case, messages = build(Generator(fail_after=1))

        events = await collect(use_case.execute(CONVERSATION.id, "Is the whale white?"))

        assert isinstance(events[-1], AnswerFailed)
        assert events[-1].detail == "answer generation failed"
        # The question survives; no half-written answer is saved.
        assert [m.role for m in messages.added] == [MessageRole.USER]


@pytest.mark.integration
async def test_citations_round_trip_through_the_database(app_session: AsyncSession) -> None:
    uow = SqlAlchemyUnitOfWork(app_session)
    document = make_document(content_hash=uuid4().hex)
    await uow.documents.add(document)
    section = Section(
        id=uuid4(), document_id=document.id, title="Chapter 1", order_index=0,
        start_page=1, end_page=20,
    )
    await uow.sections.add_many([section])
    chunk = make_chunk(document.id, 12)
    chunk.section_id = section.id
    chunk.embedding = [0.1] * 768
    await uow.chunks.add_many([chunk])
    conversation = Conversation(id=uuid4(), document_id=document.id)
    await uow.conversations.add(conversation)
    citation = Citation(
        chunk_id=chunk.id, page_start=12, page_end=12, score=8,
        section_title="Chapter 1", snippet="chunk-12",
    )
    await uow.messages.add(
        Message(
            id=uuid4(), conversation_id=conversation.id, role=MessageRole.ASSISTANT,
            content="answer", order_index=0, grounded=True, sources=[citation],
        )
    )
    await uow.commit()
    app_session.expunge_all()

    loaded = await uow.messages.list_with_citations(conversation.id)

    assert loaded[0].sources == [citation]
