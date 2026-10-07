"""The always-on copy picks a route from SYNC_REMOTE_URL and seals every call."""

import json

import httpx
import pytest

from app.config import settings
from app.services import http_client
from app.services.sync import seal, status
from app.services.sync import round as sync_round
from tests.sync.test_jobs_bundle import SENTINEL
from tests.sync.test_round import clock, go, home, world

_ = (clock, home, world)  # pytest fixtures for this module

HTTPS = "https"
TUNNEL = "tunnel"
ADDRESS = "The laptop's address must be this machine's own tunnel or an https:// address."
BUNDLE = "The certificate bundle in SSL_CERT_FILE can't be read."
UNVERIFIED = "The laptop's answer couldn't be verified."
REJECTED = (
    "The laptop didn't accept this copy's seal: the key differs, sync is off there, "
    "or the laptop has just restarted."
)
BAD_PROXY = "The proxy settings in this machine's environment can't be used."


def _route(monkeypatch, url):
    monkeypatch.setattr(settings, "sync_remote_url", url)
    assert hasattr(status, "remote_route")
    return status.remote_route()


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8101",
    "https://127.0.0.1:8101",
    "http://[::1]:8101",
    "https://[::1]:8101",
    "http://localhost:8101",
    "https://localhost",
    "https://LOCALHOST",
])
def test_loopback_http_and_https_are_the_tunnel(monkeypatch, url):
    assert _route(monkeypatch, url) == TUNNEL


@pytest.mark.parametrize("url", [
    "https://example.test",
    "https://[2001:db8::1]:8101",
    "https://example.test/",
])
def test_other_https_addresses_are_the_https_route(monkeypatch, url):
    assert _route(monkeypatch, url) == HTTPS


@pytest.mark.parametrize("url", [
    "http://10.0.0.5:8101",
    "http://example.test:8101",
    "http://127.0.0.1.evil.test",
    "http://127.0.0.1@evil.test:8101",
    "https://example.test/api/sync",
    "https://example.test/api/sync/",
    "http://127.0.0.1:8101/extra",
    "https://example.test?x=1",
    "https://example.test#frag",
    "https://user:pass@example.test",
    "https://user@127.0.0.1",
    "https://:pass@example.test",
    "http://127.0.0.1:8101?x=1",
    "http://127.0.0.1:8101#frag",
    "ftp://127.0.0.1",
    "not a url",
    "http://[",
])
def test_anything_else_is_not_a_route(monkeypatch, url):
    assert _route(monkeypatch, url) is None


def test_a_public_http_address_is_a_needs_person_skip(world, monkeypatch):
    monkeypatch.setattr(settings, "sync_remote_url", "http://10.0.0.5:8101")
    summary = sync_round.run_round(world.remote, pair=True)
    assert summary == {"ok": False, "skipped": ADDRESS, "outcome": "needs_person"}


def test_a_query_fragment_or_userinfo_is_the_same_needs_person_skip(world, monkeypatch):
    url = "https://user:SENTINEL@example.test?x=1#frag"
    monkeypatch.setattr(settings, "sync_remote_url", url)
    summary = sync_round.run_round(world.remote, pair=True)
    assert summary == {"ok": False, "skipped": ADDRESS, "outcome": "needs_person"}
    assert "SENTINEL" not in json.dumps(summary) and url not in json.dumps(summary)


def test_a_bad_certificate_bundle_is_a_needs_person_skip(world, monkeypatch, tmp_path):
    bad = tmp_path / "bad.pem"
    bad.write_text("not a certificate\n", encoding="utf-8")
    monkeypatch.setenv("SSL_CERT_FILE", str(bad))
    monkeypatch.setattr(settings, "sync_remote_url", "https://example.test")
    summary = sync_round.run_round(world.remote, pair=True, accept_profile_overwrite=True)
    assert summary == {"ok": False, "skipped": BUNDLE, "outcome": "needs_person"}
    assert "bad.pem" not in json.dumps(summary)


