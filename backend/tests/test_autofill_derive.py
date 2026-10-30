"""Work-permit answers a citizenship settles (Task 3.4 of
docs/plans/2026-10-30-country-form-questions.md): only the five rules the sources verified, computed
on read, never stored, and an answer the user gave always wins."""

import json

import pytest

from app.config import settings
from app.services import autofill_derive

SETTLED = {"authorized_now": True, "sponsorship_now": False, "sponsorship_future": False}


@pytest.fixture
def settings_dir(tmp_path, monkeypatch):
    """The settings' file mirrors go to a throwaway folder (SYSTEM.md §12, 2026-10-21)."""
    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    return tmp_path


def _values(derived):
    return {k: d.value for k, d in derived.items()}


def test_a_citizen_in_their_own_country():
    assert _values(autofill_derive.derived_for(["IN"], "IN")) == SETTLED  # IN lists no statuses
    assert _values(autofill_derive.derived_for(["CA"], "CA")) == {**SETTLED, "status": "citizen"}
    assert autofill_derive.derived_for(["GB"], "UK")["authorized_now"].via == "GB"


def test_eu_eea_and_swiss_citizens_in_germany_the_netherlands_and_ireland():
    for code in ("FR", "IE", "IS", "LI", "NO", "CH"):
        for market in ("DE", "NL", "IE"):
            assert _values(autofill_derive.derived_for([code], market)) == SETTLED, (code, market)


def test_british_citizens_in_ireland_only():
    assert autofill_derive.derived_for(["GB"], "IE")["authorized_now"].via == "GB"
    assert autofill_derive.derived_for(["GB"], "DE") == {}
    assert autofill_derive.derived_for(["GB"], "NL") == {}


def test_irish_citizens_in_the_uk_but_not_other_eu_citizens():
    assert _values(autofill_derive.derived_for(["IE"], "UK")) == SETTLED
    assert autofill_derive.derived_for(["FR"], "UK") == {}


def test_gcc_nationals_in_the_uae():
    assert _values(autofill_derive.derived_for(["SA"], "AE")) == {**SETTLED, "status": "gcc_national"}
    assert _values(autofill_derive.derived_for(["AE"], "AE")) == {**SETTLED, "status": "citizen"}


def test_nothing_else_is_derived():
    assert autofill_derive.derived_for([], "DE") == {}
    assert autofill_derive.derived_for(["IN"], "AE") == {}
    assert autofill_derive.derived_for(["US"], "CA") == {}
    # A market Maestro does not keep settles nothing, its own citizens' included.
    assert autofill_derive.derived_for(["BR"], "BR") == {}


def test_dual_citizens_take_the_first_rule_that_settles_it():
    assert autofill_derive.derived_for(["IN", "GB"], "IE")["authorized_now"].via == "GB"
    assert autofill_derive.derived_for(["FR", "GB"], "IE")["authorized_now"].via == "FR"


def test_the_markets_own_citizenship_comes_first():
    for listed in (["SA", "AE"], ["AE", "SA"]):
        derived = autofill_derive.derived_for(listed, "AE")
        assert _values(derived) == {**SETTLED, "status": "citizen"}, listed
        assert derived["status"].via == "AE", listed
    assert autofill_derive.derived_for(["IE", "GB"], "UK")["authorized_now"].via == "GB"


def test_settled_markets_are_where_a_citizenship_lets_you_work():
    # In markets.yaml's order.
    assert autofill_derive.settled_markets(["FR"]) == ["IE", "DE", "NL"]
    assert autofill_derive.settled_markets(["IN"]) == ["IN"]
    assert autofill_derive.settled_markets(["GB"]) == ["UK", "IE"]
    assert autofill_derive.settled_markets(["SA"]) == ["AE"]
    assert autofill_derive.settled_markets([]) == []


def test_citizenships_are_read_as_iso_codes():
    profile = {"personal": {"citizenships": ["fr", "Narnia", 7, "United Kingdom"]}}
    assert autofill_derive.citizenships(profile) == ["FR", "GB"]
    assert autofill_derive.citizenships({"personal": {"citizenships": "FR"}}) == []
    assert autofill_derive.citizenships(None) == []


