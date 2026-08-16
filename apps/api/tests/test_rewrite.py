"""Query rewriter adapters."""

from types import SimpleNamespace
from typing import Any

from app.chat.rewrite import FakeRewriter, HFRewriter, build_rewriter
from app.config import Settings


class _FakeCompletions:
    def __init__(self, content: str | None, error: Exception | None = None) -> None:
        self._content = content
        self._error = error
        self.kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self._error:
            raise self._error
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))],
            usage=SimpleNamespace(prompt_tokens=120, completion_tokens=12),
        )


def _rewriter(content: str | None, error: Exception | None = None) -> HFRewriter:
    completions = _FakeCompletions(content, error)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return HFRewriter(client, "openai/gpt-oss-20b")


def test_hf_rewriter_returns_the_standalone_question() -> None:
    assert _rewriter("What is the author's view on X?").rewrite(
        "What about X?", "User: tell me about the book"
    ) == "What is the author's view on X?"


def test_hf_rewriter_strips_a_reasoning_preamble() -> None:
    rewriter = _rewriter("<think>they mean the book</think>What does the book say about X?")

    assert rewriter.rewrite("what about X?", "history") == "What does the book say about X?"


def test_hf_rewriter_falls_back_to_the_original_on_empty_output() -> None:
    assert _rewriter("").rewrite("what about X?", "history") == "what about X?"
    assert _rewriter(None).rewrite("what about X?", "history") == "what about X?"


def test_hf_rewriter_falls_back_to_the_original_on_oversized_output() -> None:
    assert _rewriter("x" * 501).rewrite("what about X?", "history") == "what about X?"


def test_hf_rewriter_never_raises() -> None:
    rewriter = _rewriter(None, error=RuntimeError("router is down"))

    assert rewriter.rewrite("what about X?", "history") == "what about X?"


def test_build_rewriter_uses_huggingface_by_default_with_a_token() -> None:
    assert isinstance(build_rewriter(Settings(hf_token="hf_test")), HFRewriter)


def test_build_rewriter_falls_back_to_the_fake_without_a_token() -> None:
    assert isinstance(build_rewriter(Settings(hf_token=None, llm_api_key=None)), FakeRewriter)
