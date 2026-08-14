"""LLM text generation with streaming.

Adapter pattern: single Generator interface, multiple provider implementations.
Supports Anthropic, Mistral, Ollama, and deterministic offline fallback.
"""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


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


StreamEvent = TextDelta | GenerationDone


class Generator(Protocol):
    async def stream(
        self, system: str, messages: list[ChatMessage]
    ) -> AsyncIterator[StreamEvent]:
        """Yield text deltas, then exactly one GenerationDone."""
        ...


class FakeGenerator:
    """Deterministic offline generator: yields page numbers and a fixed sentence."""

    def __init__(self, page_numbers: list[int] | None = None) -> None:
        self._page_numbers = page_numbers or []

    async def stream(
        self, system: str, messages: list[ChatMessage]
    ) -> AsyncIterator[StreamEvent]:
        """Yield text word by word, then done event."""
        if self._page_numbers:
            page_str = ", ".join(f"p.{p}" for p in sorted(set(self._page_numbers)))
            text = f"Based on {page_str}: The document discusses this topic across multiple sections."
        else:
            text = "I couldn't find information about this in the document."

        for word in text.split():
            yield TextDelta(text=word + " ")

        yield GenerationDone(input_tokens=None, output_tokens=None)


class AnthropicGenerator:
    """Anthropic Claude generator with async streaming."""

    def __init__(self, client: Any, model: str, max_tokens: int) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    async def stream(
        self, system: str, messages: list[ChatMessage]
    ) -> AsyncIterator[StreamEvent]:
        """Stream text deltas from Claude, then yield GenerationDone."""
        async with self._client.messages.stream(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            thinking={"type": "disabled"},
            messages=[{"role": m.role, "content": m.content} for m in messages],
        ) as stream:
            async for text in stream.text_stream:
                yield TextDelta(text=text)
            final = await stream.get_final_message()

        yield GenerationDone(
            input_tokens=final.usage.input_tokens,
            output_tokens=final.usage.output_tokens,
        )


class MistralGenerator:
    """Mistral API generator with async streaming."""

    def __init__(self, client: Any, model: str, max_tokens: int) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    async def stream(
        self, system: str, messages: list[ChatMessage]
    ) -> AsyncIterator[StreamEvent]:
        """Stream text deltas from Mistral, then yield GenerationDone."""
        import httpx

        formatted_messages = [{"role": m.role, "content": m.content} for m in messages]

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                "https://api.mistral.ai/v1/chat/completions",
                json={
                    "model": self._model,
                    "messages": formatted_messages,
                    "max_tokens": self._max_tokens,
                    "stream": True,
                },
                headers={"Authorization": f"Bearer {self._client.api_key}"},
                timeout=60.0,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str and data_str != "[DONE]":
                            import json
                            try:
                                data = json.loads(data_str)
                                if data.get("choices"):
                                    delta = data["choices"][0].get("delta", {})
                                    if delta.get("content"):
                                        yield TextDelta(text=delta["content"])
                            except Exception:
                                pass

        yield GenerationDone(input_tokens=None, output_tokens=None)


class OllamaGenerator:
    """Local Ollama generator via HTTP."""

    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def stream(
        self, system: str, messages: list[ChatMessage]
    ) -> AsyncIterator[StreamEvent]:
        """Stream from local Ollama instance."""
        import httpx
        import json

        prompt = system + "\n\n" + "\n".join(
            f"{m.role}: {m.content}" for m in messages
        )

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/api/generate",
                json={"model": self._model, "prompt": prompt, "stream": True},
                timeout=60.0,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.strip():
                        try:
                            data = json.loads(line)
                            if data.get("response"):
                                yield TextDelta(text=data["response"])
                        except Exception:
                            pass

        yield GenerationDone(input_tokens=None, output_tokens=None)


def build_generator(settings: Settings | None = None) -> Generator:
    """Build generator based on configured provider and API key."""
    settings = settings or get_settings()

    provider = settings.chat_provider.lower()
    api_key = settings.llm_api_key

    # Ollama doesn't need an API key (local)
    if provider == "ollama":
        return OllamaGenerator(
            base_url=settings.ollama_base_url, model=settings.chat_model
        )

    # Fallback to FakeGenerator if no key is set for other providers
    if not api_key:
        logger.warning(
            "LLM_API_KEY unset — using FakeGenerator; results will be deterministic"
        )
        return FakeGenerator()

    # Anthropic
    if provider == "anthropic":
        try:
            from anthropic import AsyncAnthropic

            return AnthropicGenerator(
                client=AsyncAnthropic(api_key=api_key),
                model=settings.chat_model,
                max_tokens=settings.chat_max_tokens,
            )
        except ImportError:
            logger.error("anthropic package not installed; falling back to FakeGenerator")
            return FakeGenerator()

    # Mistral
    elif provider == "mistral":
        try:
            from mistralai import Mistral  # type: ignore[import-not-found]

            return MistralGenerator(
                client=Mistral(api_key=api_key),
                model=settings.chat_model,
                max_tokens=settings.chat_max_tokens,
            )
        except ImportError:
            logger.error("mistralai package not installed; falling back to FakeGenerator")
            return FakeGenerator()

    # Unknown provider
    else:
        logger.warning(f"Unknown provider '{provider}'; falling back to FakeGenerator")
        return FakeGenerator()
