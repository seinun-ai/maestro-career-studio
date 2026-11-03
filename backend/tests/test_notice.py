"""Notice read as days from the text people wrote, and days said back in words (services/notice.py)."""

import pytest

from app.services import notice


@pytest.mark.parametrize("text,days", [
    ("0", 0), (" now ", 0), ("Immediately", 0), ("immediate", 0), ("1 day", 1), ("45 days", 45),
    ("2 weeks", 14), ("1 week", 7), ("1 month", 30), ("3 Months", 90), (0, 0), (30, 30),
])
def test_days_from_text_reads_plain_answers(text, days):
    assert notice.days_from_text(text) == days


@pytest.mark.parametrize("text", ["negotiable", "2", "", None, "two weeks", "-1 days", True, "1.5 months", -3])
def test_days_from_text_leaves_what_it_cannot_read(text):
    assert notice.days_from_text(text) is None   # a bare "2" has no unit: never guessed


@pytest.mark.parametrize("days,words", [
    (0, "Immediately"), (7, "1 week"), (14, "2 weeks"), (21, "3 weeks"), (28, "28 days"),
    (30, "1 month"), (60, "2 months"), (90, "3 months"), (45, "45 days"), (1, "1 day"),
])
def test_notice_words(days, words):
    assert notice.notice_words(days) == words


@pytest.mark.parametrize("value,days", [(14, 14), (0, 0), ("14", 14), (" 30 ", 30), (14.0, 14), (0.0, 0)])
def test_whole_days_reads_a_number_of_days(value, days):
    assert notice.whole_days(value) == days   # a number box sends "14"; a hand edit may write 14.0


@pytest.mark.parametrize("value", [14.5, "14.5", -1, "-1", "1e1", "", None, True, False, "2 weeks", [14],
                                   float("inf"), float("nan")])
def test_whole_days_leaves_what_is_no_whole_number_of_days(value):
    assert notice.whole_days(value) is None
