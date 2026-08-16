"""Hugging Face Inference Providers transport.

Chat, rewrite and re-rank all speak the OpenAI chat-completions protocol against
the HF router, so the only place that knows the router exists is this module.
Embeddings take a different path — the router's `/v1` surface is chat-only.

The response-cleaning helpers are not decoration: with `:cheapest` routing the
answering model changes between calls, and open-weight models routinely wrap
their output in a reasoning preamble or a markdown fence where Claude's
structured-output API returned a parsed object.
"""

import logging
import re
from typing import Any

from openai import AsyncOpenAI, OpenAI

from app.config import Settings

logger = logging.getLogger(__name__)

HF_ROUTER_BASE_URL = "https://router.huggingface.co/v1"

_REASONING_BLOCK = re.compile(
    r"<(think|thinking|reasoning)\b[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE
)
_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)

# 402 is "out of credits" — a hard billing failure, not a transient one.
_BILLING_STATUS = 402


def hf_api_key(settings: Settings) -> str | None:
    """HF_TOKEN, falling back to LLM_API_KEY so single-key deployments keep working."""
    return settings.hf_token or settings.llm_api_key


def hf_extra_headers(settings: Settings) -> dict[str, str]:
    """`X-HF-Bill-To` when an org is configured, so usage is billed to it."""
    if settings.hf_bill_to:
        return {"X-HF-Bill-To": settings.hf_bill_to}
    return {}


def build_hf_sync_client(settings: Settings) -> OpenAI:
    return OpenAI(api_key=hf_api_key(settings), base_url=settings.hf_base_url)


def build_hf_async_client(settings: Settings) -> AsyncOpenAI:
    return AsyncOpenAI(api_key=hf_api_key(settings), base_url=settings.hf_base_url)


def is_billing_error(exc: BaseException) -> bool:
    """True for HTTP 402 — retrying a spent balance only delays the failure."""
    return getattr(exc, "status_code", None) == _BILLING_STATUS


def strip_reasoning(text: str) -> str:
    """Drop `<think>…</think>` / `<reasoning>…</reasoning>` blocks."""
    return _REASONING_BLOCK.sub("", text).strip()


def extract_json_object(text: str) -> str:
    """Return the first balanced `{…}` span, unwrapping a markdown fence first.

    Raises ValueError when there is no object to find.
    """
    fence = _JSON_FENCE.search(text)
    if fence:
        text = fence.group(1)

    start = text.find("{")
    if start == -1:
        raise ValueError(f"no JSON object in response: {text[:200]!r}")

    depth = 0
    in_string = False
    escaped = False
    for position in range(start, len(text)):
        char = text[position]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : position + 1]

    raise ValueError(f"unbalanced JSON object in response: {text[:200]!r}")


def message_text(choice: Any) -> str:
    """Assistant text off a chat completion choice, reasoning stripped."""
    return strip_reasoning(choice.message.content or "")
