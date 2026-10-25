"""Market vocabulary and the setting it drives.

The EEO assertions are the load-bearing ones: an unverified market must offer
NO demographic question set rather than falling back to the US one. Categories
are not interchangeable across countries (an Arab candidate is "White" on the
US EEO-1 form and "Other ethnic group / Arab" on the UK GSS list), so a
fallback does not degrade gracefully — it files a false answer.
"""

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas.market_settings import MarketSetting
from app.services import market_settings, markets

client = TestClient(app)


SUPPORTED = ["US", "UK", "CA", "AU", "IE", "IN", "DE", "NL"]


def test_supported_markets_are_the_declared_eight():
    assert markets.keys() == SUPPORTED


@pytest.mark.parametrize(
    "market,currency",
    [("US", "USD"), ("UK", "GBP"), ("CA", "CAD"), ("AU", "AUD"), ("IE", "EUR"), ("IN", "INR"),
     ("DE", "EUR"), ("NL", "EUR")],
)
def test_each_market_has_its_own_currency(market, currency):
    assert markets.currency_for(market) == currency


@pytest.mark.parametrize("market,label", [("DE", "Germany"), ("NL", "Netherlands")])
def test_germany_and_the_netherlands_are_data_with_no_diversity_set(market, label):
    """Added as data alone: day-first dates, the generic work-permit wording and no EEO module,
    because no German or Dutch question set has been checked against a primary source."""
    assert markets.is_supported(market) and markets.is_supported(market.lower())
    entry = markets.get(market)
    assert (entry["label"], entry["date_format"]) == (label, "DMY")
    assert entry["eeo_module"] is None and markets.offers_eeo(market) is False
    assert entry["work_auth_vocab"] == "generic"


@pytest.mark.parametrize(
    "market,asks,word",
    [("US", True, "State"), ("CA", True, "Province"), ("AU", True, "State"), ("IN", True, "State"),
     ("UK", False, "County"), ("IE", False, "County"), ("DE", False, "State"), ("NL", False, "Province")],
)
def test_each_market_says_whether_its_addresses_need_a_state_and_its_word_for_one(market, asks, word):
    """`asks_state` follows the address formats a form there requires (a state or province in the US,
    Canada, Australia and India; Ireland writes a county but requires none). `state_label` is the
    country's own word, which the Contact field shows."""
    entry = markets.get(market)
    assert (entry["asks_state"], entry["state_label"]) == (asks, word)


def test_every_market_declares_its_state_line_rather_than_taking_a_default():
    raw = markets._DATA_FILE.read_text(encoding="utf-8")
    assert raw.count("asks_state:") == raw.count("state_label:") == len(SUPPORTED)


@pytest.mark.parametrize("market", ["CA", "AU", "IE", "IN", "DE", "NL"])
def test_unverified_markets_offer_no_eeo_module(market):
    """The whole point of the eeo_module field.

    If this ever starts returning True for a market, it must be because someone
    verified that market's question set against a primary source — not because
    a default leaked through.
    """
    assert markets.offers_eeo(market) is False


@pytest.mark.parametrize("market", ["US", "UK"])
def test_verified_markets_offer_eeo(market):
    assert markets.offers_eeo(market) is True


def test_unknown_market_falls_back_rather_than_raising():
    """A stored value for a market later removed from the YAML must still
    render. Validation of human input happens at the API boundary instead."""
    assert markets.get("ZZ")["key"] == markets.DEFAULT_MARKET
    assert markets.is_supported("ZZ") is False


def test_market_keys_map_to_iso_country_codes_and_back():
    """Jobs and base resumes store ISO codes ("GB"); market keys stay as written ("UK")."""
    assert markets.country_code("UK") == "GB"
    assert markets.country_code("de") == "DE"
    assert markets.country_code("ZZ") is None
    assert markets.for_country("GB") == "UK"
    assert markets.for_country("nl") == "NL"
    assert markets.for_country("FR") is None  # a country with no market is no market
    assert markets.for_country(None) is None
    for key in markets.keys():
        assert markets.for_country(markets.country_code(key)) == key


# ---------------------------------------------------------------- home + apply_in


