"""A Places-style city search ("Springfield, IL, USA") offers the city with its state and country after it. The saved city
and state pick it in code: the first comma part is the city and the rest names the state, by code or by full name."""

import pytest

from app.schemas.autofill_fill import PickField, PickOption, StepRequest
from app.services import autofill_catalog, autofill_pick, autofill_place, autofill_step

CITY = "personal.city"


def facts_of(city="Springfield", state="IL"):
    return autofill_catalog.build({"personal": {"city": city, **({"state": state} if state else {})}}, [], [])


def opts(*texts):
    return [PickOption(oid=f"o{i}", text=t) for i, t in enumerate(texts, start=1)]


@pytest.fixture(autouse=True)
def _no_model(monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("a model was asked")
    monkeypatch.setattr(autofill_pick.jev, "decide", boom)
    monkeypatch.setattr(autofill_pick.llm, "call_openai", boom)


@pytest.mark.parametrize(("city", "state", "options", "expected"), [
    ("Springfield", "IL", ["Springfield, MO, USA", "Springfield, IL, USA", "Springfield, MA, USA"], "Springfield, IL, USA"),
    ("Springfield", "Illinois", ["Springfield, MO, USA", "Springfield, IL, USA"], "Springfield, IL, USA"),
    ("Springfield", "IL", ["Springfield, Missouri, United States", "Springfield, Illinois, United States"],
     "Springfield, Illinois, United States"),
    ("springfield", "il", ["Springfield, Illinois, USA"], "Springfield, Illinois, USA"),
    ("New York", "NY", ["New York, NY, USA", "New Yorker Ave, NY, USA"], "New York, NY, USA"),
    ("Austin", "TX", ["Austin, TX 78701, USA", "Austin, MN, USA"], "Austin, TX 78701, USA"),
    ("St. Louis", "MO", ["St. Louis, MO, USA", "St. Louis, MI, USA"], "St. Louis, MO, USA"),
    ("Washington", "DC", ["Washington, DC, USA", "Washington, PA, USA"], "Washington, DC, USA"),
])
def test_an_option_whose_first_part_is_the_city_and_whose_rest_names_the_state_is_matched(city, state, options, expected):
    got = autofill_place.city_option(city, state, [(f"o{i}", t) for i, t in enumerate(options, start=1)])
    assert dict((f"o{i}", t) for i, t in enumerate(options, start=1))[got] == expected


@pytest.mark.parametrize("options", [
    ["Springfield, MO, USA", "Springfield, MA, USA"],               # the right city, the wrong states
    ["Springfield Gardens, NY, USA", "North Springfield, IL, USA"],     # the city is only a part of the name
    ["Springfield", "Springfield, USA"],                            # no state named
    ["Springfield, IL, USA", "Springfield, Illinois, USA"],             # two options say the one place: not mine to choose
    ["Chicago, IL, USA"],
    [],
])
def test_no_option_is_matched_when_the_city_state_or_uniqueness_does_not_hold(options):
    assert autofill_place.city_option("Springfield", "IL", [(f"o{i}", t) for i, t in enumerate(options, start=1)]) is None


@pytest.mark.parametrize(("city", "state"), [("Springfield", None), ("", "IL"), (None, "IL")])
def test_without_both_a_saved_city_and_state_nothing_is_matched(city, state):
    assert autofill_place.city_option(city, state, [("o1", "Springfield, IL, USA")]) is None


def test_a_city_field_is_matched_in_code_by_pick_without_a_model(db_session):
    field = PickField(fid="c", question="Location (City)", route="slot", slot=CITY,
                      options=opts("Springfield, MO, USA", "Springfield, IL, USA"))
    got = autofill_pick.pick([field], facts_of(), db_session, None)["c"]
    assert (got.oids, got.reason) == (["o2"], "matched")


def test_a_city_field_with_no_matching_option_goes_the_ordinary_way(db_session, monkeypatch):
    asked = []
    monkeypatch.setattr(autofill_pick.jev, "decide", lambda *a, **k: asked.append(1) or {})
    monkeypatch.setattr(autofill_pick.llm, "call_openai", lambda **kw: asked.append(1) or {})
    field = PickField(fid="c", question="Location (City)", route="slot", slot=CITY, options=opts("Springfield, MO, USA"))
    autofill_pick.pick([field], facts_of(), db_session, None)
    assert asked


def test_the_step_clicks_the_option_the_page_offers(db_session):
    cands = [{"mid": f"click:o{i}", "describe": f'Click the option "{t}"'}
             for i, t in enumerate(["Springfield, MO, USA", "Springfield, Illinois, USA"], start=1)]
    req = StepRequest(fid="c", question="Location (City)", route="slot", slot=CITY, candidates=cands)
    got = autofill_step.step(req, facts_of(), db_session, None)
    assert (got.mid, got.reason) == ("click:o2", "matched")


@pytest.mark.parametrize(("city", "state", "options", "expected"), [
    ("Arlington", "TX", ["Arlington, TX, USA", "Arlington, VA, USA", "Arlington Heights, IL, USA"], "Arlington, TX, USA"),
    ("Arlington", "Texas", ["Arlington, VA, USA", "Arlington, Texas, United States"], "Arlington, Texas, United States"),
    ("NYC", "New York", ["New York, NY, USA"], "New York, NY, USA"),
    ("Kansas City", "MO", ["Kansas City, KS, USA", "Kansas City, MO, USA"], "Kansas City, MO, USA"),
    ("Portland", "ME", ["Portland, OR, USA", "Portland, ME, USA"], "Portland, ME, USA"),
    ("Irving", "tx", ["Irving, TX, USA"], "Irving, TX, USA"),
    ("Irving", "Texas ", ["Irving , Texas , USA"], "Irving , Texas , USA"),
    ("Bangalore", "Karnataka", ["Bengaluru, Karnataka, India", "Bangalore, Karnataka, India"], "Bangalore, Karnataka, India"),
])
def test_more_places_style_lists(city, state, options, expected):
    ids = [(f"o{i}", t) for i, t in enumerate(options, start=1)]
    assert dict(ids)[autofill_place.city_option(city, state, ids)] == expected


@pytest.mark.parametrize(("city", "state", "options"), [
    ("Arlington", "VA", ["Arlington, TX, USA"]),
    ("Georgia", "GA", ["Georgia"]),
    ("Paris", "TX", ["Paris, France", "Paris, Île-de-France, France"]),
    ("Paris", "", ["Paris, TX, USA"]),
    ("Washington", "DC", ["Washington, United States"]),
])
def test_the_wrong_state_or_no_state_matches_nothing(city, state, options):
    assert autofill_place.city_option(city, state, [(f"o{i}", t) for i, t in enumerate(options, start=1)]) is None
