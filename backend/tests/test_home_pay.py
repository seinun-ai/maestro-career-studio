"""Home pay has one place (docs/plans/2026-11-02-start-and-pay.md, Task 3).

Once a country is chosen, the pay of the country you live in is `preferences.desired_salary`; every
other country's is `answers_by_country[market].expected_pay`. A home entry's `expected_pay` (sent by
an older Companion or page, or stored before this rule) is read as `desired_salary` and saved there.
A move of home pins the old home's figure to the old country, and the new home's own figure becomes
`desired_salary`. With no country chosen, `desired_salary` is the one figure for every country, and
nothing moves into or out of it.
"""

import json

import pytest

from app.schemas.market_settings import MarketSetting
from app.services import autofill_profile, market_settings, text_settings

INDIA_PAY = "₹40,00,000"


@pytest.fixture(autouse=True)
def _isolated_settings_dir(tmp_path, monkeypatch):
    # set_profile mirrors to settings/autofill.json; without this the suite would overwrite the
    # developer's real profile.
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)


def _live_in(home: str, apply_in: list[str], db_session) -> None:
    market_settings.set_market(MarketSetting(home=home, apply_in=apply_in), db_session)


def _write(db_session, profile: dict) -> None:
    """The stored text as an older writer left it: no save's fold applied."""
    text_settings.set_text(autofill_profile.AUTOFILL_KEY, autofill_profile.AUTOFILL_FILE,
                           json.dumps(profile), db_session)


def _stored(tmp_path) -> dict:
    return json.loads((tmp_path / autofill_profile.AUTOFILL_FILE).read_text())


# --- save ---------------------------------------------------------------------------------------

def test_a_home_expected_pay_is_saved_as_desired_salary(db_session, tmp_path):
    _live_in("US", ["US", "IN"], db_session)
    saved = autofill_profile.set_profile(
        {"preferences": {"desired_salary": "$80,000"},
         "answers_by_country": {"US": {"expected_pay": "$95,000"}, "IN": {"expected_pay": INDIA_PAY}}}, db_session)
    assert saved["preferences"]["desired_salary"] == "$95,000"
    assert saved["answers_by_country"] == {"IN": {"expected_pay": INDIA_PAY}}
    assert _stored(tmp_path) == {"preferences": {"desired_salary": "$95,000"},
                                 "answers_by_country": {"IN": {"expected_pay": INDIA_PAY}}}


def test_a_home_entry_keeps_its_other_answers_and_a_blank_pay_moves_nothing(db_session, tmp_path):
    _live_in("IN", ["IN"], db_session)
    autofill_profile.set_profile(
        {"preferences": {"desired_salary": INDIA_PAY},
         "answers_by_country": {"IN": {"expected_pay": " ", "current_ctc": "₹25,00,000"}}}, db_session)
    assert _stored(tmp_path) == {"preferences": {"desired_salary": INDIA_PAY},
                                 "answers_by_country": {"IN": {"current_ctc": "₹25,00,000"}}}


def test_an_unchanged_home_entry_does_not_overwrite_a_new_desired_salary(db_session, tmp_path):
    """A save of the read view: the view served the stored home pay as `desired_salary`, and the
    home entry it echoes holds the rest of that country's answers. The stored pay is not merged back
    into the entry, so the new `desired_salary` is what is kept."""
    _live_in("IN", ["IN"], db_session)
    _write(db_session, {"preferences": {"desired_salary": "₹30,00,000"},
                        "answers_by_country": {"IN": {"expected_pay": INDIA_PAY, "current_ctc": "₹25,00,000"}}})
    view = autofill_profile.get_profile(db_session)
    assert view["answers_by_country"] == {"IN": {"current_ctc": "₹25,00,000"}}
    view["preferences"]["desired_salary"] = "₹45,00,000"
    autofill_profile.set_profile(view, db_session)
    assert _stored(tmp_path) == {"preferences": {"desired_salary": "₹45,00,000"},
                                 "answers_by_country": {"IN": {"current_ctc": "₹25,00,000"}}}


# --- read ---------------------------------------------------------------------------------------

def test_a_stored_home_expected_pay_wins_on_read(db_session, tmp_path):
    """Both home figures stored (written before this rule): the home's own is the one shown, and a
    read writes nothing."""
    _live_in("US", ["US", "IN"], db_session)
    stored = {"preferences": {"desired_salary": "$80,000", "notice_days": 30},
              "answers_by_country": {"US": {"expected_pay": "$95,000"}, "IN": {"expected_pay": INDIA_PAY}}}
    _write(db_session, stored)
    for view in (autofill_profile.get_profile(db_session), autofill_profile.peek_profile(db_session)):
        assert view["preferences"] == {"desired_salary": "$95,000", "notice_days": 30}
        assert view["answers_by_country"] == {"IN": {"expected_pay": INDIA_PAY}}
    assert _stored(tmp_path) == stored


