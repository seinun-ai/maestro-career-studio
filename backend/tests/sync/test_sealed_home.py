"""Home seals every peer sync route. A failed seal is a bare 404, the same shape as sync off."""

import asyncio
import base64
import json
import logging
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_db
from app.main import app
from app.routers import sync as sync_router
from app.services.sync import seal, status
from tests.sync.conftest import _Seal, _send_sealed, raw, sealed
from tests.sync.test_jobs_bundle import SENTINEL

BARE = "Not Found"
REFUSED = "A sync request was refused."
VERSION = "Update Maestro on both machines to the same version."
TOO_LARGE = "That request is too large."
TIMEOUT = "The request took too long to arrive."
FAILED = "Maestro couldn't finish that sync request."
ALLOWED_ORIGIN = "http://localhost:3000"
BAD_KEY = "SENTINEL-WRONG-KEY-9917"
BODIES = {
    "/api/sync/jobs": {"bundles": [], "tombstones": []},
    "/api/sync/ownership": {"job_ids": []},
    "/api/sync/requests": {"requests": []},
    "/api/sync/request-results": {"results": []},
    "/api/sync/handover/commit": {"job_ids": []},
    "/api/sync/handover/return": {"bundles": []},
    "/api/sync/runs": {"runs": []},
}


def _peer_routes():
    found = []
    for route in sync_router.router.routes:
        if route.path in ("/api/sync/round", "/api/sync/enroll"):
            continue
        if not route.path.startswith("/api/sync/"):
            continue
        for method in sorted(set(route.methods) - {"HEAD"}):
            found.append((method, route.path))
    return found


def _b64(raw_bytes):
    return base64.urlsafe_b64encode(raw_bytes).rstrip(b"=").decode("ascii")


def _unb64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _bad_mac(header):
    """A header that still parses, whose mac does not match. The rid stays put."""
    parts = header.split(".")
    mac = bytearray(_unb64(parts[4]))
    mac[0] ^= 1
    parts[4] = _b64(bytes(mac))
    return ".".join(parts)


def _shape(response):
    return (response.status_code, response.content, response.headers.get("x-maestro-seal"),
            response.headers.get("www-authenticate"), response.headers.get("content-type"))


@pytest.fixture
def client(db_session):
    def override():
        try:
            yield db_session
        except Exception:
            db_session.rollback()
            raise

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def peer(db_session, sync_on):
    revision = status.schema_revision(db_session)
    home = status.machine_id(db_session)
    db_session.commit()
    remote = "remote-1"
    assert remote != home
    return f"{status.SYNC_PROTOCOL}:{revision}:{remote}"


def _send(client, method, path, header, peer, body=b""):
    return raw(client, method, path, content=body, headers={
        seal.HEADER: header, "X-Maestro-Sync": peer})


# ---------------------------------------------------------------- what stays unsealed


def test_round_enroll_and_setup_stay_unsealed(client, sync_on, peer):
    """These three are not peer routes. A seal header does not change their JSON answers."""
    round_off = client.post("/api/sync/round", headers={seal.HEADER: "2.1.a.b.c.", "X-Maestro-Sync": peer})
    enroll = client.post("/api/sync/enroll", headers={"X-Maestro-Sync": peer})
    setup = client.post("/api/sync-setup/enroll", headers={seal.HEADER: "2.1.a.b.c."})
    for response in (round_off, enroll, setup):
        assert "x-maestro-seal" not in response.headers
        assert response.headers["content-type"].startswith("application/json")
    assert round_off.status_code == 404 and round_off.json()["detail"] == BARE
    assert setup.status_code == 404 and setup.json()["detail"] == BARE


def test_the_success_table_is_every_peer_route():
    covered = {(method, path) for method, path, _body in _success_cases()}
    assert covered == set(_peer_routes())


def _success_cases():
    cases = []
    for method, path in _peer_routes():
        cases.append((method, path, None if method == "GET" else BODIES[path]))
    return cases


# -------------------------------------------------------------------- bare 404


