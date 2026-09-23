"""RenameConversation: use case commits only on success; PATCH endpoint validates and persists."""

from types import TracebackType
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.usecases.chat.rename_conversation import RenameConversation
from app.domain.entities import Conversation
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from fakes import make_document


class FakeConversations:
    def __init__(self, conversation: Conversation) -> None:
        self.conversation = conversation

    async def rename(self, conversation_id: UUID, title: str) -> Conversation | None:
        if conversation_id != self.conversation.id:
            return None
        self.conversation.title = title
        return self.conversation


class RenameUow:
    def __init__(self, conversations: FakeConversations) -> None:
        self.conversations = conversations
        self.commits = 0

    async def __aenter__(self) -> "RenameUow":
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


def make_use_case() -> tuple[RenameConversation, Conversation, RenameUow]:
    conversation = Conversation(id=uuid4(), document_id=uuid4())
    uow = RenameUow(FakeConversations(conversation))
    return RenameConversation(lambda: uow), conversation, uow  # type: ignore[arg-type,return-value]


async def test_rename_sets_title_and_commits() -> None:
    use_case, conversation, uow = make_use_case()

    result = await use_case.execute(conversation.id, "Whale chat")

    assert result is not None
    assert result.title == "Whale chat"
    assert uow.commits == 1


async def test_rename_missing_conversation_returns_none_without_commit() -> None:
    use_case, _, uow = make_use_case()

    result = await use_case.execute(uuid4(), "Whale chat")

    assert result is None
    assert uow.commits == 0



@pytest.mark.integration
async def test_patch_trims_persists_and_lists(
    app_session: AsyncSession, client: AsyncClient
) -> None:
    uow = SqlAlchemyUnitOfWork(app_session)
    document = make_document(content_hash=uuid4().hex)
    await uow.documents.add(document)
    await uow.commit()
    created = await client.post(f"/documents/{document.id}/conversations")
    conversation_id = created.json()["id"]

    response = await client.patch(f"/conversations/{conversation_id}", json={"title": "  My chat "})

    assert response.status_code == 200
    assert response.json()["title"] == "My chat"
    listed = await client.get(f"/documents/{document.id}/conversations")
    assert [c["title"] for c in listed.json()] == ["My chat"]


@pytest.mark.integration
@pytest.mark.parametrize("title", ["", "   ", "x" * 101])
async def test_patch_rejects_invalid_title(client: AsyncClient, title: str) -> None:
    response = await client.patch(f"/conversations/{uuid4()}", json={"title": title})

    assert response.status_code == 422


@pytest.mark.integration
async def test_patch_unknown_conversation_is_404(client: AsyncClient) -> None:
    response = await client.patch(f"/conversations/{uuid4()}", json={"title": "Name"})

    assert response.status_code == 404
