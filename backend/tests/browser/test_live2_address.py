"""I4 (plan docs/plans/2026-10-14-companion-live-check-2.md): an address line-1 autocomplete, end to
end through the loop. Real Chromium, the scripted backend of test_fill_end_to_end.py; made-up address."""

import pytest

from tests.browser.conftest import fixture_html
from tests.browser.pages import oracle
from tests.browser.test_fill_end_to_end import _run


@pytest.fixture
def e2e_page(page):
    page.set_default_timeout(60000)
    return page


# --- I4: address autocomplete
ADDRESS = {"route": "slot", "slot": "personal.address", "value": "121 Allora PL"}
ADDRESS_MAP = {
    "Address Line 1": ADDRESS,
    "City": {"route": "slot", "slot": "personal.city", "value": "Springfield"},
    "ZIP Code": {"route": "slot", "slot": "personal.postal_code", "value": "12345"},
}


def address_run(page, mode="both", **spec):
    return _run(page, html=fixture_html("address_autocomplete.html"), page_js=f"window.addressMode = '{mode}'",
                map=ADDRESS_MAP, limits={"MAX_ROUNDS": 2}, **spec)


def paths(out):
    return [p["path"] for p in out["posts"]]


def test_the_row_with_the_house_number_and_the_street_is_picked_and_no_word_is_searched(e2e_page):
    page = e2e_page
    out = address_run(page)
    assert oracle(page, "address_clicks") == ["121 Allora Pl, Springfield"]   # the partial row was never clicked
    assert oracle(page, "address_line") == "121 Allora Pl, Springfield"
    # The explore and the choose each ask the list for the whole line; a word of it is never asked.
    assert set(oracle(page, "address_queries")) == {"121 Allora PL"} and oracle(page, "address_enters") == 0
    assert "/api/autofill/pick" not in paths(out) and "/api/autofill/step" not in paths(out)
    status = {q: r["status"] for q, r in out["by_question"].items()}
    assert status["Address Line 1"] == "verified", out["by_question"]["Address Line 1"]
    # What the pick wrote into City and ZIP matches the profile, so it stands as the page left it.
    assert (page.input_value("#city"), page.input_value("#zip")) == ("Springfield", "12345")
    assert status["City"] in ("verified", "already") and status["ZIP Code"] in ("verified", "already")


def test_a_list_without_the_full_address_is_searched_again_by_number_and_street_name(e2e_page):
    page = e2e_page
    out = address_run(page, "retry")
    assert list(dict.fromkeys(oracle(page, "address_queries"))) == ["121 Allora PL", "121 Allora"]
    assert oracle(page, "address_clicks") == ["121 Allora Pl, Springfield"]
    assert out["by_question"]["Address Line 1"]["status"] == "verified"


def test_the_city_breaks_a_tie_between_two_equally_good_rows(e2e_page):
    page = e2e_page
    out = _run(page, html=fixture_html("address_autocomplete.html"), page_js="window.addressMode = 'twins'",
               map={**ADDRESS_MAP, "City": {"route": "slot", "slot": "personal.city", "value": "Shelbyville"}},
               limits={"MAX_ROUNDS": 2})
    assert oracle(page, "address_clicks") == ["121 Allora Pl, Shelbyville"]
    assert out["by_question"]["Address Line 1"]["status"] == "verified"


def test_two_tied_rows_with_nothing_to_tell_them_apart_pick_none(e2e_page):
    page = e2e_page
    out = _run(page, html=fixture_html("address_autocomplete.html"), page_js="window.addressMode = 'twins'",
               map={"Address Line 1": ADDRESS}, limits={"MAX_ROUNDS": 2})
    assert oracle(page, "address_clicks") == []
    assert out["by_question"]["Address Line 1"]["status"] != "verified"


def test_no_row_with_the_number_and_street_leaves_the_field_for_the_user(e2e_page):
    page = e2e_page
    out = address_run(page, "none")
    row = out["by_question"]["Address Line 1"]
    assert oracle(page, "address_clicks") == [] and row["status"] == "needs_answer", row
    assert oracle(page, "address_queries")[0] == "121 Allora PL" and "/api/autofill/pick" not in paths(out)


FREE_TEXT_ADDRESS = ("<form><label for='a'>Address Line 1</label><input id='a' role='combobox' aria-autocomplete='list' aria-expanded='false'>"
                     "<div id='drop' role='listbox' style='display:none'><div role='option'>Allora Pl, Springfield</div></div>"
                     "<script>const i = document.getElementById('a'), d = document.getElementById('drop');"
                     "i.setAttribute('aria-controls', 'drop');"
                     "i.addEventListener('input', () => { setTimeout(() => { d.style.display = ''; i.setAttribute('aria-expanded', 'true'); }, 300); });"
                     "d.firstChild.addEventListener('click', () => { i.value = 'Allora Pl, Springfield'; d.style.display = 'none'; });"
                     "</script></form>")


def test_a_box_that_keeps_free_text_keeps_the_typed_line_and_the_field_is_flagged(e2e_page):
    """No suggestion has the number: the typed line stays in a box that keeps free text, and the user is told."""
    page = e2e_page
    out = _run(page, html=FREE_TEXT_ADDRESS, map={"Address Line 1": ADDRESS}, limits={"MAX_ROUNDS": 2})
    row = out["by_question"]["Address Line 1"]
    assert page.input_value("#a") == "121 Allora PL", row
    assert row["status"] == "unconfirmed", row


def rows_run(page, line, rows, **spec):
    return _run(page, html=fixture_html("address_autocomplete.html"), page_js=f"window.addressRows = {rows!r}",
                map={"Address Line 1": {"route": "slot", "slot": "personal.address", "value": line}},
                limits={"MAX_ROUNDS": 2}, **spec)


def test_a_trailing_direction_is_part_of_the_street(e2e_page):
    page = e2e_page
    out = rows_run(page, "121 Allora PL NW", ["121 Allora Pl SW, Springfield", "121 Allora Pl NW, Springfield"])
    assert oracle(page, "address_clicks") == ["121 Allora Pl NW, Springfield"]
    assert out["by_question"]["Address Line 1"]["status"] == "verified"


def test_the_last_suffix_word_ends_the_street(e2e_page):
    """"Court" is a street suffix and a street name: "100 Court St" ends at St, so "100 Court Pl" is another street."""
    page = e2e_page
    out = rows_run(page, "100 Court St", ["100 Court Pl, Springfield", "100 Court St, Springfield"])
    assert oracle(page, "address_clicks") == ["100 Court St, Springfield"]
    assert out["by_question"]["Address Line 1"]["status"] == "verified"
