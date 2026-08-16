"""Generator adapters."""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest

from app.chat.generate import (
    ChatMessage,
    FakeGenerator,
    GenerationDone,
    HFGenerator,
    TextDelta,
    build_generator,
)
from app.config import Settings


def _chunk(
    content: str | None = None,
    finish_reason: str | None = None,
    usage: Any = None,
    reasoning: str | None = None,
) -> SimpleNamespace:
    delta = SimpleNamespace(content=content, reasoning_content=reasoning)
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)],
        usage=usage,
    )


def _usage_only_chunk(prompt_tokens: int, completion_tokens: int) -> SimpleNamespace:
    """What the router sends last: usage, and an empty `choices`."""
    return SimpleNamespace(
        choices=[],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
        ),
    )


class _FakeCompletions:
    def __init__(self, chunks: list[Any], error: Exception | None = None) -> None:
        self._chunks = chunks
        self._error = error
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> AsyncIterator[Any]:
        self.kwargs = kwargs
        if self._error:
            raise self._error

        async def _stream() -> AsyncIterator[Any]:
            for chunk in self._chunks:
                yield chunk

        return _stream()


class _FakeClient:
    def __init__(self, chunks: list[Any], error: Exception | None = None) -> None:
        self.completions = _FakeCompletions(chunks, error)
        self.chat = SimpleNamespace(completions=self.completions)


async def _collect(generator: HFGenerator, system: str = "sys") -> list[Any]:
    return [
        event
        async for event in generator.stream(system, [ChatMessage(role="user", content="hi")])
    ]


async def test_hf_generator_streams_deltas_then_one_done() -> None:
    client = _FakeClient(
        [
            _chunk(content="Hello"),
            _chunk(content=" world"),
            _chunk(finish_reason="stop"),
            _usage_only_chunk(1200, 34),
        ]
    )
    events = await _collect(HFGenerator(client, "openai/gpt-oss-120b", 2048))

    assert [e.text for e in events if isinstance(e, TextDelta)] == ["Hello", " world"]
    done = [e for e in events if isinstance(e, GenerationDone)]
    assert len(done) == 1
    assert done[0] == GenerationDone(input_tokens=1200, output_tokens=34, stop_reason="stop")
    assert done[0].estimated is False


async def test_hf_generator_sends_the_system_prompt_as_a_message_and_asks_for_usage() -> None:
    client = _FakeClient([_chunk(content="hi", finish_reason="stop"), _usage_only_chunk(1, 1)])
    await _collect(HFGenerator(client, "m", 2048, extra_headers={"X-HF-Bill-To": "org"}))

    kwargs = client.completions.kwargs
    assert kwargs["messages"][0] == {"role": "system", "content": "sys"}
    assert kwargs["messages"][1] == {"role": "user", "content": "hi"}
    assert kwargs["stream_options"] == {"include_usage": True}
    assert kwargs["extra_headers"] == {"X-HF-Bill-To": "org"}


async def test_hf_generator_propagates_a_length_stop() -> None:
    client = _FakeClient(
        [_chunk(content="cut off", finish_reason="length"), _usage_only_chunk(5, 6)]
    )
    events = await _collect(HFGenerator(client, "m", 2048))

    assert events[-1].stop_reason == "length"


async def test_hf_generator_estimates_tokens_when_usage_is_absent() -> None:
    client = _FakeClient([_chunk(content="some words here", finish_reason="stop")])
    events = await _collect(HFGenerator(client, "m", 2048))

    done = events[-1]
    assert isinstance(done, GenerationDone)
    assert done.estimated is True
    assert done.input_tokens and done.output_tokens


async def test_hf_generator_ignores_reasoning_deltas() -> None:
    client = _FakeClient(
        [
            _chunk(reasoning="the user asked about X"),
            _chunk(content="answer"),
            _chunk(finish_reason="stop"),
            _usage_only_chunk(3, 4),
        ]
    )
    events = await _collect(HFGenerator(client, "m", 2048))

    assert [e.text for e in events if isinstance(e, TextDelta)] == ["answer"]


async def test_hf_generator_reports_exhausted_credits_clearly() -> None:
    class _PaymentRequired(Exception):
        status_code = 402

    client = _FakeClient([], error=_PaymentRequired("insufficient credits"))

    with pytest.raises(RuntimeError, match="402"):
        await _collect(HFGenerator(client, "m", 2048))


def test_build_generator_uses_huggingface_by_default_with_a_token() -> None:
    generator = build_generator(Settings(hf_token="hf_test"))

    assert isinstance(generator, HFGenerator)


def test_build_generator_falls_back_to_the_fake_without_a_token() -> None:
    assert isinstance(build_generator(Settings(hf_token=None, llm_api_key=None)), FakeGenerator)


def test_build_generator_accepts_the_shared_llm_key() -> None:
    assert isinstance(build_generator(Settings(llm_api_key="sk-test")), HFGenerator)
