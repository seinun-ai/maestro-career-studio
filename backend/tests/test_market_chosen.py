"""The market setting's `chosen` mark: a new install has chosen no country, so its form questions are
the generic set (no work-permit questions, Decision 1 of docs/plans/2026-10-30-country-form-questions.md);
saving where you apply, from the web or an agent, marks it chosen; a row stored before the mark keeps
the set it was shown, and so, at startup, does an install that never stored one but has answered
work permits. Currency ignores the mark."""

import json

import pytest

from sqlalchemy import select

from app.config import settings
from app.models.setting import Setting
from app.schemas.market_settings import MarketSetting
from app.services import autofill_profile, market_settings, text_settings


@pytest.fixture(autouse=True)
def settings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    return tmp_path


def test_a_new_install_starts_unchosen(client):
    assert client.get("/api/settings/market").json()["value"]["chosen"] is False
    served = client.get("/api/settings/autofill/questions").json()
    assert served["chosen"] is False and served.get("permits", {}) == {}


def test_saving_where_you_apply_marks_it_chosen(client):
    client.put("/api/settings/market", json={"value": {"home": "US", "apply_in": ["US"]}})
    assert market_settings.peek_market().chosen is True
    served = client.get("/api/settings/autofill/questions").json()
    assert list(served["permits"]) == ["US"]


def test_an_agent_setting_markets_marks_it_chosen(client):
    client.patch("/api/settings/market", json={"value": {"apply_in": ["DE"]}})
    assert market_settings.peek_market().chosen is True


def test_an_agent_setting_only_home_on_a_new_install_applies_there(client):
    """Unchosen, the default `apply_in` is no choice to keep: a home alone is where you apply."""
    client.patch("/api/settings/market", json={"value": {"home": "UK"}})
    stored = market_settings.peek_market()
    assert (stored.home, stored.apply_in, stored.chosen) == ("UK", ["UK"], True)


def test_a_row_stored_before_the_mark_reads_as_chosen(settings_dir):
    text_settings.set_text("market", "market.json", '{"home": "US", "apply_in": []}')
    assert market_settings.peek_market().chosen is True


def test_a_legacy_one_market_row_reads_as_chosen(settings_dir):
    """`{"market": X}` predates both `home` and the mark: that install chose X."""
    text_settings.set_text("market", "market.json", '{"market": "UK"}')
    stored = market_settings.peek_market()
    assert (stored.home, stored.apply_in, stored.chosen) == ("UK", ["UK"], True)


def test_a_row_written_with_the_mark_keeps_it(settings_dir):
    text_settings.set_text("market", "market.json", '{"home": "US", "apply_in": ["US"], "chosen": false}')
    assert market_settings.peek_market().chosen is False


def test_the_mark_leaves_currency_alone():
    # Non-goal: currency and date defaults. `is_set` ignores `chosen`.
    assert market_settings.is_set(MarketSetting(chosen=True)) is False
    assert market_settings.MARKET.is_set(MarketSetting(chosen=True)) is False
    assert market_settings.is_set(MarketSetting(home="UK", chosen=True)) is True


def test_no_country_is_applied_in_until_one_is_chosen():
    assert MarketSetting().applied == []
    assert MarketSetting(home="UK", apply_in=["UK", "DE"], chosen=True).applied == ["UK", "DE"]
    assert "applied" not in MarketSetting(chosen=True).model_dump()  # neither stored nor served


# ---------- startup: an install that answered permits keeps its country ----------

_US_ANSWER = {"work_auth_by_country": {"US": {"authorized_now": True}}}
_CHOSEN_US = {"home": "US", "apply_in": ["US"], "chosen": True, "market": "US"}


def _store_profile(profile: dict) -> None:
    text_settings.set_text(
        autofill_profile.AUTOFILL_KEY, autofill_profile.AUTOFILL_FILE, json.dumps(profile)
    )


def _market_text() -> str:
    return text_settings.peek_text(market_settings.MARKET_KEY, market_settings.MARKET_FILE)


def _checked(db_session) -> bool:
    db_session.expire_all()
    return db_session.get(Setting, market_settings.CHOSEN_CHECKED_FLAG) is not None


def _seed_empty_row(db_session) -> None:
    market_settings.get_market(db_session)  # a GET's first read seeds the row with ""


def _seed_blank_row(db_session) -> None:
    text_settings.set_text(market_settings.MARKET_KEY, market_settings.MARKET_FILE, "  \n")


