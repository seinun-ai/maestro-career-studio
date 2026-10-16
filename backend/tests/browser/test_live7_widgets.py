"""Live check 7 (2026-10-15, a one-page application on a hosted board; made-up employer Acme): the dropdowns whose typed search
emptied a fixed list. `fixtures/browser/greenhouse_acme_form.html` filters its options by substring as the user types, so a saved
"Masters" matches nothing in "Master's Degree" and the list shows "No options"; opened with no term it lists all ten.

Core tests drive the page operations (fill-core's explore); loop tests drive the real fill loop with the backend's answers scripted.
"""

import json

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


def test_the_fallback_word_loses_the_punctuation_it_carried_from_the_term(page, load):
    load(page, ACME)
    got = explore(page, inv(page)["Degree"], "Associate's, Nursing")
    assert texts(got) == ["Associate's Degree"]


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


# ---------- Location (City): searched as "City, State"; the options offered are kept in the trace ----------

# The page also asks for the state (a plain box), so the loop learns it from the profile through /map.
WITH_STATE = ACME.replace("</form>", '<label for="state">State</label><input id="state" type="text" aria-label="State"></form>')
CITY = {"Location (City)": {"route": "slot", "slot": "personal.city", "value": "Springfield"}}
STATE = {"State": {"route": "slot", "slot": "personal.state", "value": "Illinois"}}
SPRINGFIELD_IL = "Springfield, Illinois, United States"


def city_terms(out):
    """The terms the loop typed into the city box, in order (an explore with no term types nothing)."""
    fid = next(r["fid"] for r in out["report"]["fields"] if r["question"] == "Location (City)")
    return [req.get("term") for msg in out["sent"] if msg["type"] == "fill_explore" for req in msg["requests"] if req["fid"] == fid]


def test_a_city_box_is_searched_as_city_and_state_when_the_profile_has_the_state(page):
    out = _run(page, html=WITH_STATE, map={**CITY, **STATE}, picks={"Location (City)": {"text": SPRINGFIELD_IL, "reason": "matched"}})
    assert city_terms(out)[0] == "Springfield, Illinois"
    [pick] = [f for body in posts_to(out, "/api/autofill/pick") for f in body["fields"] if f["question"] == "Location (City)"]
    assert [o["text"] for o in pick["options"]] == [SPRINGFIELD_IL]
    assert oracle(page, "gh_location") == SPRINGFIELD_IL


def test_a_city_box_without_a_known_state_is_searched_by_the_city_alone(page):
    out = _run(page, html=ACME, map=CITY, picks={"Location (City)": {"text": SPRINGFIELD_IL, "reason": "matched"}})
    assert city_terms(out)[0] == "Springfield"
    [pick] = [f for body in posts_to(out, "/api/autofill/pick") for f in body["fields"] if f["question"] == "Location (City)"]
    assert len(pick["options"]) == 2                      # both Springfields: the backend picks by the saved state
    assert oracle(page, "gh_location") == SPRINGFIELD_IL


def test_a_city_and_state_that_find_nothing_fall_back_to_the_city_alone(page):
    out = _run(page, html=WITH_STATE, map={**CITY, "State": {**STATE["State"], "value": "Narnia"}},
               picks={"Location (City)": {"text": SPRINGFIELD_IL, "reason": "matched"}})
    assert city_terms(out)[:2] == ["Springfield, Narnia", "Springfield"]
    assert oracle(page, "gh_location") == SPRINGFIELD_IL


SPRINGFIELD_MA = "Springfield, Massachusetts, United States"


def location_trace(out):
    return next(f for f in out["report"]["trace"]["fields"] if f["label"] == "Location (City)")


def test_a_typed_search_keeps_only_how_many_options_it_offered_since_they_echo_what_was_typed(page):
    out = _run(page, html=ACME, url="https://job-boards.greenhouse.io/acme/jobs/7", map=CITY,
               picks={"Location (City)": {"text": SPRINGFIELD_IL, "reason": "matched"}})
    field = location_trace(out)
    assert field["options"] == [] and field["option_count"] == 2
    assert "Springfield" not in json.dumps(out["report"]["trace"])


def test_a_city_and_state_search_keeps_only_a_count_too(page):
    out = _run(page, html=WITH_STATE, url="https://job-boards.greenhouse.io/acme/jobs/7", map={**CITY, **STATE},
               picks={"Location (City)": {"text": SPRINGFIELD_IL, "reason": "matched"}})
    field = location_trace(out)
    assert field["options"] == [] and field["option_count"] == 1
    assert "Illinois" not in json.dumps(out["report"]["trace"]) and "Springfield" not in json.dumps(out["report"]["trace"])


def test_the_whole_list_read_with_no_term_keeps_its_texts_in_the_trace(page):
    out = _run(page, html=ACME, url="https://job-boards.greenhouse.io/acme/jobs/7", map=degree_map("Graduate Degree"),
               picks={"Degree": {"text": "Master's Degree", "reason": "matched"}})
    degree = next(f for f in out["report"]["trace"]["fields"] if f["label"] == "Degree")
    assert degree["option_count"] == 10 and degree["options"] == DEGREES
