"""Shared Hugging Face router helpers."""

import pytest

from app.config import Settings
from app.llm.hf_client import (
    extract_json_object,
    hf_api_key,
    hf_extra_headers,
    is_billing_error,
    strip_reasoning,
)


def test_token_falls_back_to_the_shared_llm_key() -> None:
    assert hf_api_key(Settings(hf_token="hf_x", llm_api_key="sk-y")) == "hf_x"
    assert hf_api_key(Settings(hf_token=None, llm_api_key="sk-y")) == "sk-y"
    assert hf_api_key(Settings(hf_token=None, llm_api_key=None)) is None


def test_bill_to_header_is_only_sent_when_configured() -> None:
    assert hf_extra_headers(Settings(hf_bill_to=None)) == {}
    assert hf_extra_headers(Settings(hf_bill_to="my-org")) == {"X-HF-Bill-To": "my-org"}


def test_strip_reasoning_drops_think_blocks() -> None:
    text = "<think>the user wants scores\nlet me count</think>\n{\"passages\": []}"

    assert strip_reasoning(text) == '{"passages": []}'


def test_strip_reasoning_drops_reasoning_blocks_and_keeps_prose() -> None:
    assert strip_reasoning("<reasoning>hmm</reasoning> the answer is 4") == "the answer is 4"
    assert strip_reasoning("plain answer") == "plain answer"


def test_extract_json_object_from_clean_json() -> None:
    assert extract_json_object('{"passages": [{"index": 0, "score": 7}]}') == (
        '{"passages": [{"index": 0, "score": 7}]}'
    )


def test_extract_json_object_unwraps_a_fence() -> None:
    text = 'Here you go:\n```json\n{"passages": []}\n```\n'

    assert extract_json_object(text) == '{"passages": []}'


def test_extract_json_object_ignores_surrounding_prose() -> None:
    text = 'Sure! {"passages": [{"index": 0, "score": 3}]} Hope that helps {done}'

    assert extract_json_object(text) == '{"passages": [{"index": 0, "score": 3}]}'


def test_extract_json_object_ignores_braces_inside_strings() -> None:
    assert extract_json_object('{"note": "a } brace"}') == '{"note": "a } brace"}'


def test_extract_json_object_raises_without_an_object() -> None:
    with pytest.raises(ValueError):
        extract_json_object("I am afraid I cannot score these passages.")


def test_extract_json_object_raises_on_an_unbalanced_object() -> None:
    with pytest.raises(ValueError):
        extract_json_object('{"passages": [{"index": 0')


def test_is_billing_error_only_matches_402() -> None:
    class _Status(Exception):
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

    assert is_billing_error(_Status(402))
    assert not is_billing_error(_Status(429))
    assert not is_billing_error(ValueError("nope"))
