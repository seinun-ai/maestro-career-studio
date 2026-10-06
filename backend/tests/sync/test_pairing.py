"""Explicit local setup, with the no-key /api/sync/ boundary kept intact."""

import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import Request

from app.config import settings
from app.main import app
from app.models.setting import Setting
from app.routers import sync as sync_router
from app.services import http_client
from app.services.sync import status
from tests.sync import test_home_endpoints as home_tests

# Reuse the existing isolated channel fixtures without importing their test cases.
ALLOWED_ORIGIN = home_tests.ALLOWED_ORIGIN
auth, client, home_id = home_tests.auth, home_tests.client, home_tests.home_id
recv, remote_id, sync_off = home_tests.recv, home_tests.remote_id, home_tests.sync_off

WINDOW = "/api/settings/second-copy"
ENROLL = "/api/sync/enroll"
SETUP = "/api/sync-setup/enroll"
CLOSED = "Pairing isn't open on your laptop. Click Allow pairing for 10 minutes there."
KEY = "SENTINEL-PAIRING-KEY-DO-NOT-PRINT"


def put_setting(db, name, value):
    row = db.get(Setting, name)
    if row is None:
        db.add(Setting(key=name, value=value))
    else:
        row.value = value
    db.commit()


def test_all_sync_routes_are_404_without_a_key(client, sync_off):
    paths = {route.path for route in app.routes if route.path.startswith("/api/sync/")}
    assert ENROLL in paths
    for route in app.routes:
        if route.path not in paths:
            continue
        for method in route.methods:
            response = client.request(method, route.path, json={})
            assert response.status_code == 404, (method, route.path)
    assert not status.key_path().exists()


def test_no_key_settings_read_is_off_and_has_no_side_effect(client, sync_off, db_session):
    before = db_session.query(Setting).count()
    assert client.get(WINDOW).json() == {
        "enabled": False, "open_until": None, "last_paired_at": None}
    assert db_session.query(Setting).count() == before
    assert not status.key_path().exists()
    assert client.post(SETUP).status_code == 404


def test_stop_without_a_key_does_not_write_settings(client, sync_off, db_session):
    before = db_session.query(Setting).count()
    assert client.delete(WINDOW).json() == {"open_until": None}
    assert db_session.query(Setting).count() == before
    assert not status.key_path().exists()


def test_click_creates_private_key_and_opens_ten_minutes(client, sync_off):
    before = datetime.now(UTC)
    response = client.post(WINDOW, headers={"Origin": ALLOWED_ORIGIN})
    assert response.status_code == 200
    until = datetime.fromisoformat(response.json()["open_until"])
    assert before + timedelta(minutes=10) <= until <= datetime.now(UTC) + timedelta(minutes=10)
    assert status.key_path().stat().st_mode & 0o777 == 0o600
    assert status.key_path().parent.stat().st_mode & 0o777 == 0o700
    assert client.get(WINDOW).json() == {
        "enabled": True, "open_until": until.isoformat(), "last_paired_at": None}


def test_stop_closes_window_without_removing_key(client, sync_on):
    key = status.read_key()
    assert client.post(WINDOW).status_code == 200
    assert client.delete(WINDOW).json() == {"open_until": None}
    assert client.get(WINDOW).json()["open_until"] is None
    assert status.read_key() == key


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
def test_window_refuses_remote_even_without_key(client, sync_off, monkeypatch, method):
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")
    response = client.request(method, WINDOW)
    assert response.status_code == 409
    assert isinstance(response.json()["detail"], str)
    assert not status.key_path().exists()


def test_unlisted_browser_cannot_opt_in(client, sync_off):
    assert client.post(WINDOW, headers={"Origin": "https://untrusted.example"}).status_code == 403
    assert not status.key_path().exists()


