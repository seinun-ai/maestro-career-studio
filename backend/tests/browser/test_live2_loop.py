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

