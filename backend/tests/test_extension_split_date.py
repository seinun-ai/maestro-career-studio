"""Workday's split dates, and the blur that used to throw half of them away.

Measured on a live form (deluxe.wd5, 2026-08-08). A date is one
`[data-automation-id="dateInputWrapper"]` holding several `role="spinbutton"`
inputs, and the widget validates when focus leaves the WIDGET rather than the
section. The old ladder blurred after EVERY field, so the month was handed over
while the year was still empty; the widget called that an incomplete date and
discarded the month ~400ms later. The field ended as `MM/2006` with "Error:
Invalid Date" beside it — the reported bug, and reproduced exactly by driving
the old ladder against the real page.

Two things that experiment also settled, both worth keeping written down:

* It is NOT about `isTrusted`. The same untrusted write holds perfectly once
  the blur moves — "08/2011" survived a blur and 700ms of settling.
* It is NOT the sibling clobbering anything. The month died before the year was
  written at all.
"""

from tests.extension_harness import outcome_for, run_profile_fill


# One work-experience block, as Workday renders it: two sections, one widget.
def _date_fields(widget="workExperience-6--startDate"):
    return [
        {"label": f"month | {widget}-datesectionmonth-input | from*",
         "kind": "text", "dateWidget": widget, "datePart": "Month"},
        {"label": f"year | {widget}-datesectionyear-input | from*",
         "kind": "text", "dateWidget": widget, "datePart": "Year"},
    ]


_EMPLOYMENT = [{"employer": "Acme", "title": "Analyst", "start_date": "Jun 2006",
                "end_date": "Aug 2011", "current": False}]


def test_both_sections_of_a_split_date_survive(tmp_path):
    """The bug, stated as the behaviour that has to hold."""
    fields = _date_fields()
    result = run_profile_fill(tmp_path, fields=fields, employment=_EMPLOYMENT)

    assert result["values"][fields[0]["label"]] == "06"
    assert result["values"][fields[1]["label"]] == "2006", (
        "the month was blurred while the year was empty, so the widget "
        "discarded it — the MM/2006 failure"
    )


def test_a_section_is_not_blurred_while_its_sibling_is_empty(tmp_path):
    """The mechanism, not just the outcome.

    Asserted on the EVENTS because the value surviving could also be explained
    by a harness that simply does not model the discard. The month must not
    carry a blur until after the year has been written.
    """
    fields = _date_fields()
    result = run_profile_fill(tmp_path, fields=fields, employment=_EMPLOYMENT)
    month_events = result["events"][fields[0]["label"]]
    year_events = result["events"][fields[1]["label"]]
    # The month is written first and blurs LAST — after the year exists.
    assert "blur" not in month_events[:month_events.index("change") + 1]
    assert "blur" in year_events or "blur" in month_events, (
        "the date must still be blurred eventually, or validation never runs"
    )


def test_the_last_date_on_the_page_is_still_blurred(tmp_path):
    """The deferred blur has to be flushed at the end of the run.

    A Workday experience block usually ENDS on a date, so without the final
    flush the last date would never validate — trading a visible failure for a
    form that silently refuses to submit.
    """
    fields = _date_fields()
    result = run_profile_fill(tmp_path, fields=fields, employment=_EMPLOYMENT)
    assert "blur" in result["events"][fields[1]["label"]]


def test_two_dates_in_one_block_do_not_share_a_flush(tmp_path):
    """From and To are different widgets. Reaching the second must flush the
    first, or the start date never validates."""
    fields = [*_date_fields("workExperience-6--startDate"),
              *_date_fields("workExperience-6--endDate")]
    fields[2]["label"] = "month | workexperience-6--enddate-datesectionmonth-input | to*"
    fields[3]["label"] = "year | workexperience-6--enddate-datesectionyear-input | to*"
    result = run_profile_fill(tmp_path, fields=fields, employment=_EMPLOYMENT)

    assert result["values"][fields[0]["label"]] == "06"
    assert result["values"][fields[1]["label"]] == "2006"
    assert result["values"][fields[2]["label"]] == "08"
    assert result["values"][fields[3]["label"]] == "2011"
    assert "blur" in result["events"][fields[1]["label"]], "the From date never validated"


def test_a_month_the_widget_strips_to_one_digit_is_still_a_success(tmp_path):
    """Workday keeps "6" for the "06" we wrote.

    The readback's stripped comparison calls that a miss on purpose — leading
    zeros are significant in postal codes and requisition ids
    (test_a_dropped_leading_zero_stays_not_stuck pins that). Inside a date PART
    the reasoning does not apply: month 6 and month 06 are the same month. It
    reports filled_normalized rather than not_stuck, so a working fill stops
    being counted as a failure.
    """
    fields = [_date_fields()[0], _date_fields()[1]]
    fields[0]["normalizesTo"] = "6"
    result = run_profile_fill(tmp_path, fields=fields, employment=_EMPLOYMENT)
    assert outcome_for(result, fields[0]["label"]) == "filled_normalized"


def test_an_ordinary_input_still_blurs_immediately(tmp_path):
    """The regression guard. Blur-triggered validation is why the ladder blurs
    at all; only a date SECTION defers, and only because its widget validates
    at a different boundary."""
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": "City", "kind": "text"}],
        profile={"personal": {"city": "Austin"}},
    )
    assert "blur" in result["events"]["City"]
