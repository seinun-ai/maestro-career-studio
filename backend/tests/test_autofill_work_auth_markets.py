"""Work-permit answers stay with the country they were given for (owner decision D9).

A profile from before per-country answers holds one top-level `work_auth`, read as the home market's.
Nothing in that set says which country it was for, so a home move must not carry it along: before a
new home is stored, the set is pinned to the home it has been read as (`market_settings.set_market`).
"""

import json

import pytest

from app.config import settings
from app.services import autofill_country, autofill_profile, market_settings, text_settings
from app.services.sync import hooks, status

CITIZEN = {"status": "citizen", "authorized_now": True, "sponsorship_now": False, "sponsorship_future": False}


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    monkeypatch.setattr(settings, "sync_key_file", tmp_path / "absent-key")
    monkeypatch.setattr(settings, "sync_remote_url", "")


def _write(db, key, filename, value) -> None:
    text_settings.set_text(key, filename, json.dumps(value), db)


def _stored_profile(db) -> dict:
    return json.loads(text_settings.peek_text(autofill_profile.AUTOFILL_KEY, autofill_profile.AUTOFILL_FILE, db))


def _legacy(db, profile=None, market=None) -> None:
    if market is not None:
        _write(db, market_settings.MARKET_KEY, market_settings.MARKET_FILE, market)
    _write(db, autofill_profile.AUTOFILL_KEY, autofill_profile.AUTOFILL_FILE, profile or {"work_auth": CITIZEN})


# --- finding: a home move carried the one old set to the new country ----------------------------------------------

@pytest.mark.parametrize("market", [{"market": "US"}, None], ids=["us-chosen", "never-chosen"])
def test_a_legacy_set_stays_with_the_country_it_was_given_for_when_home_moves(db_session, client, market):
    """Home US with the old one set, then "You live in" becomes the UK: a UK form must not answer "authorized
    now: Yes, citizen", a US form must still get the answers, and the UK is not a country you may work in.
    A market never chosen read as the default (US), so the set was the US's then too."""
    _legacy(db_session, market=market)
    put = client.put("/api/settings/market", json={"value": {"home": "UK", "apply_in": ["UK", "US"]}})
    assert put.status_code == 200, put.text

    view = client.get("/api/settings/autofill").json()["value"]
    assert view["work_auth_by_country"] == {"US": CITIZEN}
    assert "work_auth" not in view  # the UK, where you live now, has no answers yet
    uk = autofill_country.work_auth_for(view, question="", job_country="GB")
    assert (uk.status, uk.authorized_now, uk.sponsorship_now) == (None, None, None)
    assert uk.countries_authorized == ["United States"]
    us = autofill_country.work_auth_for(view, question="", job_country="US")
    assert (us.status, us.authorized_now) == ("citizen", True)
    # Pinned in the store too, so no later read can move it again.
    assert _stored_profile(db_session) == {"work_auth_by_country": {"US": CITIZEN}}


def test_a_pinned_set_does_not_follow_a_second_move(db_session):
    _legacy(db_session, market={"market": "US"})
    market_settings.set_market(market_settings.MarketSetting(home="UK", apply_in=["UK"]), db_session)
    market_settings.set_market(market_settings.MarketSetting(home="DE", apply_in=["DE"]), db_session)
    assert autofill_profile.get_profile(db_session)["work_auth_by_country"] == {"US": CITIZEN}
    assert autofill_profile.get_work_auth(db_session, "DE").authorized_now is None


def test_a_legacy_set_beside_the_old_homes_own_answers_is_not_moved_to_the_new_home(db_session):
    """The old home had its own entry, so the top-level set was read for no country; it is not given to the new one."""
    own = {"authorized_now": False, "sponsorship_now": True}
    _legacy(db_session, market={"market": "US"},
            profile={"work_auth": CITIZEN, "work_auth_by_country": {"US": own}})
    market_settings.set_market(market_settings.MarketSetting(home="UK", apply_in=["UK", "US"]), db_session)
    assert autofill_profile.get_profile(db_session)["work_auth_by_country"] == {"US": own}
    assert _stored_profile(db_session) == {"work_auth_by_country": {"US": own}}


def test_the_pin_keeps_the_rest_of_the_stored_profile_as_written(db_session):
    """Only the work-permit set moves: an old veteran word stays as stored (it is mapped when read)."""
    _legacy(db_session, market={"market": "US"},
            profile={"work_auth": CITIZEN, "eeo": {"veteran_status": "veteran"}, "personal": {"first_name": "Ada"}})
    market_settings.set_market(market_settings.MarketSetting(home="UK", apply_in=["UK"]), db_session)
    assert _stored_profile(db_session) == {"work_auth_by_country": {"US": CITIZEN},
                                           "eeo": {"veteran_status": "veteran"}, "personal": {"first_name": "Ada"}}


