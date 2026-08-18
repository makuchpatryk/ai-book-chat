"""Domain events emitted during use case execution."""

from dataclasses import dataclass
from uuid import UUID

from app.domain.values.retrieval import Citation


@dataclass(frozen=True)
class SourcesFound:
    """Sources found in document retrieval."""

    citations: list[Citation]
    pages: list[int]


@dataclass(frozen=True)
class TokenProduced:
    """A token produced by the answer generator."""

    text: str


@dataclass(frozen=True)
class AnswerCompleted:
    """Answer generation completed and persisted."""

    message_id: UUID
    grounded: bool
    truncated: bool


@dataclass(frozen=True)
class AnswerFailed:
    """Answer generation failed."""

    detail: str


AnswerEvent = SourcesFound | TokenProduced | AnswerCompleted | AnswerFailed
