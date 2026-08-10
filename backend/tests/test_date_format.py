import pytest

from app.services.date_format import format_date


@pytest.mark.parametrize(
    ("raw", "mode", "expected"),
    [
        ("Jun 2026", "long_month", "June 2026"),
        ("June 2026", "short_month", "Jun 2026"),
        ("2026-06", "short_month", "Jun 2026"),
        ("06/2026", "long_month", "June 2026"),
        ("Jun 2026", "numeric", "06/2026"),
        ("Jun 2026", "verbatim", "Jun 2026"),
        # passthrough: not parseable / sentinel / year-only / empty / None
        ("Present", "short_month", "Present"),
        ("2026", "short_month", "2026"),
        ("garbage", "long_month", "garbage"),
        ("", "short_month", ""),
        (None, "short_month", ""),
    ],
)
def test_format_date(raw, mode, expected):
    assert format_date(raw, mode) == expected
