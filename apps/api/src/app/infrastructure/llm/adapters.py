"""LLM adapter implementations."""

import json
import logging
import re
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from app.domain.ports.llm import AnswerGenerator, DocumentDescriber, QueryRewriter, Reranker
from app.domain.values.messages import Turn
from app.domain.values.overview import DocumentOverview, OverviewSection
from app.infrastructure.config.settings import Settings

logger = logging.getLogger(__name__)

REWRITE_PROMPT = """Rewrite the user's latest message as a standalone question that makes sense
without the conversation history. Resolve pronouns and implicit references against the earlier
turns. Do not answer it. Return only the rewritten question."""

SCORING_PROMPT = """You score passages from a single book for relevance to a reader's question.
For each numbered passage return an integer 0-10:
  0-2  unrelated to the question
  3-5  same topic, does not answer the question
  6-8  contains part of the answer
  9-10 directly answers the question
Judge only the passage text. Never infer content that is not present.
Return one score per passage, in the order given.
Reply with JSON only, shaped {"passages": [{"index": 0, "score": 7}]}, one entry per passage, \
using the passage's bracketed number as "index"."""

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json_object(text: str) -> dict:
    """Parse the JSON object in `text`, tolerating markdown fences and prose around it."""
    fence = _JSON_FENCE.search(text)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"no JSON object in response: {text[:200]!r}")
    return json.loads(text[start : end + 1])


class OpenAIGenerator(AnswerGenerator):
    """OpenAI-compatible answer generator."""

    def __init__(self, client: AsyncOpenAI, model: str, max_tokens: int):
        self.client = client
        self.model = model
        self.max_tokens = max_tokens

    def stream(self, system: str, turns: list[Turn]) -> AsyncIterator[str]:
        """Stream completion tokens."""
        messages = [{"role": "system", "content": system}]
        for turn in turns:
            messages.append({"role": turn.role.value, "content": turn.content})

        async def _stream() -> AsyncIterator[str]:
            stream = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=messages,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        return _stream()


class FakeGenerator(AnswerGenerator):
    """Fake generator for testing (deterministic)."""

    def stream(self, system: str, turns: list[Turn]) -> AsyncIterator[str]:
        """Yield fake tokens."""
        async def _fake() -> AsyncIterator[str]:
            yield "This is a fake answer. "
            yield "It does not use the LLM. "
            yield "Useful for testing."

        return _fake()


class OpenAIRewriter(QueryRewriter):
    """OpenAI-compatible query rewriter."""

    def __init__(self, client: AsyncOpenAI, model: str):
        self.client = client
        self.model = model

    async def rewrite(self, question: str, history: list[Turn]) -> str:
        """Make a follow-up question standalone. Returns it unchanged on any doubt."""
        # First turn: nothing to resolve, and an LLM call can only make it worse.
        if not history:
            return question

        history_text = "\n".join(
            f"{'User' if turn.role.value == 'user' else 'Assistant'}: {turn.content}"
            for turn in history[-4:]
        )
        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=512,
            messages=[
                {"role": "system", "content": REWRITE_PROMPT},
                {
                    "role": "user",
                    "content": f"{history_text}\n\nLatest question: {question}",
                },
            ],
        )
        result = (response.choices[0].message.content or "").strip()
        if not result or len(result) > 500:
            logger.warning("rewrite produced empty or oversized result, using original")
            return question
        return result


class FakeRewriter(QueryRewriter):
    """Fake rewriter for testing."""

    async def rewrite(self, question: str, history: list[Turn]) -> str:
        """Return question unchanged."""
        return question


class OpenAIReranker(Reranker):
    """OpenAI-compatible passage reranker (scores 0-10, one call for all passages)."""

    def __init__(self, client: AsyncOpenAI, model: str, max_tokens: int):
        self.client = client
        self.model = model
        self.max_tokens = max_tokens

    async def score(self, query: str, passages: list[str]) -> list[int]:
        """Score passages 0-10 in input order. Raises if the reply is unusable."""
        numbered = "\n".join(f"[{i}] {p[:1200]}" for i, p in enumerate(passages))
        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": SCORING_PROMPT},
                {"role": "user", "content": f"{query}\n\n{numbered}"},
            ],
        )
        payload = _extract_json_object(response.choices[0].message.content or "")
        by_index = {int(p["index"]): int(p["score"]) for p in payload["passages"]}
        if set(by_index) != set(range(len(passages))):
            raise ValueError(f"rerank indices {sorted(by_index)} != expected 0..{len(passages) - 1}")
        return [max(0, min(10, by_index[i])) for i in range(len(passages))]


