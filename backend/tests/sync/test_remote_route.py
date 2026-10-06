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


def test_a_bad_certificate_bundle_is_a_needs_person_skip(world, monkeypatch, tmp_path):
    bad = tmp_path / "bad.pem"
    bad.write_text("not a certificate\n", encoding="utf-8")
    monkeypatch.setenv("SSL_CERT_FILE", str(bad))
    monkeypatch.setattr(settings, "sync_remote_url", "https://example.test")
    summary = sync_round.run_round(world.remote, pair=True, accept_profile_overwrite=True)
    assert summary == {"ok": False, "skipped": BUNDLE, "outcome": "needs_person"}
    assert "bad.pem" not in json.dumps(summary)


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
