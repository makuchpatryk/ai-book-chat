"""LLM adapter implementations."""

from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from app.domain.ports.llm import AnswerGenerator, QueryRewriter, Reranker
from app.domain.values.messages import Turn
from app.infrastructure.config.settings import Settings


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
            async with self.client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=messages,
            ) as stream:
                async for text in stream.text_stream:
                    yield text

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
        """Rewrite question based on history."""
        messages = []
        for turn in history[-4:]:
            messages.append({"role": turn.role.value, "content": turn.content})
        messages.append({"role": "user", "content": question})

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=256,
            messages=messages,
        )
        return response.content[0].text


class FakeRewriter(QueryRewriter):
    """Fake rewriter for testing."""

    async def rewrite(self, question: str, history: list[Turn]) -> str:
        """Return question unchanged."""
        return question


class OpenAIReranker(Reranker):
    """OpenAI-compatible passage reranker."""

    def __init__(self, client: AsyncOpenAI, model: str):
        self.client = client
        self.model = model

    async def score(self, query: str, passages: list[str]) -> list[int]:
        """Score passages for relevance."""
        prompt = f"Query: {query}\n\nRank by relevance (0-100):\n"
        for i, p in enumerate(passages):
            prompt += f"{i}. {p[:100]}\n"

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        scores = []
        for line in text.split("\n"):
            if ": " in line:
                try:
                    score = int(line.split(": ")[1].split()[0])
                    scores.append(max(0, min(100, score)))
                except (ValueError, IndexError):
                    scores.append(0)
        return scores + [0] * (len(passages) - len(scores))


class FakeReranker(Reranker):
    """Fake reranker for testing."""

    async def score(self, query: str, passages: list[str]) -> list[int]:
        """Return uniform scores."""
        return [50] * len(passages)


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
    return OpenAIReranker(client, settings.rerank_model)