def test_a_move_with_nothing_to_pin_writes_no_profile(db_session):
    _write(db_session, market_settings.MARKET_KEY, market_settings.MARKET_FILE, {"market": "US"})
    market_settings.set_market(market_settings.MarketSetting(home="UK", apply_in=["UK"]), db_session)
    assert text_settings.peek_text(autofill_profile.AUTOFILL_KEY, autofill_profile.AUTOFILL_FILE, db_session) == ""
    mapped = '{"work_auth_by_country": {"US": {"authorized_now": true}}}'
    text_settings.set_text(autofill_profile.AUTOFILL_KEY, autofill_profile.AUTOFILL_FILE, mapped, db_session)
    market_settings.set_market(market_settings.MarketSetting(home="DE", apply_in=["DE"]), db_session)
    assert text_settings.peek_text(autofill_profile.AUTOFILL_KEY, autofill_profile.AUTOFILL_FILE, db_session) == mapped


def test_a_save_that_keeps_the_home_leaves_the_legacy_set_as_written(db_session):
    """Only a home move pins: adding a country you apply in changes no read of the one set."""
    _legacy(db_session, market={"market": "US"})
    market_settings.set_market(market_settings.MarketSetting(home="US", apply_in=["US", "UK"]), db_session)
    assert _stored_profile(db_session) == {"work_auth": CITIZEN}


def test_the_always_on_copy_refuses_the_move_and_keeps_both_settings(db_session, client, monkeypatch):
    """Both settings are profile rows the laptop owns: the flush guard refuses the pin as it refuses the move."""
    _legacy(db_session, market={"market": "US"})
    status.create_key()
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")
    put = client.put("/api/settings/market", json={"value": {"home": "UK", "apply_in": ["UK"]}})
    assert put.status_code == 409
    db_session.rollback()
    assert _stored_profile(db_session) == {"work_auth": CITIZEN}
    assert market_settings.peek_market(db_session).home == "US"
    with pytest.raises(hooks.NotOwnedHere):
        market_settings.set_market(market_settings.MarketSetting(home="UK", apply_in=["UK"]), db_session)


# --- finding: a stale one-set client overwrote another market's answers -------------------------------------------
#
# A client that knows one set (the Companion's pause row, an older page) edits `work_auth`, the set it was served.
# A read names the market that set is for (`work_auth_market`), and a save folds the set into the market the
# client names: never into whatever the home is by the time it saves.

US_SET = {"authorized_now": True, "sponsorship_now": False}
UK_SET = {"authorized_now": False, "sponsorship_now": True}


def _home(db, home, apply_in=None) -> None:
    market_settings.set_market(market_settings.MarketSetting(home=home, apply_in=apply_in or [home]), db)


def _map(db) -> dict:
    return _stored_profile(db).get("work_auth_by_country", {})


def test_a_read_names_the_market_its_one_set_is_for(db_session, client):
    _home(db_session, "UK", ["UK", "US"])
    autofill_profile.set_profile({"work_auth_by_country": {"US": US_SET, "UK": UK_SET}}, db_session)
    view = client.get("/api/settings/autofill").json()["value"]
    assert (view["work_auth"], view["work_auth_market"]) == (UK_SET, "UK")
    # Named while the home has no answers yet, so a client that adds them says whose they are.
    autofill_profile.set_profile({"work_auth_by_country": {"UK": None}}, db_session)
    view = autofill_profile.get_profile(db_session)
    assert "work_auth" not in view and view["work_auth_market"] == "UK"
    # A profile with no work-permit answers has nothing to name, and the marker is never stored.
    autofill_profile.set_profile({"personal": {"first_name": "Ada"}, "work_auth_by_country": {"US": None}}, db_session)
    assert autofill_profile.get_profile(db_session) == {"personal": {"first_name": "Ada"}}
    assert "work_auth_market" not in _stored_profile(db_session)


def test_a_stale_one_set_client_saves_into_the_market_it_was_served(db_session):
    """Served under home US, saved after the home moved to the UK: the edit is the US's, the UK's answers stand."""
    _home(db_session, "US", ["US", "UK"])
    autofill_profile.set_profile({"work_auth_by_country": {"US": US_SET, "UK": UK_SET}}, db_session)
    served = autofill_profile.get_profile(db_session)
    _home(db_session, "UK", ["US", "UK"])
    edited = {**served, "work_auth": {**served["work_auth"], "sponsorship_future": True}}
    saved = autofill_profile.set_profile(edited, db_session)
    assert _map(db_session) == {"US": {**US_SET, "sponsorship_future": True}, "UK": UK_SET}
    # The save answers as a read would now: the home's set, named. Saved again (a name edit): nothing moves.
    assert (saved["work_auth"], saved["work_auth_market"]) == (UK_SET, "UK")
    autofill_profile.set_profile({**saved, "personal": {"first_name": "Ada"}}, db_session)
    assert _map(db_session) == {"US": {**US_SET, "sponsorship_future": True}, "UK": UK_SET}


def test_a_client_that_knows_every_country_keeps_its_map_edit(db_session):
    """Profile and Setup edit the map; a `work_auth` left as served is not an edit and does not undo theirs."""
    _home(db_session, "UK", ["UK", "US"])
    autofill_profile.set_profile({"work_auth_by_country": {"US": US_SET, "UK": UK_SET}}, db_session)
    view = autofill_profile.get_profile(db_session)
    view["work_auth_by_country"] = {**view["work_auth_by_country"], "UK": {"authorized_now": True}}
    autofill_profile.set_profile(view, db_session)
    assert _map(db_session)["UK"] == {"authorized_now": True}