class FakeReranker(Reranker):
    """Fake reranker for testing."""

    async def score(self, query: str, passages: list[str]) -> list[int]:
        """Return uniform scores."""
        return [50] * len(passages)


class OpenAIDescriber(DocumentDescriber):
    """OpenAI-compatible document describer."""

    def __init__(self, client: AsyncOpenAI, model: str, max_tokens: int):
        self.client = client
        self.model = model
        self.max_tokens = max_tokens

    async def describe(
        self,
        title: str,
        author: str | None,
        section_titles: list[str],
        sample_text: str,
    ) -> DocumentOverview:
        """Generate a document overview from sampled text. Raises ValueError on invalid JSON."""
        author_line = f"Author: {author}\n" if author else ""
        sections_line = "Sections: " + ", ".join(section_titles) if section_titles else ""
        prompt = (
            f"Document Title: {title}\n"
            f"{author_line}"
            f"{sections_line}\n\n"
            f"Sample text from the document:\n{sample_text}\n\n"
            "Based on the above, generate a JSON object with:\n"
            "- summary (≤300 chars)\n"
            "- language (ISO 639-1, the document's language)\n"
            "- doc_type (e.g., 'Technical Manual', 'Novel', 'Academic Paper')\n"
            "- topics (list of 3-6 topics, as strings)\n"
            "- sections (list of {heading, body} objects, 3-6 sections)\n"
            "Reply JSON only."
        )

        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": "You are a document analyzer. Reply JSON only."},
                {"role": "user", "content": prompt},
            ],
        )
        content = response.choices[0].message.content or ""
        payload = _extract_json_object(content)

        raw_topics = payload.get("topics")
        raw_sections = payload.get("sections")
        if not isinstance(raw_sections, list):
            raise ValueError("response has no 'sections' list")

        summary = str(payload.get("summary") or "")[:300]
        language = str(payload.get("language") or "en")[:16]
        doc_type = str(payload.get("doc_type") or "")[:64]
        topics = [str(t)[:64] for t in raw_topics[:6]] if isinstance(raw_topics, list) else []
        sections_list = [
            OverviewSection(
                heading=str(s.get("heading") or "")[:256],
                body=str(s.get("body") or "")[:2048],
            )
            for s in raw_sections[:6]
            if isinstance(s, dict) and (s.get("heading") or s.get("body"))
        ]

        if len(sections_list) < 3:
            raise ValueError(f"expected 3+ sections, got {len(sections_list)}")

        return DocumentOverview(
            summary=summary,
            language=language,
            doc_type=doc_type,
            topics=topics,
            sections=sections_list,
        )


class FakeDescriber(DocumentDescriber):
    """Fake describer for testing (deterministic)."""

    async def describe(
        self,
        title: str,
        author: str | None,
        section_titles: list[str],
        sample_text: str,
    ) -> DocumentOverview:
        """Return a fake but structurally valid overview."""
        return DocumentOverview(
            summary=f"Fake summary of {title}.",
            language="en",
            doc_type="Book",
            topics=["topic1", "topic2", "topic3"],
            sections=[
                OverviewSection(heading="Introduction", body="This is the introduction."),
                OverviewSection(heading="Main Content", body="This is the main content."),
                OverviewSection(heading="Conclusion", body="This is the conclusion."),
            ],
        )


def build_generator(settings: Settings) -> AnswerGenerator:
    """Build answer generator based on settings."""
    if not settings.llm_token:
        return FakeGenerator()
    client = AsyncOpenAI(api_key=settings.llm_token, base_url=settings.llm_base_url)
    return OpenAIGenerator(client, settings.chat_model, settings.chat_max_tokens)


def build_rewriter(settings: Settings) -> QueryRewriter:
    """Build query rewriter based on settings."""
    if not settings.llm_token:
        return FakeRewriter()
    client = AsyncOpenAI(api_key=settings.llm_token, base_url=settings.llm_base_url)
    return OpenAIRewriter(client, settings.chat_rewrite_model)


def build_reranker(settings: Settings) -> Reranker:
    """Build reranker based on settings."""
    if not settings.llm_token:
        return FakeReranker()
    client = AsyncOpenAI(api_key=settings.llm_token, base_url=settings.llm_base_url)
    return OpenAIReranker(client, settings.rerank_model, settings.rerank_max_tokens)


def build_describer(settings: Settings) -> DocumentDescriber:
    """Build document describer based on settings."""
    if not settings.llm_token:
        return FakeDescriber()
    client = AsyncOpenAI(api_key=settings.llm_token, base_url=settings.llm_base_url)
    return OpenAIDescriber(client, settings.describe_model, settings.describe_max_tokens)
