"""Quiz data structures."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

QuizOption = Literal["A", "B", "C", "D"]


class QuizStatus(StrEnum):
    """Status of quiz generation."""

    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True)
class QuizQuestion:
    """A single multiple-choice question."""

    position: int
    question: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: QuizOption
