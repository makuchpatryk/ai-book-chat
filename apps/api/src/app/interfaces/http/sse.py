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
    while True:
        try:
            event = await asyncio.wait_for(source.__anext__(), timeout=interval)
            yield to_frame(event)
        except asyncio.TimeoutError:
            yield ": ping\n\n"
        except StopAsyncIteration:
            break