@pytest.mark.parametrize("empty", [
    pytest.param(lambda db_session: None, id="no-row"),
    pytest.param(_seed_empty_row, id="seeded-empty-row"),
    pytest.param(_seed_blank_row, id="blank-row"),
])
def test_an_empty_market_with_a_us_permit_answer_is_marked_chosen_where_it_read(
    settings_dir, db_session, empty
):
    empty(db_session)
    _store_profile(_US_ANSWER)
    assert market_settings.mark_answered_installs_chosen(db_session) is True
    db_session.expire_all()
    rows = db_session.scalars(select(Setting).where(Setting.key == market_settings.MARKET_KEY)).all()
    assert len(rows) == 1 and json.loads(rows[0].value) == _CHOSEN_US
    stored = market_settings.peek_market()
    assert stored.chosen is True
    assert (stored.home, stored.apply_in) == (MarketSetting().home, MarketSetting().apply_in)
    assert _checked(db_session)


def test_a_legacy_one_set_answer_counts_too(settings_dir, db_session):
    _store_profile({"work_auth": {"authorized_to_work": True}})
    assert market_settings.mark_answered_installs_chosen(db_session) is True
    assert market_settings.peek_market().chosen is True


@pytest.mark.parametrize("profile", [
    {},
    {"personal": {"first_name": "Sam"}},
    {"work_auth_by_country": {"US": {}}},
    {"work_auth_by_country": {"US": {"status": ""}}},  # a blank select is no answer
    {"work_auth": None},
    # Another country's answer (an agent or the Companion can store one) is no choice of the default.
    {"work_auth_by_country": {"DE": {"authorized_now": True}}},
])
def test_an_empty_row_with_no_us_permit_answer_stays_unchosen(settings_dir, db_session, profile):
    _store_profile(profile)
    assert market_settings.mark_answered_installs_chosen(db_session) is False
    assert _market_text() == ""
    assert market_settings.peek_market().chosen is False
    assert _checked(db_session)


def test_a_stored_row_is_left_alone(settings_dir, db_session):
    text_settings.set_text(
        "market", "market.json", '{"home": "US", "apply_in": ["US"], "chosen": false}'
    )
    _store_profile(_US_ANSWER)
    before = _market_text()
    assert market_settings.mark_answered_installs_chosen(db_session) is False
    assert _market_text() == before
    assert market_settings.peek_market().chosen is False


def test_running_it_twice_is_a_no_op(settings_dir, db_session):
    _store_profile(_US_ANSWER)
    assert market_settings.mark_answered_installs_chosen(db_session) is True
    first = _market_text()
    assert market_settings.mark_answered_installs_chosen(db_session) is False
    assert _market_text() == first


def test_it_checks_once_so_a_later_answer_never_marks_a_new_install(settings_dir, db_session):
    """A new install answers after its first start, still unchosen: a restart must not take that for
    a choice of the default country."""
    assert market_settings.mark_answered_installs_chosen(db_session) is False
    assert _checked(db_session) and _market_text() == ""
    _store_profile(_US_ANSWER)
    assert market_settings.mark_answered_installs_chosen(db_session) is False
    assert _market_text() == ""


def test_the_flag_is_this_copys_own():
    """Each copy checks its own answers once: the flag never syncs."""
    from app.services.sync import registry

    assert not registry.is_profile_row(Setting(key=market_settings.CHOSEN_CHECKED_FLAG, value="1"))


def test_the_always_on_copy_takes_the_laptops_row(settings_dir, db_session, monkeypatch):
    """The laptop owns the profile: the always-on copy never writes it."""
    from app.services.sync import status

    monkeypatch.setattr(status, "is_remote", lambda: True)
    _store_profile(_US_ANSWER)
    assert market_settings.mark_answered_installs_chosen(db_session) is False
    assert _market_text() == ""


def test_startup_runs_the_step(settings_dir, db_session, monkeypatch):
    from app.services import seeding

    for name in ("seed_templates", "seed_base_resumes", "seed_prompts", "ensure_persona",
                 "seed_career_kb"):
        monkeypatch.setattr(seeding, name, lambda session: None)
    monkeypatch.setattr(seeding.career_exports, "best_effort_refresh", lambda session: None)
    _store_profile(_US_ANSWER)
    seeding.seed_startup_data(db_session)
    assert market_settings.peek_market().chosen is True