def test_a_legacy_single_market_reads_as_home_and_apply_in():
    setting = MarketSetting.model_validate({"market": "UK"})
    assert setting.home == "UK" and setting.apply_in == ["UK"]


def test_apply_in_always_holds_known_markets_once():
    setting = MarketSetting.model_validate({"home": "DE", "apply_in": ["de", "UK", "UK", "US"]})
    assert setting.apply_in == ["DE", "UK", "US"]


def test_an_unknown_market_is_refused_not_coerced():
    with pytest.raises(ValidationError):
        MarketSetting.model_validate({"home": "XX", "apply_in": ["XX"]})
    with pytest.raises(ValidationError):
        MarketSetting.model_validate({"home": "UK", "apply_in": ["UK", "XX"]})
    with pytest.raises(ValidationError):
        MarketSetting.model_validate({"market": "XX"})


def test_home_alone_applies_in_home_and_need_not_be_in_apply_in():
    assert MarketSetting.model_validate({"home": "NL"}).apply_in == ["NL"]
    lives_away = MarketSetting.model_validate({"home": "UK", "apply_in": ["DE"]})
    assert (lives_away.home, lives_away.apply_in) == ("UK", ["DE"])


def test_the_old_market_name_reads_home_and_is_stored_for_peers_not_yet_updated():
    """`market` is the read-only stand-in for callers not moved to `home` yet (SYSTEM.md §13
    market-home-apply-in), and it is written into the stored JSON so a sync peer that has not
    updated reads the same country instead of falling back to US."""
    setting = MarketSetting(home="DE", apply_in=["DE", "NL"])
    assert setting.market == "DE"
    stored = json.loads(setting.model_dump_json())
    assert stored == {"home": "DE", "apply_in": ["DE", "NL"], "market": "DE"}
    assert MarketSetting.model_validate(stored) == setting


def test_a_stored_legacy_blob_is_mapped_when_read_and_never_rewritten():
    from app.db import SessionLocal
    from app.models.setting import Setting

    with SessionLocal() as s:
        row = s.get(Setting, market_settings.MARKET_KEY)
        if row is None:
            row = Setting(key=market_settings.MARKET_KEY, value="")
            s.add(row)
        row.value = json.dumps({"market": "IN"})
        s.commit()
        assert market_settings.peek_market(s).home == "IN"
        assert market_settings.get_market(s).apply_in == ["IN"]
        s.refresh(row)
        assert json.loads(row.value) == {"market": "IN"}  # mapped when read, never migrated
    client.put("/api/settings/market", json={"value": {"market": "US"}})


def test_get_market_returns_the_picker_and_the_eeo_posture():
    body = client.get("/api/settings/market").json()
    assert body["key"] == "market"
    assert [m["key"] for m in body["markets"]] == SUPPORTED
    # the picker carries offers_eeo so the frontend never decides this itself
    assert {m["key"]: m["offers_eeo"] for m in body["markets"]}["IN"] is False
    uk = next(m for m in body["markets"] if m["key"] == "UK")
    assert uk == {"key": "UK", "label": "United Kingdom", "country_code": "GB", "currency": "GBP",
                  "date_format": "DMY", "offers_eeo": True, "work_auth_vocab": "uk",
                  "asks_state": False, "state_label": "County"}
    # Each market's work-permit wording rides along (data), so the Profile asks it per country.
    vocab = {m["key"]: m["work_auth_vocab"] for m in body["markets"]}
    assert (vocab["US"], vocab["DE"], vocab["IN"]) == ("us_visa", "generic", "generic")


def test_put_market_takes_home_and_apply_in_or_the_old_single_market():
    new = client.put("/api/settings/market", json={"value": {"home": "UK", "apply_in": ["UK", "de"]}})
    assert new.status_code == 200, new.text
    body = new.json()
    assert (body["home"], body["apply_in"]) == ("UK", ["UK", "DE"])
    assert body["value"] == {"home": "UK", "apply_in": ["UK", "DE"], "market": "UK"}
    assert body["currency"] == "GBP"
    got = client.get("/api/settings/market").json()
    assert (got["home"], got["apply_in"]) == ("UK", ["UK", "DE"])

    old = client.put("/api/settings/market", json={"value": {"market": "NL"}})
    assert old.status_code == 200, old.text
    assert (old.json()["home"], old.json()["apply_in"]) == ("NL", ["NL"])

    refused = client.put("/api/settings/market", json={"value": {"home": "UK", "apply_in": ["XX"]}})
    assert refused.status_code == 422
    client.put("/api/settings/market", json={"value": {"market": "US"}})


