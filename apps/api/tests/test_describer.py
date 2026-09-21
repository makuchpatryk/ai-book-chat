"""Unit tests for OpenAIDescriber output parsing/clamping (stubbed client)."""

import json
from types import SimpleNamespace

import pytest

from app.infrastructure.llm.adapters import FakeDescriber, OpenAIDescriber

pytestmark = pytest.mark.unit


class StubClient:
    def __init__(self, content: str) -> None:
        completion = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )

        async def create(**kwargs: object) -> SimpleNamespace:
            self.kwargs = kwargs
            return completion

        self.kwargs: dict[str, object] = {}
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


def payload(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "summary": "A summary.",
        "language": "pl",
        "doc_type": "Novel",
        "topics": ["one", "two", "three"],
        "sections": [{"heading": f"H{i}", "body": f"B{i}"} for i in range(4)],
    }
    body.update(overrides)
    return body


async def describe(content: str):  # noqa: ANN201
    client = StubClient(content)
    describer = OpenAIDescriber(client, "model", 100)  # type: ignore[arg-type]
    return await describer.describe("Title", "Author", ["Ch 1"], "sample")


async def test_plain_json() -> None:
    overview = await describe(json.dumps(payload()))

    assert overview.summary == "A summary."
    assert overview.language == "pl"
    assert overview.doc_type == "Novel"
    assert overview.topics == ["one", "two", "three"]
    assert [s.heading for s in overview.sections] == ["H0", "H1", "H2", "H3"]


async def test_fenced_json() -> None:
    overview = await describe(f"```json\n{json.dumps(payload())}\n```")

    assert overview.language == "pl"


async def test_prose_wrapped_json() -> None:
    overview = await describe(f"Here you go: {json.dumps(payload())} Hope it helps!")

    assert overview.doc_type == "Novel"


async def test_clamps_lengths_and_counts() -> None:
    body = payload(
        summary="x" * 500,
        topics=[f"t{i}" for i in range(10)],
        sections=[{"heading": f"H{i}", "body": "b" * 5000} for i in range(9)],
    )

    overview = await describe(json.dumps(body))

    assert len(overview.summary) == 300
    assert len(overview.topics) == 6
    assert len(overview.sections) == 6
    assert all(len(s.body) <= 2048 for s in overview.sections)


async def test_empty_sections_are_dropped() -> None:
    sections = [{"heading": "", "body": ""}, {"heading": "A", "body": "a"}] + [
        {"heading": f"H{i}", "body": "b"} for i in range(3)
    ]

    overview = await describe(json.dumps(payload(sections=sections)))

    assert [s.heading for s in overview.sections] == ["A", "H0", "H1", "H2"]


async def test_missing_optional_fields_get_defaults() -> None:
    body = payload()
    for key in ("summary", "language", "doc_type", "topics"):
        del body[key]

    overview = await describe(json.dumps(body))

    assert overview.summary == ""
    assert overview.language == "en"
    assert overview.topics == []


@pytest.mark.parametrize(
    "content",
    [
        "no json here at all",
        "",
        '{"summary": "truncated',
        json.dumps(payload(sections=[{"heading": "only", "body": "two"}] * 2)),
        json.dumps(payload(sections="not a list")),
        json.dumps({"summary": "no sections key"}),
    ],
)
async def test_unusable_output_raises_value_error(content: str) -> None:
    with pytest.raises(ValueError):
        await describe(content)


async def test_wrong_shaped_entries_do_not_crash() -> None:
    body = payload(topics="not a list", sections=["junk", 3] + payload()["sections"])  # type: ignore[operator]

    overview = await describe(json.dumps(body))

    assert overview.topics == []
    assert len(overview.sections) == 4


async def test_prompt_carries_title_author_sections_and_sample() -> None:
    client = StubClient(json.dumps(payload()))
    describer = OpenAIDescriber(client, "model", 100)  # type: ignore[arg-type]

    await describer.describe("My Title", "My Author", ["Ch 1", "Ch 2"], "SAMPLE TEXT")

    prompt = client.kwargs["messages"][1]["content"]  # type: ignore[index]
    for expected in ("My Title", "My Author", "Ch 1, Ch 2", "SAMPLE TEXT"):
        assert expected in prompt
    assert client.kwargs["max_tokens"] == 100


async def test_fake_describer_is_structurally_valid() -> None:
    overview = await FakeDescriber().describe("T", None, [], "")

    assert 3 <= len(overview.sections) <= 6
    assert 3 <= len(overview.topics) <= 6
    assert len(overview.summary) <= 300
