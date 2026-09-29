"""TypeSafe (System One) passage reranker."""

import asyncio

from typesafe_sdk import AsyncTypeSafeClient, Score

from app.domain.ports.llm import Reranker

# Ordered least to most relevant; the model sees each level independently, so
# every one describes a concrete situation rather than a degree.
RELEVANCE_QUESTION = Score(
    instructions=(
        "A reader asked a question about a book. Judge how much the book passage helps "
        "answer that question, using only what the passage actually says."
    ),
    criteria=[
        "The passage is about something unrelated to the question.",
        "The passage covers the same topic as the question but says nothing that answers it.",
        "The passage contains part of the answer, or facts an answer would build on.",
        "The passage directly and specifically answers the question.",
    ],
)
_TOP_LEVEL = len(RELEVANCE_QUESTION.criteria) - 1
_MAX_CONCURRENCY = 16


class TypeSafeReranker(Reranker):
    """Scores each passage with its own Score question, all in parallel.

    Results are mapped onto the 0-10 integer scale the retrieval policy uses.
    Any failed call fails the whole rerank, so the caller degrades to distance
    filtering rather than ranking on partial scores.
    """

    def __init__(self, api_key: str, model: str | None = None, base_url: str | None = None):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    async def score(self, query: str, passages: list[str]) -> list[int]:
        """Score passages 0-10 in input order. Raises if any call fails."""
        if not passages:
            return []

        gate = asyncio.Semaphore(_MAX_CONCURRENCY)
        async with AsyncTypeSafeClient(
            api_key=self.api_key, model=self.model, base_url=self.base_url
        ) as client:

            async def one(passage: str) -> int:
                async with gate:
                    response = await client.system_one(
                        state={"question": query, "passage": passage},
                        questions={"relevance": RELEVANCE_QUESTION},
                    )
                level = response.scores["relevance"].score
                return max(0, min(10, round(level / _TOP_LEVEL * 10)))

            return list(await asyncio.gather(*(one(p) for p in passages)))
