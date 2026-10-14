"""The fill loop (shared/fill-loop.js) on the owner's second live check, Batch I: reporting, address,
URL and date handling, and the flicker trace. Real Chromium, the same scripted-backend harness as
test_fill_end_to_end.py; every page is a fixture or inline made-up markup."""

import pytest

from tests.browser.conftest import fixture_html
from tests.browser.pages import oracle
from tests.browser.test_fill_end_to_end import _run


@pytest.fixture
def e2e_page(page):
    page.set_default_timeout(60000)
    return page


# --- I8: never left blank because of a missing label
def test_an_optional_unlabelled_textarea_is_asked_never_left_blank(e2e_page):
    page = e2e_page
    out = _run(page, html="<form><textarea id='t'></textarea></form>", map={})
    [row] = out["report"]["fields"]
    assert (row["status"], row["lastOutcome"]) == ("needs_answer", "no_fact"), row


def test_an_optional_unlabelled_text_box_with_no_fact_is_still_left_blank(e2e_page):
    """Only prose boxes and required controls are protected: a bare optional input is the old rule."""
    out = _run(e2e_page, html="<form><input id='t'></form>", map={})
    [row] = out["report"]["fields"]
    assert (row["status"], row["lastOutcome"]) == ("left_blank", "no_fact"), row


def test_a_labelled_optional_textarea_with_no_fact_is_left_blank(e2e_page):
    out = _run(e2e_page, html="<form><label for='t'>Anything else we should know?</label><textarea id='t'></textarea></form>", map={})
    [row] = out["report"]["fields"]
    assert row["status"] == "left_blank", row



# --- I6: native date boxes take the 1st (owner decision)
DATE_PAGE = ("<form><label for='s'>Start date</label><input id='s' type='date'>"
             "<label for='e'>Graduation</label><input id='e' type='date'>"
             "<label for='f'>Full date</label><input id='f' type='date'></form>")


def test_a_month_only_date_is_written_as_the_first_and_reported_assumed_with_its_note(e2e_page):
    page = e2e_page
    out = _run(page, html=DATE_PAGE, map={
        "Start date": {"route": "slot", "slot": "experience.0.start", "value": "2021-05", "format": "date"},
        "Graduation": {"route": "slot", "slot": "education.0.end", "value": "2024", "format": "date"},
        "Full date": {"route": "slot", "slot": "experience.0.end", "value": "2022-03-09", "format": "date"}})
    got = {q: (r["status"], r["note"]) for q, r in out["by_question"].items()}
    assert got == {"Start date": ("assumed", "Day set to the 1st"),
                   "Graduation": ("assumed", "Set to the 1st of January"),
                   "Full date": ("verified", None)}, got
    assert [page.input_value(i) for i in ("#s", "#e", "#f")] == ["2021-05-01", "2024-01-01", "2022-03-09"]


def test_a_date_beyond_the_boxs_max_is_not_written_and_is_the_users(e2e_page):
    page = e2e_page
    out = _run(page, html="<form><label for='s'>Start date</label><input id='s' type='date' max='2021-04-30'></form>",
               map={"Start date": {"route": "slot", "slot": "experience.0.start", "value": "2021-05", "format": "date"}})
    assert out["by_question"]["Start date"]["status"] != "assumed" and page.input_value("#s") == ""

