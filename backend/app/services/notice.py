"""A notice period read as whole days, and days said back in words. Pure: no database, no I/O.

Notice used to be free text ("2 weeks", "now"); the one answer is now `notice_days`. Only the plain shapes are read: a
bare "2" has no unit and "negotiable" no number, so both stay unread rather than guessed. A month is 30 days. A form
that asks in words gets weeks below four, the round months, and days for anything else."""

import re
from typing import Any

_ZERO_WORDS = {"0", "now", "immediately", "immediate"}
_PERIOD = re.compile(r"^\s*(\d+)\s*(day|days|week|weeks|month|months)\s*$", re.IGNORECASE)
_UNIT_DAYS = {"day": 1, "week": 7, "month": 30}


def days_from_text(text: Any) -> int | None:
    """The whole days `text` says, else None. A bare integer (a JSON number) is days already."""
    if isinstance(text, bool):  # an int subclass, never a notice period
        return None
    if isinstance(text, int):
        return text if text >= 0 else None
    if not isinstance(text, str):
        return None
    if text.strip().lower() in _ZERO_WORDS:
        return 0
    if not (match := _PERIOD.match(text)):
        return None
    return int(match[1]) * _UNIT_DAYS[match[2].lower().rstrip("s")]


def notice_words(days: int) -> str:
    """`days` in words: 0 "Immediately", 7, 14 or 21 in weeks, 30, 60 or 90 in months, anything else in days."""
    if days == 0:
        return "Immediately"
    if days in (7, 14, 21):
        count, unit = days // 7, "week"
    elif days in (30, 60, 90):
        count, unit = days // 30, "month"
    else:
        count, unit = days, "day"
    return f"{count} {unit}{'' if count == 1 else 's'}"
