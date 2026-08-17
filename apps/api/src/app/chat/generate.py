"""LLM text generation with streaming.

Adapter pattern: single Generator interface, an OpenAI-protocol implementation
and a deterministic offline fallback for when no token is configured.
"""

import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol

from app.config import Settings, get_settings
from app.ingestion.tokenizer import count_tokens
from app.llm.client import build_async_client, is_billing_error

logger = logging.getLogger(__name__)

# Matches the "[Page 12-14]" headers the chat pipeline puts before each chunk.
_PAGE_RANGE_RE = re.compile(r"\[Page (\d+)-(\d+)\]")


@dataclass
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class TextDelta:
    text: str


@dataclass
class GenerationDone:
    input_tokens: int | None
    output_tokens: int | None
    stop_reason: str | None = None
    # True when the counts are a local tiktoken estimate because the provider
    # returned no usage block — the cost log must not present them as billed.
    estimated: bool = False


StreamEvent = TextDelta | GenerationDone


class Generator(Protocol):
    # Not `async def`: the implementations are async generators, so the method
    # returns the iterator directly rather than a coroutine yielding one.
    def stream(self, system: str, messages: list[ChatMessage]) -> AsyncIterator[StreamEvent]:
        """Yield text deltas, then exactly one GenerationDone."""
        ...


class FakeGenerator:
    """Deterministic offline generator: yields page numbers and a fixed sentence.

    It mirrors the two shapes the real generator is prompted for — a grounded
    answer with page citations, and an ungrounded one that names the gap and
    then speaks from general knowledge — so offline runs exercise both paths.
    """

    def __init__(self, page_numbers: list[int] | None = None) -> None:
        self._page_numbers = page_numbers or []

    async def stream(
        self, system: str, messages: list[ChatMessage]
    ) -> AsyncIterator[StreamEvent]:
        """Yield text word by word, then done event."""
        # The pipeline builds one generator for every turn, so the pages come
        # from the context in `system` unless a caller pinned them explicitly.
        pages = self._page_numbers or [
            int(n) for match in _PAGE_RANGE_RE.findall(system) for n in match
        ]
        if pages:
            page_str = ", ".join(f"p.{p}" for p in sorted(set(pages)))
            text = f"Based on {page_str}: The document discusses this topic across multiple sections."
        else:
            text = (
                "This document doesn't cover the question. From general knowledge: "
                "no offline answer is available, so run with LLM_TOKEN set for a real one."
            )

        for word in text.split():
            yield TextDelta(text=word + " ")

        yield GenerationDone(input_tokens=None, output_tokens=None)


class LLMGenerator:
    """Streaming generator over an OpenAI-compatible chat-completions endpoint."""

    def __init__(self, client: Any, model: str, max_tokens: int) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._warned_missing_usage = False

    async def stream(
        self, system: str, messages: list[ChatMessage]
    ) -> AsyncIterator[StreamEvent]:
        """Stream text deltas from the endpoint, then yield GenerationDone."""
        payload = [
            {"role": "system", "content": system},
            *({"role": m.role, "content": m.content} for m in messages),
        ]
        finish_reason: str | None = None
        usage: Any = None
        answer = ""

        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                max_tokens=self._max_tokens,
                messages=payload,
                stream=True,
                # Without this many gateways send no usage block at all, and the
                # cost measurement dies silently.
                stream_options={"include_usage": True},
            )
            async for chunk in stream:
                chunk_usage = getattr(chunk, "usage", None)
                if chunk_usage is not None:
                    usage = chunk_usage
                choices = getattr(chunk, "choices", None)
                if not choices:
                    # The usage-only trailing chunk carries an empty `choices`.
                    continue
                choice = choices[0]
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
                # `reasoning_content` / `reasoning` deltas are the model thinking
                # out loud; only `content` belongs in the answer.
                delta_text = getattr(choice.delta, "content", None)
                if delta_text:
                    answer += delta_text
                    yield TextDelta(text=delta_text)
        except Exception as exc:
            if is_billing_error(exc):
                logger.error(
                    "llm request rejected for billing",
                    extra={"phase": "generate", "model": self._model},
                )
                raise RuntimeError(
                    "LLM credits exhausted (HTTP 402) — add credits or point "
                    "LLM_BASE_URL at another endpoint"
                ) from exc
            raise

        input_tokens = getattr(usage, "prompt_tokens", None)
        output_tokens = getattr(usage, "completion_tokens", None)
        if input_tokens is None or output_tokens is None:
            if not self._warned_missing_usage:
                logger.warning(
                    f"no usage returned by {self._model}; token counts are local estimates"
                )
                self._warned_missing_usage = True
            prompt_text = system + "".join(m.content for m in messages)
            yield GenerationDone(
                input_tokens=count_tokens(prompt_text),
                output_tokens=count_tokens(answer),
                stop_reason=finish_reason,
                estimated=True,
            )
            return

        yield GenerationDone(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            stop_reason=finish_reason,
        )


def build_generator(settings: Settings | None = None) -> Generator:
    """Real generator when LLM_TOKEN is set, deterministic fake otherwise."""
    settings = settings or get_settings()

    if not settings.llm_token:
        logger.warning("LLM_TOKEN unset — using FakeGenerator; results will be deterministic")
        return FakeGenerator()

    return LLMGenerator(
        client=build_async_client(settings),
        model=settings.chat_model,
        max_tokens=settings.chat_max_tokens,
    )
