"""Market vocabulary and the setting it drives.

The EEO assertions are the load-bearing ones: an unverified market must offer
NO demographic question set rather than falling back to the US one. Categories
are not interchangeable across countries (an Arab candidate is "White" on the
US EEO-1 form and "Other ethnic group / Arab" on the UK GSS list), so a
fallback does not degrade gracefully — it files a false answer.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import markets

client = TestClient(app)


def test_supported_markets_are_the_declared_six():
    assert markets.keys() == ["US", "UK", "CA", "AU", "IE", "IN"]


@pytest.mark.parametrize(
    "market,currency",
    [("US", "USD"), ("UK", "GBP"), ("CA", "CAD"), ("AU", "AUD"), ("IE", "EUR"), ("IN", "INR")],
)
def test_each_market_has_its_own_currency(market, currency):
    assert markets.currency_for(market) == currency


@pytest.mark.parametrize("market", ["CA", "AU", "IE", "IN"])
def test_unverified_markets_offer_no_eeo_module(market):
    """The whole point of the eeo_module field.

    If this ever starts returning True for a market, it must be because someone
    verified that market's question set against a primary source — not because
    a default leaked through.
    """
    assert markets.offers_eeo(market) is False
    assert markets.eeo_module(market) is None


@pytest.mark.parametrize("market,module", [("US", "us_eeo1"), ("UK", "uk_gss")])
def test_verified_markets_name_their_module(market, module):
    assert markets.offers_eeo(market) is True
    assert markets.eeo_module(market) == module


def test_unknown_market_falls_back_rather_than_raising():
    """A stored value for a market later removed from the YAML must still
    render. Validation of human input happens at the API boundary instead."""
    assert markets.get("ZZ")["key"] == markets.DEFAULT_MARKET
    assert markets.is_supported("ZZ") is False


def test_get_market_returns_the_picker_and_the_eeo_posture():
    body = client.get("/api/settings/market").json()
    assert body["key"] == "market"
    assert [m["key"] for m in body["supported"]] == ["US", "UK", "CA", "AU", "IE", "IN"]
    # the picker carries offers_eeo so the frontend never decides this itself
    assert {m["key"]: m["offers_eeo"] for m in body["supported"]}["IN"] is False


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
    """
    client.put("/api/settings/market", json={"value": {"market": "US"}})
    us = client.get("/api/setup/status").json()["autofill"]
    assert "eeo" in us["groups"]

    client.put("/api/settings/market", json={"value": {"market": "IN"}})
    india = client.get("/api/setup/status").json()["autofill"]
    assert "eeo" not in india["groups"], "EEO must not be required in a market with no module"

    us_answerable = sum(g["answerable"] for g in us["groups"].values())
    in_answerable = sum(g["answerable"] for g in india["groups"].values())
    assert in_answerable == us_answerable - 4, "the four US EEO fields leave the denominator"
    assert india["readiness"] >= us["readiness"]

    client.put("/api/settings/market", json={"value": {"market": "US"}})


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

        client.put("/api/settings/market", json={"value": {"market": "UK"}})
        job = Job(raw_text="y", raw_text_hash="b" * 64, source="user")
        _apply_extraction(job, dict(extraction), s)
        assert job.salary_currency == "GBP"

        # an explicit currency in the posting always wins over the market
        job = Job(raw_text="z", raw_text_hash="c" * 64, source="user")
        _apply_extraction(job, dict(extraction, salary_currency="eur"), s)
        assert job.salary_currency == "EUR"

        # and a posting with no pay still gets no currency invented for it
        job = Job(raw_text="w", raw_text_hash="d" * 64, source="user")
        _apply_extraction(job, {"company": "Acme"}, s)
        assert job.salary_currency is None
    client.put("/api/settings/market", json={"value": {"market": "US"}})
