"""Query rewriting for follow-up questions using prior conversation context."""

import logging
from typing import Any, Protocol

import anyio

from app.chat.prompts import REWRITE_PROMPT
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class Rewriter(Protocol):
    def rewrite(self, question: str, history: str) -> str:
        """Rewrite a question to be standalone, using history for context."""
        ...


class FakeRewriter:
    """Deterministic offline rewriter: echoes the question."""

    def rewrite(self, question: str, history: str) -> str:
        """Return question unchanged."""
        return question


class AnthropicRewriter:
    """Anthropic Claude query rewriter."""

    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self._model = model

    def rewrite(self, question: str, history: str) -> str:
        """Rewrite question using Claude."""
        try:
            messages = [
                {
                    "role": "user",
                    "content": f"{history}\n\nLatest question: {question}",
                }
            ]
            message = self._client.messages.create(
                model=self._model,
                max_tokens=512,
                system=REWRITE_PROMPT,
                messages=messages,
            )
            result = message.content[0].text.strip()
            if not result or len(result) > 500:
                logger.warning("rewrite produced empty or oversized result, using original")
                return question
            return result
        except Exception as e:
            logger.warning(f"rewrite failed ({e}), using original question")
            return question


class MistralRewriter:
    """Mistral API query rewriter."""

    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self._model = model

    def rewrite(self, question: str, history: str) -> str:
        """Rewrite question using Mistral."""
        try:
            messages = [
                {
                    "role": "user",
                    "content": f"{history}\n\nLatest question: {question}",
                }
            ]
            message = self._client.messages.create(
                model=self._model,
                max_tokens=512,
                messages=messages,
            )
            result = message.content[0].text.strip()
            if not result or len(result) > 500:
                logger.warning("rewrite produced empty or oversized result, using original")
                return question
            return result
        except Exception as e:
            logger.warning(f"rewrite failed ({e}), using original question")
            return question


class OllamaRewriter:
    """Local Ollama query rewriter."""

    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    def rewrite(self, question: str, history: str) -> str:
        """Rewrite question using local Ollama."""
        import httpx

        try:
            prompt = f"{REWRITE_PROMPT}\n\n{history}\n\nLatest question: {question}"
            response = httpx.post(
                f"{self._base_url}/api/generate",
                json={"model": self._model, "prompt": prompt, "stream": False},
                timeout=60.0,
            )
            response.raise_for_status()
            result = response.json().get("response", "").strip()
            if not result or len(result) > 500:
                logger.warning("rewrite produced empty or oversized result, using original")
                return question
            return result
        except Exception as e:
            logger.warning(f"rewrite failed ({e}), using original question")
            return question


def build_rewriter(settings: Settings | None = None) -> Rewriter:
    """Build rewriter based on configured provider and API key."""
    settings = settings or get_settings()

    provider = settings.chat_provider.lower()
    api_key = settings.llm_api_key

    # Ollama doesn't need an API key (local)
    if provider == "ollama":
        return OllamaRewriter(
            base_url=settings.ollama_base_url, model=settings.chat_rewrite_model
        )

    # Fallback to FakeRewriter if no key is set for other providers
    if not api_key:
        logger.warning(
            "LLM_API_KEY unset — using FakeRewriter; no query rewriting"
        )
        return FakeRewriter()

    # Anthropic
    if provider == "anthropic":
        try:
            from anthropic import Anthropic

            return AnthropicRewriter(
                client=Anthropic(api_key=api_key),
                model=settings.chat_rewrite_model,
            )
        except ImportError:
            logger.error("anthropic package not installed; falling back to FakeRewriter")
            return FakeRewriter()

    # Mistral
    elif provider == "mistral":
        try:
            from mistralai import Mistral  # type: ignore[import-not-found]

            return MistralRewriter(
                client=Mistral(api_key=api_key),
                model=settings.chat_rewrite_model,
            )
        except ImportError:
            logger.error("mistralai package not installed; falling back to FakeRewriter")
            return FakeRewriter()

    # Unknown provider
    else:
        logger.warning(f"Unknown provider '{provider}'; falling back to FakeRewriter")
        return FakeRewriter()


async def rewrite(
    question: str, history: list[tuple[str, str]], rewriter: Rewriter, settings: Settings
) -> str:
    """Rewrite a question for standalone understanding, or return it verbatim if no history.

    Returns the rewritten question. Never raises; degrade-on-failure rule applies.
    """
    # Skip rewrite if no history (first turn of conversation)
    if not history:
        return question

    # Format history as "User: ... Assistant: ..."
    history_text = "\n".join(
        f"{'User' if role == 'user' else 'Assistant'}: {content}"
        for role, content in history
    )

    # Run rewrite in thread (sync API)
    try:
        result = await anyio.to_thread.run_sync(
            rewriter.rewrite, question, history_text
        )
        return result
    except Exception as e:
        logger.warning(f"rewrite exception ({e}), using original question")
        return question
