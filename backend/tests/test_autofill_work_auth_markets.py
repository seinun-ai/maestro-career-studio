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