def test_a_save_that_leaves_a_country_out_keeps_its_answers(db_session):
    """A client that does not know a country cannot have meant to remove its answers; a country sent as null
    goes."""
    _home(db_session, "US", ["US", "UK"])
    autofill_profile.set_profile({"work_auth_by_country": {"US": US_SET}}, db_session)
    stale = autofill_profile.get_profile(db_session)
    autofill_profile.set_profile({"work_auth_by_country": {"UK": UK_SET}}, db_session)  # another client adds the UK
    autofill_profile.set_profile({**stale, "personal": {"first_name": "Ada"}}, db_session)
    assert _map(db_session) == {"US": US_SET, "UK": UK_SET}
    autofill_profile.set_profile({"personal": {"first_name": "Ada"}}, db_session)  # no map at all
    assert _map(db_session) == {"US": US_SET, "UK": UK_SET}
    autofill_profile.set_profile({"work_auth_by_country": {"UK": None}}, db_session)
    assert _map(db_session) == {"US": US_SET}


@pytest.mark.parametrize("mark", [None, "", "ZZ", 7])
def test_a_set_whose_market_is_unknown_is_not_saved_anywhere(db_session, mark):
    """`work_auth_market` null (a /context profile with no job's country), empty, unsupported, or not a string:
    the set is for no market this store knows, so the stored answers stand."""
    _home(db_session, "US", ["US", "UK"])
    autofill_profile.set_profile({"work_auth_by_country": {"US": US_SET}}, db_session)
    autofill_profile.set_profile({"work_auth": UK_SET, "work_auth_market": mark}, db_session)
    assert _map(db_session) == {"US": US_SET}


def test_a_set_with_no_marker_is_the_homes_only_while_no_other_country_has_answers(db_session):
    """A client from before the marker: with one country's answers (or none) its set can only be the home's,
    as it always was; once another country has answers it could be either, so the stored answers stand."""
    _home(db_session, "UK", ["UK", "US"])
    autofill_profile.set_profile({"work_auth": UK_SET}, db_session)
    assert _map(db_session) == {"UK": UK_SET}
    autofill_profile.set_profile({"work_auth": US_SET, "work_auth_by_country": {"UK": UK_SET}}, db_session)
    assert _map(db_session) == {"UK": US_SET}
    autofill_profile.set_profile({"work_auth_by_country": {"US": US_SET}}, db_session)  # now two countries
    autofill_profile.set_profile({"work_auth": UK_SET}, db_session)
    assert _map(db_session) == {"UK": US_SET, "US": US_SET}


def test_the_reviewers_case_a_stale_set_after_a_move_from_a_legacy_profile(db_session, client):
    """Legacy set under US, served to an old page; the home moves to the UK and the page saves its set edited:
    it lands on the US, and the UK still has nothing."""
    _legacy(db_session, market={"market": "US"})
    served = client.get("/api/settings/autofill").json()["value"]
    assert served["work_auth_market"] == "US"
    client.put("/api/settings/market", json={"value": {"home": "UK", "apply_in": ["UK", "US"]}})
    put = client.put("/api/settings/autofill",
                     json={"value": {**served, "work_auth": {**served["work_auth"], "authorized_now": False}}})
    assert put.status_code == 200
    assert _map(db_session) == {"US": {**CITIZEN, "authorized_now": False}}
    assert "work_auth" not in put.json()["value"]


def test_a_profile_resolved_for_a_job_names_the_jobs_market(db_session):
    """/context and /choose serve the job's country's set as `work_auth`, so the marker names that market (null
    with no job or a country no market covers); such a profile put back folds nowhere it was not served for."""
    from app.models.application import Application
    from app.services import autofill_job
    from tests.test_proposals_models import _mk_job

    _home(db_session, "US", ["US", "UK"])
    autofill_profile.set_profile({"work_auth_by_country": {"US": US_SET, "UK": UK_SET}}, db_session)
    profile = autofill_profile.get_profile(db_session)
    apps = {}
    for code in ("GB", "FR"):
        job = _mk_job(db_session, company=f"Acme {code}", country_code=code)
        apps[code] = Application(job_id=job.id, base_resume="hybrid")
        db_session.add(apps[code])
    db_session.commit()
    uk = autofill_job.profile_for_job(db_session, profile, apps["GB"].id)
    assert uk["work_auth"] == {**UK_SET, "countries_authorized": ["United States"]}
    assert uk["work_auth_market"] == "UK"
    assert autofill_job.profile_for_job(db_session, profile, apps["FR"].id)["work_auth_market"] is None
    assert autofill_job.profile_for_job(db_session, profile, None)["work_auth_market"] is None
    autofill_profile.set_profile({**uk, "work_auth": {**UK_SET, "sponsorship_future": True}}, db_session)
    assert _map(db_session) == {"US": US_SET, "UK": {**UK_SET, "sponsorship_future": True}}
