"""Date readability: the health gate and the ATS engine must agree on "current".

The bug this pins: `ats/resume_indexer` accepted {present, current, now,
ongoing} and granted recency credit, while `health_zones.parse_ym` accepted
only present|current|now. A resume saying "Ongoing" was therefore scored as a
CURRENT role by the engine and simultaneously failed health gate S3 (tier
`serious`) for an unparseable end date — same document, opposite readings.
"""

import pytest

from app.services import resume_dates
from app.services.ats.resume_indexer import parse_month_year
from app.services.health_zones import parse_ym


@pytest.mark.parametrize(
    "token", ["Present", "Current", "Currently", "Now", "Ongoing", "To date", "Till date", "To present"]
)
def test_both_subsystems_agree_a_token_means_current(token):
    """The single-source assertion. If these ever diverge again, the ATS engine
    and the health gate are describing the same resume differently."""
    assert resume_dates.is_current(token) is True
    assert parse_ym(token) == "present"
    # The ATS side returns None for a current marker: there is no end date to
    # parse. That is agreement, not disagreement — both say "no end date here".
    assert parse_month_year(token) is None


def test_current_is_a_whole_string_match_not_a_prefix():
    """"Present day rotation" is not a current marker. The ATS side previously
    matched on the first whitespace token, which would have accepted it."""
    assert resume_dates.is_current("Present day rotation") is False
    assert parse_ym("Present day rotation") is None


@pytest.mark.parametrize(
    "value,expected",
    [
        ("Summer 2022", (2022, 6)), ("Fall 2021", (2021, 9)), ("Autumn 2021", (2021, 9)),
        ("Winter 2020", (2020, 12)), ("Spring 2023", (2023, 3)),
        ("Q1 2021", (2021, 1)), ("Q3 2022", (2022, 7)),
        ("2019", (2019, 1)), ("2019-07", (2019, 7)), ("07/2019", (2019, 7)),
    ],
)
def test_gate_reads_seasonal_quarter_and_year_only_dates(value, expected):
    """Academic CVs and internships say "Summer 2022"; UK and Australian CVs use
    year-only for older roles. All are readable dates and must not be reported
    as a defect."""
    assert parse_ym(value) == expected


@pytest.mark.parametrize("value", ["Summer 2022", "Q3 2022", "2019"])
def test_the_ats_engine_deliberately_does_NOT_learn_these(value):
    """The recency rule is unchanged on purpose. A season or a bare year is
    readable but is not a precise month, and recency credit is computed from
    precise months. Readable for the gate, no credit for the score."""
    assert parse_month_year(value) is None


@pytest.mark.parametrize("value", ["Q5 2021", "Summerish 2022", "Blah 2022", "", None])
def test_genuinely_unreadable_dates_still_fail(value):
    """The gate must still catch real defects — widening it must not make it
    vacuous."""
    assert parse_ym(value) is None


def test_gate_dates_passes_a_resume_using_ongoing():
    """End to end: the S3 gate itself, not just the parser."""
    from app.services.health_gates import gate_dates

    resume = {
        "experience": [
            {"company": "Acme", "role": "Analyst", "start_date": "Jan 2020", "end_date": "Ongoing"},
            {"company": "Beta", "role": "Intern", "start_date": "Summer 2018", "end_date": "Fall 2018"},
            {"company": "Gamma", "role": "Assistant", "start_date": "2015", "end_date": "2017"},
        ]
    }
    result = gate_dates(resume)
    assert result["status"] == "pass", result["detail"]


def test_gate_dates_still_fails_a_genuinely_unparseable_date():
    from app.services.health_gates import gate_dates

    resume = {
        "experience": [
            {"company": "Acme", "role": "Analyst", "start_date": "sometime", "end_date": "later"}
        ]
    }
    assert gate_dates(resume)["status"] == "fail"