@pytest.mark.parametrize(("method", "path"), _peer_routes())
def test_an_unsealed_peer_route_is_a_bare_404(client, sync_on, method, path):
    response = raw(client, method, path)
    assert response.status_code == 404
    assert response.content == b""
    assert "x-maestro-seal" not in response.headers
    assert "www-authenticate" not in response.headers


@pytest.mark.parametrize(("method", "path"), _peer_routes())
def test_a_wrong_key_is_a_bare_404(client, sync_on, peer, method, path):
    body = b"" if method == "GET" else json.dumps(BODIES[path]).encode()
    header, wire, _rid = seal.seal_request(BAD_KEY, method, path, "", body, peer)
    response = _send(client, method, path, header, peer, wire)
    assert response.status_code == 404 and response.content == b""
    assert BAD_KEY.encode() not in response.content
    assert "x-maestro-seal" not in response.headers


@pytest.mark.parametrize("header", [None, f"Bearer {BAD_KEY}", BAD_KEY, "Bearer ", "Basic abc"])
def test_a_bearer_only_request_is_a_bare_404(client, sync_on, peer, header):
    headers = {"X-Maestro-Sync": peer}
    if header is not None:
        headers["Authorization"] = header
    body = {"bundles": [{"note": SENTINEL}], "tombstones": []}
    response = raw(client, "POST", "/api/sync/jobs", headers=headers, json=body)
    assert response.status_code == 404 and response.content == b""
    assert BAD_KEY not in response.text and SENTINEL not in response.text
    assert (status.read_key() or "") not in response.text
    assert "www-authenticate" not in response.headers


def test_a_bad_seal_matches_sync_being_off(client, sync_on, monkeypatch, tmp_path):
    bad = raw(client, "GET", "/api/sync/hello", headers={seal.HEADER: "2.nope"})
    monkeypatch.setattr(settings, "sync_key_file", tmp_path / "absent-key")
    off = raw(client, "GET", "/api/sync/hello", headers={
        "Authorization": f"Bearer {BAD_KEY}", seal.HEADER: "2.nope"})
    assert _shape(bad) == _shape(off)
    assert bad.status_code == 404 and bad.content == b""


def test_a_replayed_request_is_a_bare_404(client, sync_on, peer):
    header, wire, _rid = seal.seal_request(status.read_key(), "GET", "/api/sync/hello", "", b"", peer)
    first = _send(client, "GET", "/api/sync/hello", header, peer, wire)
    again = _send(client, "GET", "/api/sync/hello", header, peer, wire)
    assert first.status_code == 200 and seal.HEADER.lower() in first.headers
    assert again.status_code == 404 and again.content == b""
    assert "x-maestro-seal" not in again.headers


def test_a_bad_mac_does_not_burn_the_request_id(client, sync_on, peer):
    """Registering the rid before the mac matches would make the real request a replay."""
    key = status.read_key()
    header, wire, _rid = seal.seal_request(key, "GET", "/api/sync/hello", "", b"", peer)
    rejected = _send(client, "GET", "/api/sync/hello", _bad_mac(header), peer, wire)
    assert rejected.status_code == 404 and rejected.content == b""
    opened = _send(client, "GET", "/api/sync/hello", header, peer, wire)
    assert opened.status_code == 200
    assert seal.HEADER.lower() in opened.headers


def test_a_bad_mac_is_refused_before_the_body_is_read(db_session, sync_on, peer):
    key = status.read_key()
    header, _wire, _rid = seal.seal_request(key, "POST", "/api/sync/jobs", "", b"{}", peer)
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
        "scheme": "http", "path": "/api/sync/jobs", "raw_path": b"/api/sync/jobs",
        "query_string": b"", "root_path": "", "client": ("127.0.0.1", 9),
        "server": ("testserver", 80), "app": app,
        "headers": [
            (b"host", b"testserver"),
            (seal.HEADER.lower().encode(), _bad_mac(header).encode()),
            (b"x-maestro-sync", peer.encode()),
            (b"content-type", b"application/octet-stream"),
        ],
    }
    called = []

    async def receive():
        called.append("body")
        await asyncio.sleep(30)
        return {"type": "http.request", "body": b"x" * 1000, "more_body": False}

    sent = []

    async def send(message):
        sent.append(message)

    def override():
        yield db_session

    app.dependency_overrides[get_db] = override
    try:
        started = time.monotonic()
        asyncio.run(asyncio.wait_for(app(scope, receive, send), timeout=1))
        elapsed = time.monotonic() - started
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert elapsed < 1
    assert called == []
    assert sent[0]["status"] == 404
    body = b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")
    assert body == b""


