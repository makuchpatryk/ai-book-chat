"""Unit tests for Quiz entity state transitions."""

import pytest

from app.domain.values.quiz import QuizStatus
from fakes import make_quiz, make_quiz_questions

pytestmark = pytest.mark.unit


def test_new_quiz_has_no_questions() -> None:
    quiz = make_quiz()

    assert quiz.status == QuizStatus.PENDING
    assert quiz.questions == []
    assert quiz.error_message is None


def test_mark_pending_resets_questions_and_error() -> None:
    quiz = make_quiz(status=QuizStatus.FAILED, error_message="boom")

    quiz.mark_pending()

    assert quiz.status == QuizStatus.PENDING
    assert quiz.questions == []
    assert quiz.error_message is None


def test_apply_questions_with_exactly_ten_marks_ready() -> None:
    quiz = make_quiz()

    quiz.apply_questions(make_quiz_questions(10))

    assert quiz.status == QuizStatus.READY
    assert len(quiz.questions) == 10
    assert quiz.error_message is None


@pytest.mark.parametrize("count", [0, 1, 9, 11, 20])
def test_apply_questions_rejects_wrong_count(count: int) -> None:
    quiz = make_quiz()

    with pytest.raises(ValueError, match="expected 10 questions"):
        quiz.apply_questions(make_quiz_questions(count))

    assert quiz.status == QuizStatus.PENDING


def test_apply_questions_rejects_invalid_correct_option() -> None:
    quiz = make_quiz()
    questions = make_quiz_questions(10)
    bad = questions[0]
    questions[0] = type(bad)(**{**bad.__dict__, "correct_option": "E"})  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="invalid correct_option"):
        quiz.apply_questions(questions)


def test_mark_failed_truncates_and_sets_status() -> None:
    quiz = make_quiz()

    quiz.mark_failed("x" * 2000)

    assert quiz.status == QuizStatus.FAILED
    assert quiz.error_message is not None
    assert len(quiz.error_message) == 1000
