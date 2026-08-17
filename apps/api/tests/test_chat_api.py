"""Integration tests for chat SSE endpoint."""

import asyncio
import json
import uuid
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.chat.pipeline import DoneEvent, SourcesEvent, TokenEvent
from app.db.models import (
    Chunk,
    Conversation,
    Document,
    DocumentStatus,
    Message,
    MessageRole,
    MessageSource,
    Section,
)


async def create_ready_document(
    db: AsyncSession, settings
) -> tuple[Document, list[Chunk]]:
    """Create a READY document with chunks and sections for testing."""
    document = Document(
        id=uuid.uuid4(),
        filename="test.pdf",
        title="Test Document",
        page_count=10,
        status=DocumentStatus.READY,
        file_path=str(settings.upload_dir / "test.pdf"),
        # Unique per document: content_hash carries a unique index.
        content_hash=uuid.uuid4().hex,
        chunking_strategy="flat",
    )
    db.add(document)
    await db.flush()

    section = Section(
        id=uuid.uuid4(),
        document_id=document.id,
        title="Introduction",
        order_index=0,
        start_page=1,
        end_page=3,
    )
    db.add(section)
    await db.flush()

    chunks = []
    for i in range(3):
        chunk = Chunk(
            id=uuid.uuid4(),
            document_id=document.id,
            section_id=section.id,
            content=f"Sample text for chunk {i}. This discusses important concepts.",
            page_start=1 + i,
            page_end=1 + i,
            token_count=100,
            order_index=i,
            embedding=[0.1] * 768,
        )
        db.add(chunk)
        chunks.append(chunk)

    await db.commit()
    return document, chunks


def parse_sse(line: str) -> dict | None:
    """Parse a single SSE event."""
    if not line.strip():
        return None
    lines = line.split("\n")
    result = {}
    for line in lines:
        if line.startswith("event: "):
            result["event"] = line[7:].strip()
        elif line.startswith("data: "):
            data_str = line[6:].strip()
            if data_str:
                try:
                    result["data"] = json.loads(data_str)
                except json.JSONDecodeError:
                    pass
        elif line.startswith(": "):
            result["comment"] = True
    return result if result else None


async def parse_sse_stream(content: bytes) -> list[dict]:
    """Parse SSE stream into events."""
    events = []
    text = content.decode("utf-8")
    blocks = text.split("\n\n")
    for block in blocks:
        if block.strip():
            event = parse_sse(block)
            if event:
                events.append(event)
    return events


@pytest.mark.asyncio
async def test_chat_sse_event_order(
    client: AsyncClient, app_session: AsyncSession, fake_llm, settings
):
    """Test that SSE events arrive in correct order: sources, tokens, done."""
    document, chunks = await create_ready_document(app_session, settings)
    conversation = Conversation(
        id=uuid4(), document_id=document.id, title="Test"
    )
    app_session.add(conversation)
    await app_session.commit()

    response = await client.post(
        f"/conversations/{conversation.id}/messages",
        json={"content": "What is in this document?"},
    )

    assert response.status_code == 200
    events = await parse_sse_stream(response.content)

    event_types = [e.get("event") for e in events if "event" in e]
    assert "sources" in event_types
    assert "token" in event_types
    assert "done" in event_types

    sources_idx = event_types.index("sources")
    token_idx = event_types.index("token")
    done_idx = event_types.index("done")

    assert sources_idx < token_idx, "sources should come before tokens"
    assert token_idx < done_idx, "tokens should come before done"


@pytest.mark.asyncio
async def test_chat_sse_message_id_valid(
    client: AsyncClient, app_session: AsyncSession, fake_llm, settings
):
    """Test that done event contains a valid message_id that exists in DB."""
    document, chunks = await create_ready_document(app_session, settings)
    conversation = Conversation(
        id=uuid4(), document_id=document.id, title="Test"
    )
    app_session.add(conversation)
    await app_session.commit()

    response = await client.post(
        f"/conversations/{conversation.id}/messages",
        json={"content": "What is in this document?"},
    )

    assert response.status_code == 200
    events = await parse_sse_stream(response.content)

    done_events = [e for e in events if e.get("event") == "done"]
    assert len(done_events) == 1

    message_id = done_events[0]["data"]["message_id"]
    result = await app_session.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.order_index)
    )
    persisted = result.scalars().all()

    assert len(persisted) == 2
    assert str(persisted[-1].id) == message_id


@pytest.mark.asyncio
async def test_chat_sse_ungrounded_persists(
    client: AsyncClient, app_session: AsyncSession, fake_llm, settings
):
    """Test that ungrounded (no matching chunks) answer is persisted."""
    document, chunks = await create_ready_document(app_session, settings)
    conversation = Conversation(
        id=uuid4(), document_id=document.id, title="Test"
    )
    app_session.add(conversation)
    await app_session.commit()

    response = await client.post(
        f"/conversations/{conversation.id}/messages",
        json={"content": "Tell me about aliens"},
    )

    assert response.status_code == 200
    events = await parse_sse_stream(response.content)

    done_event = next((e for e in events if e.get("event") == "done"), None)
    assert done_event is not None
    assert done_event["data"]["grounded"] is False

    messages = await app_session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .options(selectinload(Message.sources))
        .order_by(Message.order_index)
    )
    all_messages = list(messages)

    assert len(all_messages) == 2
    assistant_msg = all_messages[-1]
    assert assistant_msg.grounded is False
    assert len(assistant_msg.sources) == 0