def test_a_good_mac_reads_the_body_and_a_stall_is_a_sealed_408(client, sync_on, peer, monkeypatch):
    called = []

    async def stalled(self):
        called.append("body")
        yield b"{"
        await asyncio.sleep(2)

    monkeypatch.setattr("starlette.requests.Request.stream", stalled)
    monkeypatch.setattr(sync_router, "_CHUNK_TIMEOUT", 0.05)
    key = status.read_key()
    header, wire, rid = seal.seal_request(key, "POST", "/api/sync/ownership", "", b'{"job_ids":[]}', peer)
    started = time.monotonic()
    response = _send(client, "POST", "/api/sync/ownership", header, peer, wire)
    assert time.monotonic() - started < 1
    assert called == ["body"]
    assert response.status_code == 408
    assert b"too long" not in response.content
    plain = seal.open_response(key, rid, 408, response.headers[seal.HEADER], response.content)
    assert json.loads(plain) == {"detail": TIMEOUT}
    assert not sync_router._LOCK.locked()


# ----------------------------------------------------------------------- the seal binds


@pytest.mark.parametrize("skew", [301, -301])
def test_a_seal_one_second_outside_the_window_is_a_bare_404(client, sync_on, peer, monkeypatch, skew):
    moment = 1_700_000_000.0
    monkeypatch.setattr(seal.time, "time", lambda: moment)
    header, wire, _rid = seal.seal_request(
        status.read_key(), "GET", "/api/sync/hello", "", b"", peer, now=moment - skew)
    response = _send(client, "GET", "/api/sync/hello", header, peer, wire)
    assert response.status_code == 404 and response.content == b""


def test_a_seal_at_the_window_edge_is_accepted(client, sync_on, peer, monkeypatch):
    moment = 1_700_000_000.0
    monkeypatch.setattr(seal.time, "time", lambda: moment)
    code, body = sealed(client, "GET", "/api/sync/hello", peer=peer, key=status.read_key())
    # sealed() stamps `now` itself; rebuild at the edge so 300 is in and 301 is out.
    header, wire, rid = seal.seal_request(
        status.read_key(), "GET", "/api/sync/hello", "", b"", peer, now=moment - seal.SKEW_SECONDS)
    response = _send(client, "GET", "/api/sync/hello", header, peer, wire)
    assert response.status_code == 200
    plain = seal.open_response(status.read_key(), rid, 200, response.headers[seal.HEADER],
                               response.content)
    assert json.loads(plain)["protocol"] == status.SYNC_PROTOCOL
    assert code == 200 and body["protocol"] == status.SYNC_PROTOCOL


def test_the_wrong_direction_label_is_a_bare_404(client, sync_on, peer):
    header, wire, _rid = seal.seal_request(
        status.read_key(), "GET", "/api/sync/hello", "", b"", peer, label=seal.TO_REMOTE)
    response = _send(client, "GET", "/api/sync/hello", header, peer, wire)
    assert response.status_code == 404 and response.content == b""


@pytest.mark.parametrize(("method", "path", "query", "sent_path", "sent_query"), [
    ("PUT", "/api/sync/hello", "", "/api/sync/hello", ""),
    ("GET", "/api/sync/profile", "", "/api/sync/hello", ""),
    ("GET", "/api/sync/profile", "a=1&b=2", "/api/sync/profile", "a=1&b=9"),
])
def test_a_tampered_aad_component_is_a_bare_404(
        client, sync_on, peer, method, path, query, sent_path, sent_query):
    header, wire, _rid = seal.seal_request(status.read_key(), method, path, query, b"", peer)
    url = f"{sent_path}?{sent_query}" if sent_query else sent_path
    response = raw(client, "GET", url, content=wire, headers={
        seal.HEADER: header, "X-Maestro-Sync": peer})
    assert response.status_code == 404 and response.content == b""


