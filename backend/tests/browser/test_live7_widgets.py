"""Live check 7 (2026-10-15, a one-page application on a hosted board; made-up employer Acme): the dropdowns whose typed search
emptied a fixed list. `fixtures/browser/greenhouse_acme_form.html` filters its options by substring as the user types, so a saved
"Masters" matches nothing in "Master's Degree" and the list shows "No options"; opened with no term it lists all ten.

Core tests drive the page operations (fill-core's explore); loop tests drive the real fill loop with the backend's answers scripted.
"""

import pytest

from tests.browser.conftest import fixture_html
from tests.browser.pages import explore, inv, oracle
from tests.browser.test_fill_end_to_end import _run

ACME = fixture_html("greenhouse_acme_form.html")
DEGREES = ["High School", "Associate's Degree", "Bachelor's Degree", "Master's Degree", "Master of Business Administration (MBA)",
           "Doctor of Philosophy (Ph.D.)", "Juris Doctor (J.D.)", "Doctor of Medicine (M.D.)", "Some College", "Other"]


def texts(got):
    return [o["text"] for o in got["options"]]


# ---------- the word fallback: apostrophes and plurals ----------


@pytest.mark.parametrize("term, wanted", [
    ("Masters", "Master's Degree"),
    ("Bachelors Degree", "Bachelor's Degree"),
    ("Associates", "Associate's Degree"),
])
def test_a_typed_term_that_empties_the_list_is_searched_again_without_apostrophes_and_plurals(page, load, term, wanted):
    load(page, ACME)
    got = explore(page, inv(page)["Degree"], term)
    assert wanted in texts(got), (term, texts(got))


def test_the_old_word_fallback_still_works(page, load):
    load(page, ACME)
    got = explore(page, inv(page)["Degree"], "Juris Practice")
    assert texts(got) == ["Juris Doctor (J.D.)"]


def test_a_term_with_no_word_in_the_list_stays_empty_here(page, load):
    load(page, ACME)
    got = explore(page, inv(page)["Degree"], "Graduate Degree")
    assert texts(got) == [] and got["error"] == "empty_popup"


# ---------- the loop: a typed search that empties a search box is explored again with no term ----------


def degree_map(value):
    return {"Degree": {"route": "slot", "slot": "education.0.degree", "value": value}}


def posts_to(out, path):
    return [p["body"] for p in out["posts"] if p["path"] == path]


def test_a_saved_value_no_option_contains_is_picked_from_the_whole_list_not_handed_to_the_step_agent(page):
    out = _run(page, html=ACME, map=degree_map("Graduate Degree"),
               picks={"Degree": {"text": "Master's Degree", "reason": "matched"}})
    [pick] = [f for body in posts_to(out, "/api/autofill/pick") for f in body["fields"] if f["question"] == "Degree"]
    assert [o["text"] for o in pick["options"]] == DEGREES and pick["complete"] is True
    assert posts_to(out, "/api/autofill/step") == []
    assert oracle(page, "gh_degree") == "Master's Degree"
    assert out["by_question"]["Degree"]["status"] in ("verified", "assumed", "closest", "matched")


def test_the_stem_fallback_alone_finds_masters_so_no_second_look_is_needed(page):
    out = _run(page, html=ACME, map=degree_map("Masters"), picks={"Degree": {"text": "Master's Degree", "reason": "matched"}})
    [pick] = [f for body in posts_to(out, "/api/autofill/pick") for f in body["fields"] if f["question"] == "Degree"]
    assert "Master's Degree" in [o["text"] for o in pick["options"]]
    assert posts_to(out, "/api/autofill/step") == [] and oracle(page, "gh_degree") == "Master's Degree"


def test_a_search_only_list_that_shows_nothing_without_a_term_still_goes_to_the_step_agent(page):
    out = _run(page, html=ACME, map={"Location (City)": {"route": "slot", "slot": "personal.city", "value": "Atlantis"}})
    [city] = [b for b in posts_to(out, "/api/autofill/step") if b["question"] == "Location (City)"][:1]
    assert city["complete"] is False
    assert [p for p in posts_to(out, "/api/autofill/pick") if "Location" in str(p)] == []
    assert oracle(page, "gh_location") is None

