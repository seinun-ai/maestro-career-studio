"""ECB reference rates: parse the daily file, cache it on this machine, fetch at most once a day.

The cache is machine-local (each copy fetches its own; it is not the user's profile), the fetch
is injectable so no test touches the network, and with no cache a conversion has no rate rather
than a made-up one.
"""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.config import settings
from app.models.setting import Setting
from app.services import fx_rates, money

FIXTURE = Path(__file__).parent / "fixtures" / "ecb_eurofxref_daily.xml"
XML = FIXTURE.read_text(encoding="utf-8")
DAY = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
REAL_FETCH = fx_rates.fetch_text  # kept before the autouse fixture swaps it out


class Fetch:
    """A stand-in for the network: counts calls, answers with the fixture or fails."""

    def __init__(self, text: str | None = XML):
        self.text = text
        self.urls: list[str] = []

    def __call__(self, url: str) -> str:
        self.urls.append(url)
        if self.text is None:
            raise httpx.ConnectError("offline")
        return self.text


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """A route that forgets to take the stub fails loudly instead of reaching the ECB."""

    def refuse(url: str) -> str:
        raise AssertionError(f"tried the network: {url}")

    monkeypatch.setattr(fx_rates, "fetch_text", refuse)


def test_parse_reads_the_date_and_every_rate_against_the_euro():
    parsed = fx_rates.parse_ecb_xml(XML)
    assert parsed["base"] == "EUR" and parsed["date"] == "2026-10-19"
    assert parsed["rates"]["USD"] == Decimal("1.0870")
    assert parsed["rates"]["GBP"] == Decimal("0.87700")
    assert len(parsed["rates"]) == 29 and "EUR" not in parsed["rates"]
    assert all(isinstance(rate, Decimal) and rate > 0 for rate in parsed["rates"].values())


@pytest.mark.parametrize("text", [
    "",
    "not xml",
    "<gesmes:Envelope xmlns:gesmes='http://www.gesmes.org/xml/2002-08-01'/>",  # no day
    XML.replace("rate='1.0870'", "rate='lots'"),
    XML.replace("rate='1.0870'", "rate='-1'"),
    XML.replace("<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
                "<?xml version=\"1.0\"?><!DOCTYPE x [<!ENTITY a \"aaaa\">]>"),
])
def test_parse_refuses_anything_that_is_not_the_ecb_file(text):
    with pytest.raises(ValueError):
        fx_rates.parse_ecb_xml(text)


def test_no_cache_means_no_rate_never_an_invented_one(db_session):
    assert fx_rates.current(db_session) is None
    assert money.convert(Decimal("100"), "USD", "EUR", fx_rates.current(db_session)) is None


def test_current_is_a_read_that_writes_nothing(db_session):
    fx_rates.current(db_session)
    assert db_session.get(Setting, fx_rates.KEY) is None


def test_one_fetch_per_day(db_session):
    fetch = Fetch()
    first = fx_rates.refresh(db_session, fetch=fetch, now=DAY)
    assert fetch.urls == [fx_rates.ECB_URL]
    assert first["date"] == "2026-10-19" and first["rates"]["USD"] == Decimal("1.0870")

    fx_rates.refresh(db_session, fetch=fetch, now=DAY + timedelta(hours=1))
    fx_rates.refresh(db_session, fetch=fetch, now=DAY + timedelta(hours=23, minutes=59))
    assert len(fetch.urls) == 1  # the cache is younger than a day

    fx_rates.refresh(db_session, fetch=fetch, now=DAY + timedelta(days=1, minutes=1))
    assert len(fetch.urls) == 2  # older than a day, and a page asked

    stored = json.loads(db_session.get(Setting, fx_rates.KEY).value)
    assert stored["base"] == "EUR" and stored["rates"]["USD"] == "1.0870"  # exact, as published
    assert stored["fetched_at"].startswith("2026-10-21T09:01")


