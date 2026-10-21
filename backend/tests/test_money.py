"""Money: the pure arithmetic (`services/money.py`) and the user's money settings.

The rules the arithmetic keeps (D8): a conversion goes through the euro on ECB reference rates
and returns None, never a guess, when a rate is missing; a range keeps both ends; missing pay
stays missing.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.config import settings
from app.schemas.money import MoneySettings
from app.services import money, money_settings

RATES = {"base": "EUR", "date": "2026-10-19", "rates": {"USD": Decimal("1.0870"), "GBP": Decimal("0.8770")}}


def test_convert_goes_through_euro_and_never_guesses():
    assert money.convert(Decimal("100"), "EUR", "EUR", RATES) == Decimal("100")
    assert money.convert(Decimal("108.70"), "USD", "EUR", RATES).quantize(Decimal("1")) == Decimal("100")
    assert money.convert(Decimal("1"), "ARS", "EUR", RATES) is None  # no ECB rate
    assert money.convert(Decimal("1"), "USD", "EUR", None) is None  # no cache yet


def test_convert_between_two_non_euro_currencies_and_its_edges():
    # 87.70 GBP = 100 EUR = 108.70 USD
    assert money.convert(Decimal("87.70"), "GBP", "USD", RATES).quantize(Decimal("0.01")) == Decimal("108.70")
    assert money.convert(Decimal("50"), "usd", "usd", None) == Decimal("50")  # same currency needs no rate
    assert money.convert(None, "USD", "EUR", RATES) is None
    assert money.convert(Decimal("1"), None, "EUR", RATES) is None
    as_text = {"base": "EUR", "rates": {"USD": "1.0870"}}  # a cache read back from JSON
    assert money.convert(Decimal("1.0870"), "USD", "EUR", as_text) == Decimal("1")


def test_yearly_uses_2080_hours_and_twelve_months():
    assert money.to_yearly(Decimal("50"), "hour") == Decimal("104000")
    assert money.to_yearly(Decimal("5000"), "month") == Decimal("60000")
    assert money.to_yearly(Decimal("1000"), "week") == Decimal("52000")
    assert money.to_yearly(Decimal("400"), "day") == Decimal("104000")  # 260 working days
    assert money.to_yearly(Decimal("1"), None) is None


def test_yearly_takes_the_users_hours_and_leaves_a_year_alone():
    assert money.to_yearly(Decimal("50"), "hour", hours_per_year=1800) == Decimal("90000")
    assert money.to_yearly(Decimal("90000"), "year") == Decimal("90000")
    assert money.to_yearly(None, "year") is None
    assert money.to_yearly(Decimal("1"), "fortnight") is None  # an unknown period is not guessed
    assert money.HOURS_PER_YEAR == 2080


def test_midpoint_of_a_range_or_the_one_end_given():
    assert money.midpoint(Decimal("70"), Decimal("90")) == Decimal("80")
    assert money.midpoint(None, Decimal("90")) == Decimal("90")
    assert money.midpoint(None, None) is None


# ---------------------------------------------------------------- settings


def test_money_settings_default_to_a_year_with_the_posted_amount_shown():
    value = MoneySettings()
    assert value.home_currency is None  # follows where you live until you pick one
    assert (value.period, value.show_posted, value.hours_per_year) == ("year", True, 2080)


def test_money_settings_refuse_what_they_cannot_use():
    assert MoneySettings(home_currency="eur").home_currency == "EUR"
    with pytest.raises(ValidationError):
        MoneySettings(home_currency="XYZ")  # not a currency the country data names
    with pytest.raises(ValidationError):
        MoneySettings(period="week")
    with pytest.raises(ValidationError):
        MoneySettings(hours_per_year=0)


@pytest.fixture
def settings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    return tmp_path


def test_the_home_currency_is_chosen_else_where_you_live_else_the_deployment(client, settings_dir, monkeypatch):
    monkeypatch.setattr(settings, "home_currency", "CHF")
    body = client.get("/api/settings/money").json()
    assert body["key"] == "money"
    assert body["value"] == {"home_currency": None, "period": "year", "show_posted": True,
                             "hours_per_year": 2080}
    assert body["home_currency"] == "CHF"  # no market chosen yet: HOME_CURRENCY

    client.put("/api/settings/market", json={"value": {"home": "DE", "apply_in": ["DE", "UK"]}})
    assert client.get("/api/settings/money").json()["home_currency"] == "EUR"  # where you live

    saved = client.put("/api/settings/money", json={"value": {
        "home_currency": "gbp", "period": "month", "show_posted": False, "hours_per_year": 1720}})
    assert saved.status_code == 200, saved.text
    assert saved.json()["home_currency"] == "GBP"  # your choice wins
    assert saved.json()["value"]["period"] == "month"
    assert (settings_dir / money_settings.MONEY_FILE).exists()  # mirrored like every profile setting
    assert client.get("/api/settings/money").json()["value"]["hours_per_year"] == 1720

    assert client.put("/api/settings/money", json={"value": {"home_currency": "XYZ"}}).status_code == 422


def test_money_is_profile_and_travels_with_the_profile():
    from app.models.setting import Setting
    from app.services.sync import profile_bundle, registry

    assert profile_bundle.MIRRORS[money_settings.MONEY_KEY] == money_settings.MONEY_FILE
    assert registry.is_profile_row(Setting(key=money_settings.MONEY_KEY, value="{}"))
