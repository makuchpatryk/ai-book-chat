"""with_heartbeat must ping during slow steps without killing the source."""

import asyncio

from app.domain.events import TokenProduced
from app.interfaces.http.sse import with_heartbeat


async def _slow_source():
    await asyncio.sleep(0.25)
    yield TokenProduced(text="a")
    yield TokenProduced(text="b")


async def test_slow_source_survives_heartbeats():
    frames = [frame async for frame in with_heartbeat(_slow_source(), interval=0.05)]

    assert frames.count(": ping\n\n") >= 2
    tokens = [f for f in frames if f.startswith("event: token")]
    assert len(tokens) == 2
