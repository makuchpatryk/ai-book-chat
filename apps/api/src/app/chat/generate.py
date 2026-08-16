"""LLM text generation with streaming.

Adapter pattern: single Generator interface, multiple provider implementations.
Supports Hugging Face Inference Providers, Anthropic, Mistral, Ollama, and a
deterministic offline fallback.
"""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol

from app.config import Settings, get_settings
from app.ingestion.tokenizer import count_tokens
from app.llm.hf_client import build_hf_async_client, hf_api_key, hf_extra_headers, is_billing_error

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


class HFGenerator:
    """Hugging Face Inference Providers generator (OpenAI-compatible router)."""

    def __init__(
        self,
        client: Any,
        model: str,
        max_tokens: int,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._extra_headers = extra_headers or {}
        self._warned_missing_usage = False

    async def stream(
        self, system: str, messages: list[ChatMessage]
    ) -> AsyncIterator[StreamEvent]:
        """Stream text deltas from the router, then yield GenerationDone."""
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
                # Without this the router never sends a usage block at all, and
                # the cost measurement this provider exists for dies silently.
                stream_options={"include_usage": True},
                extra_headers=self._extra_headers,
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
                    "huggingface request rejected for billing",
                    extra={"phase": "generate", "provider": "huggingface", "model": self._model},
                )
                raise RuntimeError(
                    "Hugging Face Inference credits exhausted (HTTP 402) — add credits "
                    "or point CHAT_PROVIDER at another provider"
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
            stop_reason=final.stop_reason,
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

    # Hugging Face has its own key, falling back to LLM_API_KEY
    if provider == "huggingface":
        if not hf_api_key(settings):
            logger.warning("HF_TOKEN unset — using FakeGenerator; results will be deterministic")
            return FakeGenerator()
        return HFGenerator(
            client=build_hf_async_client(settings),
            model=settings.chat_model,
            max_tokens=settings.chat_max_tokens,
            extra_headers=hf_extra_headers(settings),
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
