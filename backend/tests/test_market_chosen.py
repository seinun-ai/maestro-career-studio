"""The market setting's `chosen` mark: a new install has chosen no country, so its form questions are
the generic set (no work-permit questions, Decision 1 of docs/plans/2026-10-30-country-form-questions.md);
saving where you apply, from the web or an agent, marks it chosen; a row stored before the mark keeps
the set it was shown. Currency ignores the mark."""

import pytest

from app.config import settings
from app.schemas.market_settings import MarketSetting
from app.services import market_settings, text_settings


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