def test_put_market_switches_currency_and_eeo_posture():
    india = client.put("/api/settings/market", json={"value": {"market": "IN"}})
    assert india.status_code == 200, india.text
    assert india.json()["currency"] == "INR"
    assert india.json()["offers_eeo"] is False

    us = client.put("/api/settings/market", json={"value": {"market": "US"}})
    assert us.json()["currency"] == "USD"
    assert us.json()["offers_eeo"] is True


def test_invalid_market_422s_rather_than_defaulting():
    """Validated, never normalized — a typo must not silently become US, which
    would mean the wrong currency AND the wrong demographic question set."""
    resp = client.put("/api/settings/market", json={"value": {"market": "ZZ"}})
    assert resp.status_code == 422


def test_market_is_case_insensitive_on_input():
    resp = client.put("/api/settings/market", json={"value": {"market": "uk"}})
    assert resp.status_code == 200
    assert resp.json()["value"]["market"] == "UK"
    client.put("/api/settings/market", json={"value": {"market": "US"}})


def test_non_eeo_market_can_reach_full_autofill_readiness():
    """The point of gating the EEO group.

    `_EEO` is the US set — veteran status, CC-305 disability, and the EEO-1's
    two-part hispanic_latino split. Counting it as required made 100% readiness
    unreachable for every non-US user, since those questions have no answer to
    give. Switching market must change the DENOMINATOR, not just hide the form.

    Every answer but the diversity set is given, for both countries: work-permit answers are per
    country, so this profile is its own and not whatever an earlier test left in the settings.
    """
    from app.services import setup_status

    work_auth = {"status": "citizen", "authorized_now": True, "sponsorship_now": False, "sponsorship_future": False}
    before = client.get("/api/settings/autofill").json()["value"]
    client.put("/api/settings/autofill", json={"value": {
        "personal": {key: "x" for key in setup_status._PERSONAL},
        "preferences": {key: "x" for key in setup_status._PREFERENCES},
        "work_auth_by_country": {"US": work_auth, "IN": work_auth},
    }})
    try:
        client.put("/api/settings/market", json={"value": {"market": "US"}})
        us = client.get("/api/setup/status").json()["autofill"]
        assert "eeo" in us["groups"]

        client.put("/api/settings/market", json={"value": {"market": "IN"}})
        india = client.get("/api/setup/status").json()["autofill"]
        assert "eeo" not in india["groups"], "EEO must not be required in a market with no module"

        us_answerable = sum(g["answerable"] for g in us["groups"].values())
        in_answerable = sum(g["answerable"] for g in india["groups"].values())
        # The four US EEO fields leave the denominator, and so does the US visa status, which only a
        # market whose work_auth_vocab is us_visa asks.
        assert in_answerable == us_answerable - 4 - 1, "the four US EEO fields leave the denominator"
        assert india["readiness"] == 1.0 > us["readiness"]
    finally:
        client.put("/api/settings/market", json={"value": {"market": "US"}})
        had = before.get("work_auth_by_country") or {}
        restore = {k: v for k, v in before.items() if k not in ("work_auth", "work_auth_market")}
        restore["work_auth_by_country"] = {**had, "US": had.get("US"), "IN": had.get("IN")}
        client.put("/api/settings/autofill", json={"value": restore})