@pytest.mark.asyncio
async def test_chat_sse_error_event(
    client: AsyncClient, app_session: AsyncSession, settings, monkeypatch
):
    """Test that generator errors emit error event."""
    document, chunks = await create_ready_document(app_session, settings)
    conversation = Conversation(
        id=uuid4(), document_id=document.id, title="Test"
    )
    app_session.add(conversation)
    await app_session.commit()

    async def mock_answer(*args, **kwargs):
        yield TokenEvent(text="partial ")
        raise RuntimeError("Test error")

    monkeypatch.setattr("app.api.routes.conversations.answer", mock_answer)

    response = await client.post(
        f"/conversations/{conversation.id}/messages",
        json={"content": "What is in this document?"},
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "event: error" in content
    assert "Test error" in content


@pytest.mark.asyncio
async def test_chat_sse_persist_failure_ends_stream_cleanly(
    client: AsyncClient, app_session: AsyncSession, fake_llm, settings, monkeypatch
):
    """A failed save reports an error event instead of aborting the response body."""
    document, chunks = await create_ready_document(app_session, settings)
    conversation = Conversation(
        id=uuid4(), document_id=document.id, title="Test"
    )
    app_session.add(conversation)
    await app_session.commit()

    async def failing_persist(*args, **kwargs):
        raise RuntimeError("database is on fire")

    monkeypatch.setattr(
        "app.api.routes.conversations.persist_assistant_message", failing_persist
    )

    response = await client.post(
        f"/conversations/{conversation.id}/messages",
        json={"content": "What is in this document?"},
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    # Tokens still streamed, then a clean error frame instead of a truncated body.
    assert "event: token" in content
    assert "event: error" in content
    assert "event: done" not in content


@pytest.mark.asyncio
async def test_chat_sse_heartbeat(
    client: AsyncClient, app_session: AsyncSession, fake_llm, settings, monkeypatch
):
    """Test that heartbeat frames appear with slow generation."""
    document, chunks = await create_ready_document(app_session, settings)
    conversation = Conversation(
        id=uuid4(), document_id=document.id, title="Test"
    )
    app_session.add(conversation)
    await app_session.commit()

    # The route reads this off the injected Settings instance, not the class —
    # pydantic fields are not class attributes, so patch the instance.
    monkeypatch.setattr(settings, "chat_heartbeat_seconds", 0.05)

    async def slow_answer(*args, **kwargs):
        yield SourcesEvent(results=[], pages=[])
        await asyncio.sleep(0.1)
        yield TokenEvent(text="Hello ")
        await asyncio.sleep(0.1)
        yield TokenEvent(text="world")
        yield DoneEvent(grounded=False, truncated=False)

    monkeypatch.setattr("app.api.routes.conversations.answer", slow_answer)

    response = await client.post(
        f"/conversations/{conversation.id}/messages",
        json={"content": "What is in this document?"},
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    ping_count = content.count(": ping")
    assert ping_count >= 1, "Should have at least one heartbeat ping"


@pytest.mark.asyncio
async def test_chat_document_not_ready(
    client: AsyncClient, app_session: AsyncSession
):
    """Test that chat on non-READY document returns 409."""
    document = Document(
        id=uuid4(),
        filename="test.pdf",
        title="Test Document",
        status=DocumentStatus.PENDING,
        file_path="/tmp/test.pdf",
        content_hash=uuid.uuid4().hex,
    )
    app_session.add(document)
    await app_session.flush()

    conversation = Conversation(id=uuid4(), document_id=document.id, title="Test")
    app_session.add(conversation)
    await app_session.commit()

    response = await client.post(
        f"/conversations/{conversation.id}/messages",
        json={"content": "What is in this document?"},
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_get_messages_returns_section_title(
    client: AsyncClient, app_session: AsyncSession, settings
):
    """History reads the chunk's section; a lazy load there raises MissingGreenlet."""
    document, chunks = await create_ready_document(app_session, settings)
    conversation = Conversation(id=uuid4(), document_id=document.id, title="Test")
    app_session.add(conversation)
    await app_session.flush()

    assistant = Message(
        id=uuid4(),
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content="An answer.",
        grounded=True,
        truncated=False,
        order_index=0,
    )
    app_session.add(assistant)
    await app_session.flush()

    app_session.add(
        MessageSource(
            message_id=assistant.id,
            chunk_id=chunks[0].id,
            score=9,
            rank=0,
        )
    )
    await app_session.commit()

    response = await client.get(f"/conversations/{conversation.id}/messages")

    assert response.status_code == 200
    sources = response.json()[0]["sources"]
    assert [s["section_title"] for s in sources] == ["Introduction"]


@pytest.mark.asyncio
async def test_chat_unknown_conversation(
    client: AsyncClient, fake_llm
):
    """Test that chat on unknown conversation returns 404."""
    response = await client.post(
        f"/conversations/{uuid4()}/messages",
        json={"content": "What is in this document?"},
    )

    assert response.status_code == 404