def test_an_explicit_answer_wins_and_the_rest_is_derived():
    profile = {"personal": {"citizenships": ["AE"]},
               "work_auth_by_country": {"AE": {"status": "golden_visa", "sponsorship_future": False}}}
    assert autofill_derive.answers_for(profile, "AE") == {**SETTLED, "status": "golden_visa"}


def test_a_value_the_typed_reader_cannot_use_is_no_answer():
    """A blank select, a status outside the market's list and a non-answer read as unknown
    everywhere (`autofill_profile._usable_answers_only`), so they hide nothing a citizenship
    settles; a usable answer beside them still wins."""
    profile = {"personal": {"citizenships": ["SA"]},
               "work_auth_by_country": {"AE": {"status": "", "authorized_now": "maybe",
                                               "authorization_expires_on": "2030-01-01"}}}
    assert autofill_derive.answers_for(profile, "AE") == {
        **SETTLED, "status": "gcc_national", "authorization_expires_on": "2030-01-01"}


def test_an_invalid_stored_status_shows_the_derived_one():
    profile = {"personal": {"citizenships": ["AE"]}, "work_auth_by_country": {"AE": {"status": "OPT"}}}
    assert autofill_derive.answers_for(profile, "AE") == {**SETTLED, "status": "citizen"}


def test_an_answer_in_the_legacy_shape_is_read_as_the_typed_reader_reads_it():
    """The legacy pair (SYSTEM.md §13 autofill-work-auth-shape) is a given answer under the typed
    keys, so a derived typed key never hides it."""
    profile = {"personal": {"citizenships": ["FR"]},
               "work_auth_by_country": {"DE": {"authorized_to_work": "yes", "requires_sponsorship": "no"}}}
    assert autofill_derive.answers_for(profile, "DE") == SETTLED


@pytest.mark.parametrize("entry", [
    {"authorized_now": False},
    {"sponsorship_now": True},
    {"sponsorship_future": True, "authorized_now": True},
    {"authorized_to_work": "yes", "requires_sponsorship": "yes"},  # the legacy pair
])
def test_an_answer_that_contradicts_the_rule_turns_it_off_for_that_country(entry):
    """Never a derived "no sponsorship" beside a given "not authorized": the user knows something
    the rule does not, so the market reads only what they gave."""
    profile = {"personal": {"citizenships": ["FR"]}, "work_auth_by_country": {"DE": entry}}
    assert autofill_derive.answers_for(profile, "DE") == entry
    # Another country the rule settles is untouched.
    assert autofill_derive.answers_for(profile, "NL") == SETTLED


def test_the_market_is_read_as_a_key():
    profile = {"personal": {"citizenships": ["FR"]},
               "work_auth_by_country": {"DE": {"authorization_expires_on": "2030-01-01"}}}
    assert autofill_derive.answers_for(profile, " de ") == {**SETTLED, "authorization_expires_on": "2030-01-01"}


def test_with_nothing_derived_the_stored_answers_are_read_as_they_are():
    profile = {"personal": {"citizenships": ["IN"]},
               "work_auth_by_country": {"DE": {"authorized_to_work": "yes", "status": ""}}}
    assert autofill_derive.answers_for(profile, "DE") == {"authorized_to_work": "yes", "status": ""}
    assert autofill_derive.answers_for(profile, "UK") == {}


def test_a_legacy_single_set_is_the_home_markets():
    profile = {"personal": {"citizenships": ["FR"]}, "work_auth": {"sponsorship_future": True}}
    assert autofill_derive.answers_for(profile, "DE", home="DE") == {"sponsorship_future": True}
    assert autofill_derive.answers_for(profile, "NL", home="DE") == SETTLED


def test_derived_answers_are_never_stored(client, settings_dir):
    assert client.put("/api/settings/market", json={"value": {"home": "DE", "apply_in": ["DE"]}}).status_code == 200
    assert client.put("/api/settings/autofill", json={"value": {"personal": {"citizenships": ["FR"]}}}).status_code == 200
    stored = json.loads((settings_dir / "autofill.json").read_text())
    assert stored["personal"]["citizenships"] == ["FR"]
    assert "DE" not in (stored.get("work_auth_by_country") or {})
    assert "DE" not in (client.get("/api/settings/autofill").json()["value"].get("work_auth_by_country") or {})