def _proxy_round(world, monkeypatch, proxy):
    monkeypatch.setenv("HTTPS_PROXY", proxy)
    monkeypatch.delenv("ALL_PROXY", raising=False)
    monkeypatch.delenv("all_proxy", raising=False)
    monkeypatch.setattr(settings, "sync_remote_url", "https://example.test")
    summary = sync_round.run_round(world.remote, pair=True, accept_profile_overwrite=True)
    assert summary == {"ok": False, "skipped": BAD_PROXY, "outcome": "needs_person"}
    assert proxy not in json.dumps(summary)
    assert "socks5" not in json.dumps(summary) and "ftp://" not in json.dumps(summary)


def test_a_socks_proxy_is_a_needs_person_skip(world, monkeypatch, caplog):
    caplog.set_level("DEBUG")
    proxy = "socks5://sentinel-proxy.example:1080"
    _proxy_round(world, monkeypatch, proxy)
    assert proxy not in caplog.text


def test_an_ftp_proxy_is_a_needs_person_skip(world, monkeypatch, caplog):
    caplog.set_level("DEBUG")
    proxy = "ftp://sentinel-proxy.example"
    _proxy_round(world, monkeypatch, proxy)
    assert proxy not in caplog.text


def test_a_proxy_with_a_bad_port_is_a_needs_person_skip(world, monkeypatch, caplog):
    # httpx raises InvalidURL here, which is not a ValueError.
    caplog.set_level("DEBUG")
    proxy = "http://sentinel-proxy.example:notaport"
    _proxy_round(world, monkeypatch, proxy)
    assert proxy not in caplog.text


def test_a_tunnel_ignores_a_socks_proxy(world, monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "socks5://sentinel-proxy.example:1080")
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:9")
    summary = sync_round.run_round(world.remote, pair=True)
    assert summary["outcome"] == "transient"
    assert "sentinel-proxy" not in json.dumps(summary)
    assert BAD_PROXY not in json.dumps(summary)


def _transport_round(world, monkeypatch, respond):
    def build(**kwargs):
        kwargs["transport"] = httpx.MockTransport(respond)
        return httpx.Client(**kwargs)

    monkeypatch.setattr(http_client, "new_client", build)
    return sync_round.run_round(world.remote, pair=True, accept_profile_overwrite=True)


def test_a_bare_404_needs_a_person(world, monkeypatch):
    summary = _transport_round(world, monkeypatch, lambda _request: httpx.Response(404))
    assert summary["ok"] is False and summary["outcome"] == "needs_person"
    assert summary["error"] == REJECTED
    assert UNVERIFIED not in json.dumps(summary)


def test_a_404_whose_seal_will_not_open_stays_unverified(world, monkeypatch):
    def respond(_request):
        return httpx.Response(404, content=b"x", headers={seal.HEADER: "2.not-a-nonce"})

    summary = _transport_round(world, monkeypatch, respond)
    assert summary["ok"] is False and summary["outcome"] == "transient"
    assert summary["error"] == UNVERIFIED


def test_an_https_round_trusts_the_environment_and_a_tunnel_does_not(world, monkeypatch):
    seen = []

    def build(**kwargs):
        seen.append(kwargs)

        def fail(_request):
            raise httpx.ConnectError("stop")

        return httpx.Client(transport=httpx.MockTransport(fail), **kwargs)

    monkeypatch.setattr(http_client, "new_client", build)
    monkeypatch.setattr(settings, "sync_remote_url", "https://example.test")
    https = sync_round.run_round(world.remote, pair=True)
    assert https["outcome"] == "transient"
    assert seen and seen[-1]["trust_env"] is True and seen[-1]["verify"] is True
    assert "Authorization" not in seen[-1].get("headers", {})

    status.update_state(world.remote, failures=0, next_attempt_at=None, attempted_at=None,
                        last_error=None)
    seen.clear()
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:9")
    tunnel = sync_round.run_round(world.remote, pair=True)
    assert tunnel["outcome"] == "transient"
    assert seen and seen[-1]["trust_env"] is False and seen[-1]["verify"] is True
    assert "Authorization" not in seen[-1].get("headers", {})


def test_a_forged_response_backs_off_with_the_fixed_sentence(world, home, clock):
    home.forge = True
    summary = go(world)
    assert summary["ok"] is False and summary["outcome"] == "transient"
    assert summary["error"] == UNVERIFIED
    assert SENTINEL not in json.dumps(summary)
    saved = status.read_state(world.remote)
    assert saved["last_error"] == UNVERIFIED
    assert seal.HEADER not in json.dumps(summary)
