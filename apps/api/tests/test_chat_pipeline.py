"""Tests for chat pipeline correctness."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.generate import FakeGenerator, GenerationDone, TextDelta
from app.chat.pipeline import DoneEvent, answer
from app.db.models import Document, DocumentStatus, Conversation, Chunk, Section
from uuid import uuid4
import uuid


async def create_test_document_with_conversation(db: AsyncSession, settings):
    """Helper to create a READY document with conversation."""
    document = Document(
        id=uuid.uuid4(),
        filename="test.pdf",
        title="Test",
        page_count=5,
        status=DocumentStatus.READY,
        file_path=str(settings.upload_dir / "test.pdf"),
        content_hash="abc123",
        chunking_strategy="flat",
    )
    db.add(document)
    await db.flush()

    section = Section(
        id=uuid.uuid4(),
        document_id=document.id,
        title="Test",
        order_index=0,
        start_page=1,
        end_page=5,
    )
    db.add(section)
    await db.flush()

    chunk = Chunk(
        id=uuid.uuid4(),
        document_id=document.id,
        section_id=section.id,
        content="Test content",
        page_start=1,
        page_end=5,
        token_count=100,
        order_index=0,
        embedding=[0.1] * 1536,
    )
    db.add(chunk)

    conversation = Conversation(
        id=uuid.uuid4(), document_id=document.id, title="Test"
    )
    db.add(conversation)
    await db.commit()

    return document, conversation


@pytest.mark.asyncio
async def test_pipeline_done_event_structure(
    app_session: AsyncSession, settings
):
    """Test that DoneEvent has correct fields (no message_id)."""
    document, conversation = await create_test_document_with_conversation(
        app_session, settings
    )

    generator = FakeGenerator()
    rewriter = type("FakeRewriter", (), {"rewrite": lambda *a: "test"})()

    events = []
    async for event in answer(
        app_session, conversation.id, "test query", generator, rewriter, settings
    ):
        events.append(event)

    done_events = [e for e in events if isinstance(e, DoneEvent)]
    assert len(done_events) == 1

    done = done_events[0]
    assert hasattr(done, "grounded")
    assert hasattr(done, "truncated")
    assert not hasattr(done, "message_id")


@pytest.mark.asyncio
async def test_pipeline_recent_turns_cached(
    app_session: AsyncSession, settings, monkeypatch
):
    """Test that recent_turns is called only once, not twice."""
    document, conversation = await create_test_document_with_conversation(
        app_session, settings
    )

    call_count = 0

    from app.services import conversations

    original_recent_turns = conversations.recent_turns

    async def tracked_recent_turns(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return await original_recent_turns(*args, **kwargs)

    monkeypatch.setattr("app.chat.pipeline.conv_service.recent_turns", tracked_recent_turns)

    generator = FakeGenerator()
    rewriter = type("FakeRewriter", (), {"rewrite": lambda *a: "test"})()

    async for _ in answer(
        app_session, conversation.id, "test query", generator, rewriter, settings
    ):
        pass

    assert call_count == 1, f"recent_turns should be called once, was called {call_count} times"
