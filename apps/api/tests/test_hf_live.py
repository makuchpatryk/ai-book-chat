"""Opt-in check against the real Hugging Face router: `uv run pytest -m live`.

Excluded from the default run (see `addopts` in pyproject.toml) so the suite
stays offline and free. Costs a few tenths of a cent per run.
"""

import pytest

from app.chat.generate import ChatMessage, GenerationDone, HFGenerator, TextDelta, build_generator
from app.config import get_settings
from app.llm.hf_client import hf_api_key
from app.retrieval.rerank import HFReranker, RerankCandidate, build_reranker

pytestmark = pytest.mark.live


@pytest.fixture(autouse=True)
def require_token() -> None:
    if not hf_api_key(get_settings()):
        pytest.skip("HF_TOKEN not set")


async def test_real_chat_completion_streams_text_and_usage() -> None:
    generator = build_generator()
    assert isinstance(generator, HFGenerator)

    events = [
        event
        async for event in generator.stream(
            "Answer in one short sentence.",
            [ChatMessage(role="user", content="What is the capital of France?")],
        )
    ]

    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    done = events[-1]
    assert "Paris" in text
    assert isinstance(done, GenerationDone)
    assert done.stop_reason is not None
    assert done.input_tokens and done.output_tokens
    assert done.estimated is False


def test_real_rerank_returns_one_score_per_passage() -> None:
    reranker = build_reranker()
    assert isinstance(reranker, HFReranker)

    candidates = [
        RerankCandidate(index=0, content="The mitochondrion produces the cell's energy."),
        RerankCandidate(index=1, content="The 1974 World Cup final was played in Munich."),
        RerankCandidate(index=2, content="ATP is synthesised in the mitochondrial matrix."),
    ]
    scores = reranker.score("How do cells make energy?", candidates)

    assert len(scores) == 3
    assert all(0 <= score <= 10 for score in scores)
    assert scores[1] < max(scores[0], scores[2])
