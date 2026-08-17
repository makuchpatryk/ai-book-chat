"""Query rewriting for follow-up questions using prior conversation context."""

import logging
from typing import Any, Protocol

import anyio

from app.chat.prompts import REWRITE_PROMPT
from app.config import Settings, get_settings
from app.llm.client import build_sync_client, message_text

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


class LLMRewriter:
    """Query rewriter over an OpenAI-compatible chat-completions endpoint."""

    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self._model = model

    def rewrite(self, question: str, history: str) -> str:
        """Rewrite question via the configured endpoint. Never raises."""
        try:
            completion = self._client.chat.completions.create(
                model=self._model,
                max_tokens=512,
                messages=[
                    {"role": "system", "content": REWRITE_PROMPT},
                    {
                        "role": "user",
                        "content": f"{history}\n\nLatest question: {question}",
                    },
                ],
            )
            result = message_text(completion.choices[0])
            if not result or len(result) > 500:
                logger.warning("rewrite produced empty or oversized result, using original")
                return question
            usage = getattr(completion, "usage", None)
            logger.info(
                "rewrite usage",
                extra={
                    "phase": "rewrite",
                    "model": self._model,
                    "input_tokens": getattr(usage, "prompt_tokens", None),
                    "output_tokens": getattr(usage, "completion_tokens", None),
                },
            )
            return result
        except Exception as e:
            logger.warning(f"rewrite failed ({e}), using original question")
            return question


def build_rewriter(settings: Settings | None = None) -> Rewriter:
    """Real rewriter when LLM_TOKEN is set, pass-through fake otherwise."""
    settings = settings or get_settings()

    if not settings.llm_token:
        logger.warning("LLM_TOKEN unset — using FakeRewriter; no query rewriting")
        return FakeRewriter()

    return LLMRewriter(client=build_sync_client(settings), model=settings.chat_rewrite_model)


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