def test_enroll_origin_is_refused_before_key_or_body(client, sync_on, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("must refuse before touching secrets or the body")
    monkeypatch.setattr(status, "read_key", forbidden)
    monkeypatch.setattr(Request, "body", forbidden)
    response = client.post(ENROLL, headers={"Origin": ALLOWED_ORIGIN}, content=KEY)
    assert response.status_code == 403


def test_enroll_without_key_is_404(client, sync_off):
    assert client.post(ENROLL).status_code == 404


def test_enroll_without_key_is_404_for_a_web_origin_too(client, sync_off):
    assert client.post(ENROLL, headers={"Origin": ALLOWED_ORIGIN}).status_code == 404


@pytest.mark.parametrize("until", [None, "expired", "damaged"])
def test_closed_expired_or_damaged_window_refuses(client, auth, db_session, until):
    if until:
        value = (datetime.now(UTC) - timedelta(seconds=1)).isoformat() if until == "expired" else KEY
        put_setting(db_session, "sync.pairing_until", value)
    response = client.post(ENROLL, headers=auth)
    assert response.status_code == 409
    assert response.json()["detail"] == CLOSED
    assert KEY not in response.text
    assert client.get(WINDOW).json()["open_until"] is None


@pytest.mark.parametrize("header", ["bad", "2:wrong:peer", None])
def test_enroll_version_mismatch_keeps_window_open(client, auth, header):
    assert client.post(WINDOW).status_code == 200
    headers = {"X-Maestro-Sync": header} if header else {}
    response = client.post(ENROLL, headers=headers)
    assert response.status_code == 409 and response.json()["reason"] == "version"
    assert client.get(WINDOW).json()["open_until"] is not None


def test_enroll_returns_key_once_closes_and_logs_only_fixed_line(client, auth, sync_on, caplog):
    sync_on.write_text(KEY + "\n")
    caplog.set_level(logging.DEBUG)
    client.post(WINDOW)
    response = client.post(ENROLL, headers={"X-Maestro-Sync": auth["X-Maestro-Sync"]})
    assert response.status_code == 200
    assert response.json() == {"key": KEY}
    card = client.get(WINDOW).json()
    assert card["open_until"] is None and card["last_paired_at"] is not None
    assert client.post(ENROLL, headers=auth).json()["detail"] == CLOSED
    assert sum(r.getMessage() == "A copy fetched the sync key." for r in caplog.records) == 1
    assert KEY not in caplog.text


@pytest.mark.parametrize("failure", ["closed", "version"])
def test_five_failures_limit_for_ten_minutes(client, auth, db_session, monkeypatch, failure):
    from app.services.sync import pairing
    now = datetime.now(UTC)
    monkeypatch.setattr(pairing, "utcnow", lambda: now)
    if failure == "version":
        client.post(WINDOW)
    headers = auth if failure == "closed" else {"X-Maestro-Sync": "wrong"}
    for _ in range(5):
        assert client.post(ENROLL, headers=headers).status_code == 409
    client.post(WINDOW)
    assert client.post(ENROLL, headers=auth).status_code == 429
    now += timedelta(minutes=10, seconds=1)
    client.post(WINDOW)
    assert client.post(ENROLL, headers=auth).status_code == 200


def test_enroll_uses_the_sync_single_flight_lock(client, auth):
    client.post(WINDOW)
    sync_router._LOCK.acquire()
    try:
        response = client.post(ENROLL, headers=auth)
        assert response.status_code == 409 and response.json()["reason"] == "busy"
    finally:
        sync_router._LOCK.release()
    assert client.post(ENROLL, headers=auth).status_code == 200
    assert not sync_router._LOCK.locked()


@pytest.fixture
def remote_setup(sync_off, monkeypatch):
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")
    return status.key_path()


def fake_tunnel(monkeypatch, handler):
    calls = []
    def build(**kwargs):
        assert kwargs["trust_env"] is False
        assert not kwargs.get("follow_redirects", False)
        return httpx.Client(**kwargs, transport=httpx.MockTransport(
            lambda request: (calls.append(request), handler(request))[1]))
    monkeypatch.setattr(http_client, "new_client", build)
    return calls


def test_remote_fetch_stores_private_key_and_returns_only_ok(
        client, remote_setup, db_session, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    calls = fake_tunnel(monkeypatch, lambda request: httpx.Response(200, json={"key": KEY}))
    response = client.post(SETUP)
    assert response.status_code == 200 and response.json() == {"ok": True}
    assert remote_setup.read_text().strip() == KEY
    assert remote_setup.stat().st_mode & 0o777 == 0o600
    assert remote_setup.parent.stat().st_mode & 0o777 == 0o700
    assert len(calls) == 1 and calls[0].url.path == ENROLL
    assert "authorization" not in calls[0].headers
    assert calls[0].headers["x-maestro-sync"].startswith(
        f"{status.SYNC_PROTOCOL}:{status.schema_revision(db_session)}:")
    assert KEY not in response.text + caplog.text
    assert client.post(SETUP).status_code == 409 and len(calls) == 1


@pytest.mark.parametrize("kind", ["regular", "empty", "symlink"])
def test_remote_refuses_any_existing_key_path(client, remote_setup, monkeypatch, kind):
    remote_setup.parent.mkdir(parents=True, exist_ok=True)
    if kind == "symlink":
        remote_setup.symlink_to(remote_setup.parent / "missing")
    else:
        remote_setup.write_text(KEY if kind == "regular" else "")
    calls = fake_tunnel(monkeypatch, lambda request: pytest.fail("must not fetch"))
    assert client.post(SETUP).status_code == 409 and not calls


def test_remote_write_is_exclusive_even_when_file_appears_during_fetch(
        client, remote_setup, monkeypatch):
    def reply(request):
        remote_setup.parent.mkdir(parents=True, exist_ok=True)
        remote_setup.write_text("existing-key")
        return httpx.Response(200, json={"key": KEY})
    fake_tunnel(monkeypatch, reply)
    assert client.post(SETUP).status_code == 409
    assert remote_setup.read_text() == "existing-key"


@pytest.mark.parametrize("url", ["https://outside.example", "http://127.0.0.1.outside.example"])
def test_remote_refuses_non_loopback_before_fetch(client, remote_setup, monkeypatch, url):
    monkeypatch.setattr(settings, "sync_remote_url", url)
    calls = fake_tunnel(monkeypatch, lambda request: pytest.fail("must not fetch"))
    response = client.post(SETUP)
    assert response.json()["outcome"] == "needs_person" and not calls
    assert not remote_setup.exists()


def test_remote_origin_is_refused_before_key_or_fetch(client, remote_setup, monkeypatch):
    monkeypatch.setattr(status, "read_key", lambda: pytest.fail("must not read"))
    calls = fake_tunnel(monkeypatch, lambda request: pytest.fail("must not fetch"))
    assert client.post(SETUP, headers={"Origin": ALLOWED_ORIGIN}).status_code == 403
    assert not calls and not remote_setup.exists()


def test_remote_busy_enrollment_has_a_transient_outcome(client, remote_setup):
    sync_router._LOCK.acquire()
    try:
        response = client.post(SETUP)
        assert response.status_code == 409
        assert response.json()["outcome"] == "transient"
    finally:
        sync_router._LOCK.release()
    assert not remote_setup.exists()


@pytest.mark.parametrize("case", [
    (409, "closed", "needs_person"), (409, "version", "needs_person"),
    (429, "limited", "needs_person"), (503, None, "transient"),
    (307, None, "needs_person"),
])
def test_remote_failures_have_fixed_sentences(client, remote_setup, monkeypatch, case):
    code, reason, outcome = case
    fake_tunnel(monkeypatch, lambda request: httpx.Response(
        code, json={"detail": KEY, "reason": reason}, headers={"Location": "https://outside.example"}))
    response = client.post(SETUP)
    assert response.json()["ok"] is False and response.json()["outcome"] == outcome
    if reason == "closed":
        assert response.json()["detail"] == CLOSED
    assert KEY not in response.text and not remote_setup.exists()


def test_remote_unreachable_is_transient_without_exception_text(client, remote_setup, monkeypatch):
    def unreachable(request):
        raise httpx.ConnectError(KEY)
    fake_tunnel(monkeypatch, unreachable)
    response = client.post(SETUP)
    assert response.json() == {"ok": False, "outcome": "transient", "detail": "Laptop unreachable."}
    assert not remote_setup.exists()


@pytest.mark.parametrize("body", [{"key": ""}, {"key": "a\nb"}, {"key": 3}, [], {"key": "x" * 9000}])
def test_remote_rejects_unusable_answers_without_writing(client, remote_setup, monkeypatch, body):
    fake_tunnel(monkeypatch, lambda request: httpx.Response(200, json=body))
    response = client.post(SETUP)
    assert response.json()["outcome"] == "needs_person" and not remote_setup.exists()


def test_web_card_contract_and_rendering():
    from tests.node_ts import run_node_test
    result = run_node_test("components/settings/second-copy-section.test.mjs")
    assert result.returncode == 0, result.stdout + result.stderr


def test_setup_docs_and_settings_mount():
    from tests.node_ts import FRONTEND
    assert "<SecondCopySection />" in (FRONTEND / "app/settings/page.tsx").read_text()
    assert '"second-copy"' in (FRONTEND / "lib/settings-tabs.ts").read_text()