def test_query_order_does_not_matter_and_the_value_does(client, sync_on, peer):
    key = status.read_key()
    header, wire, rid = seal.seal_request(key, "GET", "/api/sync/profile", "b=2&a=1", b"", peer)
    response = raw(client, "GET", "/api/sync/profile?a=1&b=2", content=wire, headers={
        seal.HEADER: header, "X-Maestro-Sync": peer})
    assert response.status_code == 200
    plain = seal.open_response(key, rid, 200, response.headers[seal.HEADER], response.content)
    assert "unchanged" in json.loads(plain) or "rows" in json.loads(plain)


def test_a_swapped_peer_header_is_a_bare_404(client, sync_on, peer):
    header, wire, _rid = seal.seal_request(status.read_key(), "GET", "/api/sync/hello", "", b"", peer)
    swapped = peer.rsplit(":", 1)[0] + ":other-1"
    response = _send(client, "GET", "/api/sync/hello", header, swapped, wire)
    assert response.status_code == 404 and response.content == b""


# ----------------------------------------------------------------------- responses


def test_origin_is_refused_before_the_seal(client, sync_on, peer):
    """A browser Origin is a 403 even when the seal would have failed, and the 403 is in the clear."""
    response = raw(client, "GET", "/api/sync/hello", headers={
        "Origin": ALLOWED_ORIGIN, "X-Maestro-Sync": "not-a-header",
        "Authorization": f"Bearer {BAD_KEY}", seal.HEADER: "not-a-seal"})
    assert response.status_code == 403
    assert "x-maestro-seal" not in response.headers
    assert BAD_KEY not in response.text
    assert response.json()["detail"] == "Browser requests can't use this."


def test_an_authorization_header_is_ignored(client, sync_on, peer):
    response, rid, secret = _send_sealed(client, _Seal(
        "GET", "/api/sync/hello", peer=peer, headers={"Authorization": f"Bearer {BAD_KEY}"}))
    opened = seal.open_response(
        secret, rid, response.status_code, response.headers[seal.HEADER], response.content)
    body = json.loads(opened)
    assert response.status_code == 200 and body["protocol"] == status.SYNC_PROTOCOL
    assert BAD_KEY not in json.dumps(body)


def test_a_version_mismatch_is_sealed(client, sync_on, peer):
    protocol, revision, remote = peer.split(":")
    bad = f"{int(protocol) + 1}:{revision}:{remote}"
    code, body = sealed(client, "GET", "/api/sync/hello", peer=bad)
    header, wire, rid = seal.seal_request(status.read_key(), "GET", "/api/sync/hello", "", b"", bad)
    response = _send(client, "GET", "/api/sync/hello", header, bad, wire)
    assert response.status_code == 409
    assert b"Update Maestro" not in response.content
    plain = seal.open_response(status.read_key(), rid, 409, response.headers[seal.HEADER],
                               response.content)
    assert json.loads(plain) == {"detail": VERSION, "reason": "version"}
    assert code == 409 and body["reason"] == "version"


def test_the_seal_is_checked_before_the_version(client, sync_on):
    """A bad seal with a nonsense version is a bare 404, not a 409 about the version."""
    response = raw(client, "GET", "/api/sync/hello", headers={
        "Authorization": f"Bearer {BAD_KEY}", "X-Maestro-Sync": "bad"})
    assert response.status_code == 404 and response.content == b""
    assert b"version" not in response.content.lower() and b"Update" not in response.content