def test_capture_currency_follows_the_selected_market():
    """A job captured while the market is India must be stamped INR, not USD."""
    from app.models.job import Job
    from app.routers.jobs import _apply_extraction
    from app.db import SessionLocal

    extraction = {"company": "Acme", "salary_min": 100, "salary_max": 200, "salary_period": "year"}
    with SessionLocal() as s:
        client.put("/api/settings/market", json={"value": {"market": "IN"}})
        job = Job(raw_text="x", raw_text_hash="a" * 64, source="user")
        _apply_extraction(job, dict(extraction), s)
        assert job.salary_currency == "INR"
        assert job.salary_currency_assumed is True  # the job names no country: the home currency

        client.put("/api/settings/market", json={"value": {"market": "UK"}})
        job = Job(raw_text="y", raw_text_hash="b" * 64, source="user")
        _apply_extraction(job, dict(extraction), s)
        assert job.salary_currency == "GBP"

        # an explicit currency in the posting always wins over the market
        job = Job(raw_text="z", raw_text_hash="c" * 64, source="user")
        _apply_extraction(job, dict(extraction, salary_currency="eur"), s)
        assert job.salary_currency == "EUR"
        assert job.salary_currency_assumed is False

        # a job in a country takes that country's currency before the market's, still assumed
        job = Job(raw_text="v", raw_text_hash="e" * 64, source="user")
        _apply_extraction(job, dict(extraction, country="DE"), s)
        assert (job.salary_currency, job.salary_currency_assumed) == ("EUR", True)

        # and a posting with no pay still gets no currency invented for it
        job = Job(raw_text="w", raw_text_hash="d" * 64, source="user")
        _apply_extraction(job, {"company": "Acme"}, s)
        assert job.salary_currency is None
    client.put("/api/settings/market", json={"value": {"market": "US"}})


def test_a_jobs_default_currency_is_its_own_countrys_then_the_home_currency():
    """A German job saved by someone who lives in the UK is posted in euros; a job that names no
    country (or a country with no currency in the data) takes the home currency. Both are
    assumptions, and the job says so."""
    from app.db import SessionLocal
    from app.models.job import Job
    from app.routers.jobs import _apply_extraction

    client.put("/api/settings/market", json={"value": {"home": "UK", "apply_in": ["UK", "DE"]}})
    pay = {"company": "Acme", "salary_min": 70000, "salary_max": 85000, "salary_period": "year"}
    with SessionLocal() as s:
        assert market_settings.default_currency_for_capture(s, "DE") == "EUR"
        assert market_settings.default_currency_for_capture(s, "de") == "EUR"
        assert market_settings.default_currency_for_capture(s, None) == "GBP"
        assert market_settings.default_currency_for_capture(s, "AQ") == "GBP"  # no currency: home

        german = Job(raw_text="de", raw_text_hash="f" * 64, source="user")
        _apply_extraction(german, dict(pay, location="Berlin, Germany"), s)
        assert german.country_code == "DE"
        assert (german.salary_currency, german.salary_currency_assumed) == ("EUR", True)

        nowhere = Job(raw_text="nowhere", raw_text_hash="9" * 64, source="user")
        _apply_extraction(nowhere, dict(pay, location="Remote"), s)
        assert nowhere.country_code is None
        assert (nowhere.salary_currency, nowhere.salary_currency_assumed) == ("GBP", True)
    client.put("/api/settings/market", json={"value": {"market": "US"}})


def test_with_no_market_chosen_the_deployment_currency_answers(monkeypatch):
    """Precedence: the job's country, else the home market the user chose, else HOME_CURRENCY."""
    from app.config import settings
    from app.db import SessionLocal

    client.put("/api/settings/market", json={"value": {"market": "US"}})  # the default: not chosen
    monkeypatch.setattr(settings, "home_currency", "CHF")
    with SessionLocal() as s:
        assert market_settings.default_currency_for_capture(s, None) == "CHF"
        assert market_settings.default_currency_for_capture(s, "NL") == "EUR"


def test_offers_eeo_answers_per_country_and_for_where_you_apply(db_session, tmp_path, monkeypatch):
    """A country has a diversity set only when its market has a checked module (US, UK today); a
    country no market covers has none, never the default market's."""
    from app.services import text_settings

    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)
    market_settings.set_market(MarketSetting(home="DE", apply_in=["DE", "NL"]), db_session)
    assert market_settings.offers_eeo(db_session) is False
    for country, offered in (("US", True), ("UK", True), ("GB", True), ("DE", False), ("FR", False)):
        assert market_settings.offers_eeo(db_session, country) is offered, country

    market_settings.set_market(MarketSetting(home="DE", apply_in=["DE", "UK"]), db_session)
    assert market_settings.offers_eeo(db_session) is True
