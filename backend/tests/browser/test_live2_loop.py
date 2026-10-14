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


# --- I5: URL values through the loop
WEBSITE = {"route": "slot", "slot": "personal.website", "value": "sample-one-site.example.dev"}


def test_a_url_slot_is_written_with_https(e2e_page):
    page = e2e_page
    out = _run(page, html="<form><label for='w'>Website</label><input id='w'></form>", map={"Website": WEBSITE})
    assert page.input_value("#w") == "https://sample-one-site.example.dev"
    assert out["by_question"]["Website"]["status"] == "verified"


def test_a_stored_url_that_already_has_a_scheme_is_written_as_it_is(e2e_page):
    page = e2e_page
    _run(page, html="<form><label for='w'>LinkedIn</label><input id='w'></form>", map={
        "LinkedIn": {"route": "slot", "slot": "personal.linkedin", "value": "http://www.example.com/in/sample"}})
    assert page.input_value("#w") == "http://www.example.com/in/sample"


def test_a_box_too_short_for_the_url_is_left_for_the_user_and_nothing_is_truncated(e2e_page):
    page = e2e_page
    out = _run(page, html="<form><label for='w'>Website</label><input id='w' maxlength='20'></form>", map={"Website": WEBSITE})
    assert page.input_value("#w") == "" and out["by_question"]["Website"]["status"] != "verified"


def test_a_box_holding_a_different_host_is_flagged_and_never_counted_answered(e2e_page):
    page = e2e_page
    out = _run(page, html="<form><label for='w'>Website</label><input id='w' value='example.dev'></form>", map={"Website": WEBSITE})
    row = out["by_question"]["Website"]
    assert (row["status"], row["lastOutcome"]) == ("needs_answer", "holds_something_else"), row
    assert page.input_value("#w") == "example.dev"   # the box is not overwritten


def test_a_box_holding_the_same_site_in_another_spelling_is_already_there(e2e_page):
    page = e2e_page
    out = _run(page, html="<form><label for='w'>Website</label><input id='w' value='https://www.Sample-One-Site.example.dev/'></form>",
               map={"Website": WEBSITE})
    assert out["by_question"]["Website"]["status"] == "already"
