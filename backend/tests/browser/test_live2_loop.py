"""The fill loop (shared/fill-loop.js) on the owner's second live check, Batch I: reporting, address,
URL and date handling, and the flicker trace. Real Chromium, the same scripted-backend harness as
test_fill_end_to_end.py; every page is a fixture or inline made-up markup."""

import pytest

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


# --- I7: flicker visibility in the run trace
def test_the_trace_records_took_back_and_the_fields_value_changes(e2e_page, tmp_path):
    from app.schemas.autofill_trace import RunTrace
    from tests.browser.pages import SINGLE_HIT_SEARCH
    from tests.test_extension_sw_router import _posted_trace

    page = e2e_page
    out = _run(page, html=SINGLE_HIT_SEARCH, url="https://careers.acme.test/apply", limits={"MAX_ROUNDS": 1},
               map={"Field of study": {"route": "slot", "slot": "education.0.discipline", "value": "Analytics"}})
    trace = out["report"]["trace"]
    [field] = [f for f in trace["fields"] if f["label"] == "Field of study"]
    effects = [s.get("effect") for s in field["steps"]]
    assert "took_back" in effects and field["changes"] >= 2, (effects, field["changes"])
    # The posted trace (scrubbed by the service worker) keeps both, and the schema takes them.
    sent = _posted_trace(tmp_path, {**trace, "host": "careers.acme.test"})
    RunTrace.model_validate(sent)
    [posted] = [f for f in sent["fields"] if f["label"] == "Field of study"]
    assert "took_back" in [s.get("effect") for s in posted["steps"]] and posted["changes"] == field["changes"]
    # Value-free: a count and a word.
    assert "Analytics" not in str([s for s in posted["steps"]])
    [row] = [r for r in out["report"]["fields"] if r["question"] == "Field of study"]
    assert row["changes"] == field["changes"]


# --- review follow-ups: fixed sentences instead of retries, and the date parts
def test_a_date_outside_the_boxs_range_is_the_users_with_a_fixed_sentence_and_is_not_retried(e2e_page):
    page = e2e_page
    out = _run(page, html="<form><label for='s'>Start date</label><input id='s' type='date' max='2021-04-30'></form>",
               map={"Start date": {"route": "slot", "slot": "experience.0.start", "value": "2021-05", "format": "date"}})
    row = out["by_question"]["Start date"]
    assert (row["status"], row["lastOutcome"]) == ("needs_answer", "outside_date_range"), row
    assert row["answer"] == "This date is outside the range the box allows. Left for you."
    assert len([m for m in out["sent"] if m["type"] == "fill_apply"]) == 1   # one write, no retries


def test_a_url_longer_than_its_box_is_the_users_with_a_fixed_sentence_and_is_not_retried(e2e_page):
    page = e2e_page
    out = _run(page, html="<form><label for='w'>Website</label><input id='w' maxlength='20'></form>", map={"Website": WEBSITE})
    row = out["by_question"]["Website"]
    assert (row["status"], row["lastOutcome"]) == ("needs_answer", "too_long"), row
    assert row["answer"] == "This box is too short for the whole link, so nothing was typed. Left for you."
    assert len([m for m in out["sent"] if m["type"] == "fill_apply"]) == 1


def test_a_clamped_date_is_reported_assumed_with_its_own_note(e2e_page):
    page = e2e_page
    out = _run(page, html="<form><label for='s'>Start date</label><input id='s' type='date' min='2021-05-10'></form>",
               map={"Start date": {"route": "slot", "slot": "experience.0.start", "value": "2021-05", "format": "date"}})
    row = out["by_question"]["Start date"]
    assert (row["status"], row["note"]) == ("assumed", "Date set to the nearest the box allows"), row
    assert page.input_value("#s") == "2021-05-10"


# --- review follow-ups: URL edge cases
def test_a_github_handle_is_written_as_it_is_not_given_a_scheme(e2e_page):
    page = e2e_page
    out = _run(page, html="<form><label for='g'>GitHub</label><input id='g'></form>",
               map={"GitHub": {"route": "slot", "slot": "personal.github", "value": "jdoe"}})
    assert page.input_value("#g") == "jdoe" and out["by_question"]["GitHub"]["status"] == "verified"


def test_an_email_in_a_url_slot_is_written_as_it_is(e2e_page):
    page = e2e_page
    _run(page, html="<form><label for='w'>Website</label><input id='w'></form>",
         map={"Website": {"route": "slot", "slot": "personal.website", "value": "jdoe@example.dev"}})
    assert page.input_value("#w") == "jdoe@example.dev"


def test_a_host_with_a_path_gets_a_scheme(e2e_page):
    page = e2e_page
    _run(page, html="<form><label for='w'>Portfolio</label><input id='w'></form>",
         map={"Portfolio": {"route": "slot", "slot": "personal.website", "value": "www.sample-one-site.example.dev/work"}})
    assert page.input_value("#w") == "https://www.sample-one-site.example.dev/work"


def test_a_number_that_looks_like_a_dotted_host_is_not_a_url_the_box_holds(e2e_page):
    """A box holding "1.2.3" is answered by whatever is in it, not flagged as another site."""
    out = _run(e2e_page, html="<form><label for='w'>Website</label><input id='w' value='1.2.3'></form>", map={"Website": WEBSITE})
    assert out["by_question"]["Website"]["status"] == "already"
