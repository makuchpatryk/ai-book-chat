"""SSE frame generation and heartbeat."""

import asyncio
import json
from collections.abc import AsyncIterator

from app.domain.events import (
    AnswerEvent,
    AnswerCompleted,
    AnswerFailed,
    SourcesFound,
    TokenProduced,
)


def to_frame(event: AnswerEvent) -> str:
    """Convert a domain event to an SSE frame."""
    if isinstance(event, SourcesFound):
        payload = {
            "results": [
                {
                    "chunk_id": str(c.chunk_id),
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                    "score": c.score,
                    "section_title": c.section_title,
                    "snippet": c.snippet,
                }
                for c in event.citations
            ],
            "pages": event.pages,
        }
        return f"event: sources\ndata: {json.dumps(payload)}\n\n"

    elif isinstance(event, TokenProduced):
        payload = {"text": event.text}
        return f"event: token\ndata: {json.dumps(payload)}\n\n"

    elif isinstance(event, AnswerCompleted):
        payload = {
            "message_id": str(event.message_id),
            "grounded": event.grounded,
            "truncated": event.truncated,
        }
        return f"event: done\ndata: {json.dumps(payload)}\n\n"

    elif isinstance(event, AnswerFailed):
        payload = {"detail": event.detail}
        return f"event: error\ndata: {json.dumps(payload)}\n\n"

    else:
        raise ValueError(f"unknown event type: {type(event)}")


async def with_heartbeat(
    source: AsyncIterator[AnswerEvent],
    interval: float = 15.0,
) -> AsyncIterator[str]:
    """Wrap an event stream with heartbeat pings.

    Yields SSE frames (strings). If no event arrives within interval seconds,
    yields a heartbeat ping (`: ping` comment).
    """
    # `asyncio.wait_for` would cancel `source.__anext__()` on timeout, killing the
    # generator mid-flight (the stream would then end with no answer). Keep the
    # pending task alive across heartbeats and only wait on it.
    pending: asyncio.Future[AnswerEvent] | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(source.__anext__())
            done, _ = await asyncio.wait({pending}, timeout=interval)
            if not done:
                yield ": ping\n\n"
                continue
            task, pending = pending, None
            try:
                event = task.result()
            except StopAsyncIteration:
                break
            yield to_frame(event)
    finally:
        if pending is not None:
            pending.cancel()
