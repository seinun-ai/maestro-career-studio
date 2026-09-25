"""The six failures docs/reports/2026-09-25-extension-reliability-research.md
reproduced, asserted as the new engine must behave."""

import pytest

from tests.browser.conftest import fixture_html

# raises=Exception keeps "FAIL in CI without Chromium" alive: the harness's
# pytest.fail() is a BaseException, so it is not swallowed as the expected failure.
pytestmark = pytest.mark.xfail(strict=True, raises=Exception, reason="engine lands in Tasks 2-4")

NS = "window.careerStudioCompanion"


def inventory(page):
    return page.evaluate(f"() => {NS}.fillOps.inventory({{}}).fields")


def apply(page, action):
    return page.evaluate(f"(a) => {NS}.fillOps.apply([a])", action)[0]


def test_1_an_aria_labelledby_field_is_listed_with_its_question(page, load):
    load(page, "<span id='q'>First name</span><input id='f-92' aria-labelledby='q'>")
    assert [f["question"] for f in inventory(page)] == ["First name"]


def test_2_identity_is_the_element_not_joined_label_text(page, load):
    load(page, "<label for='c'>Country</label><button id='c' aria-haspopup='listbox' name='field-12'>Select One</button>")
    first = inventory(page)[0]["fid"]
    assert inventory(page)[0]["fid"] == first and "|" not in first


def test_3_an_unmatched_input_combobox_is_listed(page, load):
    load(page, "<label for='s'>What is your preferred shift?</label><input id='s' role='combobox'>")
    assert [(f["shape"], f["question"]) for f in inventory(page)] == [("search", "What is your preferred shift?")]


def test_4_a_closed_dropdown_is_explored_before_anyone_decides(page, load):
    load(page, fixture_html("workday_listbox.html"))
    fid = next(f["fid"] for f in inventory(page) if f["question"].startswith("Are you legally"))
    got = page.evaluate(f"(fid) => {NS}.fillOps.explore([{{fid}}])", fid)
    assert [o["text"] for o in got[fid]["options"]] == ["Yes", "No"]


def test_5_a_rejected_click_is_never_reported_filled(page, load):
    load(page, fixture_html("react_select.html"))
    page.evaluate("window.rejectClicks = true")
    f = inventory(page)[0]
    row = apply(page, {"fid": f["fid"], "fp": f["fp"], "op": "choose", "text": "India", "term": "ind"})
    assert row["outcome"] != "verified" and row["committed"] == ""


def test_6_a_hidden_unrelated_option_is_never_clicked(page, load):
    load(page, fixture_html("workday_listbox.html"))
    f = next(f for f in inventory(page) if f["question"].startswith("Are you legally"))
    row = apply(page, {"fid": f["fid"], "fp": f["fp"], "op": "choose", "text": "Canada"})
    assert row["outcome"] == "unexpected"
    assert page.evaluate("window.staleHit === undefined")