def test_a_refusal_and_a_crash_are_sealed(client, sync_on, peer, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError(f"/private/{SENTINEL}")

    monkeypatch.setattr(sync_router.status, "machine_id", boom)
    key = status.read_key()
    header, wire, rid = seal.seal_request(key, "GET", "/api/sync/hello", "", b"", peer)
    response = _send(client, "GET", "/api/sync/hello", header, peer, wire)
    assert response.status_code == 500
    assert SENTINEL.encode() not in response.content
    plain = seal.open_response(key, rid, 500, response.headers[seal.HEADER], response.content)
    assert json.loads(plain) == {"detail": FAILED}
    assert not sync_router._LOCK.locked()


def test_a_body_over_the_cap_is_a_sealed_413(client, sync_on, peer, monkeypatch):
    monkeypatch.setattr(sync_router, "MAX_BODY_BYTES", 40)
    key = status.read_key()
    payload = json.dumps({"job_ids": [SENTINEL * 5]}).encode()
    header, wire, rid = seal.seal_request(key, "POST", "/api/sync/ownership", "", payload, peer)
    assert len(wire) > 40
    response = _send(client, "POST", "/api/sync/ownership", header, peer, wire)
    assert response.status_code == 413
    assert SENTINEL.encode() not in response.content
    assert b"too large" not in response.content
    plain = seal.open_response(key, rid, 413, response.headers[seal.HEADER], response.content)
    assert json.loads(plain) == {"detail": TOO_LARGE}


def test_the_cap_is_the_wire_body(client, sync_on, peer, monkeypatch):
    """The cap counts ciphertext. A limit that fits the plaintext but not the wire is a 413."""
    key = status.read_key()
    payload = json.dumps({"job_ids": []}).encode()
    header, wire, rid = seal.seal_request(key, "POST", "/api/sync/ownership", "", payload, peer)
    monkeypatch.setattr(sync_router, "MAX_BODY_BYTES", len(wire) - 1)
    refused = _send(client, "POST", "/api/sync/ownership", header, peer, wire)
    assert refused.status_code == 413
    monkeypatch.setattr(sync_router, "MAX_BODY_BYTES", len(wire))
    header, wire, rid = seal.seal_request(key, "POST", "/api/sync/ownership", "", payload, peer)
    accepted = _send(client, "POST", "/api/sync/ownership", header, peer, wire)
    assert accepted.status_code == 200
    plain = seal.open_response(key, rid, 200, accepted.headers[seal.HEADER], accepted.content)
    assert json.loads(plain) == {}


@pytest.mark.parametrize(("method", "path", "body"), _success_cases())
def test_a_sealed_request_round_trips(client, sync_on, peer, method, path, body):
    code, opened = sealed(client, method, path, json=body, peer=peer)
    assert code == 200
    assert opened is not None


# ---------------------------------------------------------------------------- logs


def test_seal_failures_are_logged_once_a_minute_per_source(client, sync_on, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    clock = {"now": 1_000.0}
    monkeypatch.setattr(sync_router, "time", SimpleNamespace(monotonic=lambda: clock["now"]),
                        raising=False)
    seen = getattr(sync_router, "_seal_seen", None)
    if seen is not None:
        seen.clear()

    def refuse(source):
        raw(client, "GET", "/api/sync/hello", headers={
            seal.HEADER: status.read_key(), "X-Forwarded-For": source})

    refuse("10.0.0.1")
    refuse("10.0.0.1")
    refuse("10.0.0.2")
    assert caplog.text.count(REFUSED) == 2
    clock["now"] = 1_030.0
    refuse("10.0.0.1")
    assert caplog.text.count(REFUSED) == 2
    clock["now"] = 1_061.0
    refuse("10.0.0.1")
    assert caplog.text.count(REFUSED) == 3
    assert "10.0.0.1" not in caplog.text and "10.0.0.2" not in caplog.text
    assert status.read_key() not in caplog.text


def test_logs_omit_the_key_the_seal_and_a_bundle_value(client, sync_on, peer, caplog):
    caplog.set_level(logging.DEBUG)
    key = status.read_key()
    sealed(client, "POST", "/api/sync/ownership", json={"job_ids": [SENTINEL]}, peer=peer)
    raw(client, "POST", "/api/sync/jobs", headers={
        seal.HEADER: key, "X-Forwarded-For": SENTINEL, "X-Maestro-Sync": peer,
    }, json={"bundles": [{"title": SENTINEL}]})
    text = caplog.text
    assert REFUSED in text
    assert key not in text and SENTINEL not in text and peer not in text