def test_unchosen_folds_nothing(db_session, tmp_path):
    """With no country chosen the stored home is the default, not a choice: `desired_salary` is the
    one figure, and an entry under the default's key stays where it is, on read and on save. A
    legacy one-set `work_auth` is still read as that default's, as before."""
    assert market_settings.peek_market(db_session).chosen is False
    stored = {"preferences": {"desired_salary": "$80,000"},
              "answers_by_country": {"US": {"expected_pay": "$95,000"}},
              "work_auth": {"authorized_now": True}}
    _write(db_session, stored)
    view = autofill_profile.get_profile(db_session)
    assert view["preferences"] == {"desired_salary": "$80,000"}
    assert view["answers_by_country"] == {"US": {"expected_pay": "$95,000"}}
    assert view["work_auth_by_country"] == {"US": {"authorized_now": True}}
    assert (view["work_auth"], view["work_auth_market"]) == ({"authorized_now": True}, "US")

    view["answers_by_country"]["US"]["expected_pay"] = "$99,000"
    saved = autofill_profile.set_profile(view, db_session)
    assert saved["preferences"] == {"desired_salary": "$80,000"}
    assert _stored(tmp_path)["answers_by_country"] == {"US": {"expected_pay": "$99,000"}}
    assert _stored(tmp_path)["preferences"] == {"desired_salary": "$80,000"}


# --- pay_for ------------------------------------------------------------------------------------

def test_pay_for_home_other_none_and_no_market(db_session):
    _live_in("US", ["US", "IN", "IE"], db_session)
    autofill_profile.set_profile({"preferences": {"desired_salary": "$80,000"},
                                  "answers_by_country": {"IN": {"expected_pay": INDIA_PAY},
                                                         "IE": {"expected_pay": " "}}}, db_session)
    view = autofill_profile.get_profile(db_session)
    assert autofill_profile.pay_for(view, "US", "US") == "$80,000"
    assert autofill_profile.pay_for(view, "in", "US") == INDIA_PAY
    assert autofill_profile.pay_for(view, "IE", "US") is None      # a blank is no pay of its own
    assert autofill_profile.pay_for(view, "UK", "US") is None      # never the home figure
    assert autofill_profile.pay_for(view, None, "US") == "$80,000"  # no market: the home pay
    assert autofill_profile.pay_for({}, "US", "US") is None


# --- move ---------------------------------------------------------------------------------------

def test_moving_home_pins_the_old_pay_and_adopts_the_new(db_session):
    _live_in("US", ["US", "IN", "IE"], db_session)
    autofill_profile.set_profile({"preferences": {"desired_salary": "$80,000"},
                                  "answers_by_country": {"IN": {"expected_pay": INDIA_PAY}}}, db_session)
    _live_in("IN", ["US", "IN", "IE"], db_session)
    view = autofill_profile.get_profile(db_session)
    assert view["preferences"]["desired_salary"] == INDIA_PAY
    assert view["answers_by_country"] == {"US": {"expected_pay": "$80,000"}}

    _live_in("IE", ["US", "IN", "IE"], db_session)   # Ireland has no pay of its own: none is its
    view = autofill_profile.get_profile(db_session)
    assert "desired_salary" not in view.get("preferences", {})
    assert view["answers_by_country"] == {"US": {"expected_pay": "$80,000"}, "IN": {"expected_pay": INDIA_PAY}}
    assert autofill_profile.pay_for(view, "IE", "IE") is None

    _live_in("US", ["US", "IN", "IE"], db_session)   # and back: each country kept its own
    view = autofill_profile.get_profile(db_session)
    assert view["preferences"]["desired_salary"] == "$80,000"
    assert view["answers_by_country"] == {"IN": {"expected_pay": INDIA_PAY}}


def test_a_move_keeps_the_old_homes_own_pay_over_the_generic_one(db_session, tmp_path):
    """Both home figures stored: the home's own was the one read, so it is the one pinned."""
    _live_in("US", ["US", "IN"], db_session)
    _write(db_session, {"preferences": {"desired_salary": "$80,000"},
                        "answers_by_country": {"US": {"expected_pay": "$95,000"}}})
    _live_in("IN", ["US", "IN"], db_session)
    view = autofill_profile.get_profile(db_session)
    assert "desired_salary" not in view.get("preferences", {})
    assert view["answers_by_country"] == {"US": {"expected_pay": "$95,000"}}


def test_the_pin_alone_changes_no_read(db_session, tmp_path):
    """`set_market` pins before the move lands, so a failure between the two must leave every read
    as it was: the old home's pay is pinned to it and read back as `desired_salary` while it is
    still home, and the new home's own figure stays in its entry until the move makes it home."""
    _live_in("US", ["US", "IN"], db_session)
    _write(db_session, {"preferences": {"desired_salary": "$80,000", "notice_days": 30},
                        "answers_by_country": {"IN": {"expected_pay": INDIA_PAY}}})
    before = autofill_profile.get_profile(db_session)
    autofill_profile.pin_home_pay("US", db_session)
    assert autofill_profile.get_profile(db_session) == before
    assert _stored(tmp_path) == {"preferences": {"notice_days": 30}, "answers_by_country": {
        "US": {"expected_pay": "$80,000"}, "IN": {"expected_pay": INDIA_PAY}}}


def test_a_first_choice_of_countries_pins_nothing(db_session, tmp_path):
    """Unchosen, `desired_salary` is the one figure in whatever currency was meant: the first choice
    adopts it as the new home's pay. A legacy one-set `work_auth` is still pinned to the default it
    was read as, as before."""
    _write(db_session, {"preferences": {"desired_salary": "$80,000"}, "work_auth": {"authorized_now": True}})
    _live_in("IN", ["IN"], db_session)
    stored = _stored(tmp_path)
    assert stored["preferences"] == {"desired_salary": "$80,000"} and "answers_by_country" not in stored
    assert stored["work_auth_by_country"] == {"US": {"authorized_now": True}}
    assert autofill_profile.get_profile(db_session)["preferences"]["desired_salary"] == "$80,000"