def test_offline_keeps_the_last_cache_and_waits_before_trying_again(db_session):
    fx_rates.refresh(db_session, fetch=Fetch(), now=DAY)
    offline = Fetch(text=None)
    later = DAY + timedelta(days=2)
    kept = fx_rates.refresh(db_session, fetch=offline, now=later)
    assert kept["date"] == "2026-10-19" and kept["rates"]["GBP"] == Decimal("0.87700")
    assert len(offline.urls) == 1

    fx_rates.refresh(db_session, fetch=offline, now=later + timedelta(minutes=30))
    assert len(offline.urls) == 1  # a failed try waits an hour, so offline pages do not each wait 5 s
    fx_rates.refresh(db_session, fetch=offline, now=later + timedelta(hours=1, minutes=1))
    assert len(offline.urls) == 2
    assert fx_rates.current(db_session)["fetched_at"] == DAY.isoformat()


def test_a_bad_answer_from_the_ecb_keeps_the_cache(db_session):
    fx_rates.refresh(db_session, fetch=Fetch(), now=DAY)
    kept = fx_rates.refresh(db_session, fetch=Fetch(text="<html>maintenance</html>"),
                            now=DAY + timedelta(days=1, hours=1))
    assert kept["rates"]["USD"] == Decimal("1.0870")


def test_offline_with_no_cache_stays_empty(db_session):
    assert fx_rates.refresh(db_session, fetch=Fetch(text=None), now=DAY) is None
    assert fx_rates.current(db_session) is None


def test_force_fetches_now_and_reports_a_failure(db_session):
    fetch = Fetch()
    fx_rates.refresh(db_session, fetch=fetch, now=DAY)
    fx_rates.fetch_now(db_session, fetch=fetch, now=DAY + timedelta(minutes=5))
    assert len(fetch.urls) == 2
    with pytest.raises(fx_rates.FetchFailed):
        fx_rates.fetch_now(db_session, fetch=Fetch(text=None), now=DAY + timedelta(minutes=6))
    assert fx_rates.current(db_session)["rates"]["USD"] == Decimal("1.0870")


def test_the_default_fetch_uses_the_shared_client_with_a_five_second_timeout(monkeypatch):
    from app.services import http_client

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, text=XML)

    def new_client(**kwargs):
        seen["timeout"] = kwargs.get("timeout")
        return httpx.Client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(http_client, "new_client", new_client)
    assert REAL_FETCH(fx_rates.ECB_URL) == XML
    assert seen == {"url": fx_rates.ECB_URL, "timeout": fx_rates.TIMEOUT_S}
    assert fx_rates.TIMEOUT_S == 5


# ---------------------------------------------------------------- routes


def test_get_rates_fetches_when_stale_and_answers_from_the_cache(client, monkeypatch):
    fetch = Fetch()
    monkeypatch.setattr(fx_rates, "fetch_text", fetch)
    body = client.get("/api/fx/rates").json()
    assert body["base"] == "EUR" and body["date"] == "2026-10-19"
    assert body["rates"]["USD"] == pytest.approx(1.087)
    assert body["source"] == "European Central Bank" and body["source_url"] == fx_rates.ECB_URL
    assert client.get("/api/fx/rates").json()["date"] == "2026-10-19"
    assert len(fetch.urls) == 1


def test_get_rates_with_no_cache_and_no_network_says_there_are_none(client, monkeypatch):
    monkeypatch.setattr(fx_rates, "fetch_text", Fetch(text=None))
    body = client.get("/api/fx/rates").json()
    assert body["date"] is None and body["rates"] == {} and body["fetched_at"] is None


def test_refresh_route_fetches_now_or_says_it_could_not(client, monkeypatch):
    monkeypatch.setattr(fx_rates, "fetch_text", Fetch(text=None))
    failed = client.post("/api/fx/rates/refresh")
    assert failed.status_code == 502
    assert failed.json()["detail"] == "Couldn't get today's rates from the European Central Bank."
    monkeypatch.setattr(fx_rates, "fetch_text", Fetch())
    done = client.post("/api/fx/rates/refresh")
    assert done.status_code == 200 and done.json()["date"] == "2026-10-19"


# ---------------------------------------------------------------- sync


def test_the_cache_is_machine_local_and_writable_on_the_always_on_copy(db_session, tmp_path, monkeypatch):
    from app.services.sync import registry, status

    assert not registry.is_profile_row(Setting(key=fx_rates.KEY, value="{}"))
    monkeypatch.setattr(settings, "sync_key_file", tmp_path / "sync.key")
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")
    status.create_key()
    assert status.is_remote()
    fetch = Fetch()
    assert fx_rates.refresh(db_session, fetch=fetch, now=DAY)["date"] == "2026-10-19"
    assert len(fetch.urls) == 1
