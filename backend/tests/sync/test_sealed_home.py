"""Home seals every peer sync route. A failed seal is a bare 404, the same shape as sync off."""

import asyncio
import base64
import json
import logging
import time
from types import SimpleNamespace
from typing import Annotated

import httpx
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.datastructures import URL
from starlette.requests import Request

from app.config import settings
from app.db import get_db
from app.main import app
from app.routers import sync as sync_router
from app.services.sync import seal, status
from tests.sync.conftest import _Seal, _send_sealed, raw, sealed
from tests.sync.test_pairing import digest as code_digest
from tests.sync.test_pairing import show
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


def test_round_and_setup_stay_unsealed_and_enroll_is_the_bare_404(client, sync_on, peer):
    """/round and /api/sync-setup are not peer routes: a seal header doesn't change their JSON
    answers. /enroll is sealed with the pairing code's keys, so an unsealed call is the bare 404."""
    round_off = client.post("/api/sync/round", headers={seal.HEADER: "2.1.a.b.c.", "X-Maestro-Sync": peer})
    setup = client.post("/api/sync-setup/enroll", headers={seal.HEADER: "2.1.a.b.c."})
    for response in (round_off, setup):
        assert "x-maestro-seal" not in response.headers
        assert response.headers["content-type"].startswith("application/json")
    assert round_off.status_code == 404 and round_off.json()["detail"] == BARE
    assert setup.status_code == 404 and setup.json()["detail"] == BARE
    enroll = client.post("/api/sync/enroll", headers={"X-Maestro-Sync": peer})
    assert enroll.status_code == 404 and enroll.content == b""
    assert "x-maestro-seal" not in enroll.headers


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


def _stamp_header(stamp: str) -> list[tuple[bytes, bytes]]:
    sample, _wire, _rid = seal.seal_request("k", "GET", "/api/sync/hello", "", b"", "2:x:ab")
    parts = sample.split(".")
    parts[1] = stamp
    value = ".".join(parts).encode("latin-1")
    return [(seal.HEADER.lower().encode("ascii"), value)]


def _http(headers: list[tuple[bytes, bytes]]):
    """One ASGI call. Returns status, body, headers (no date), and any escaped exception."""
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
        "scheme": "http", "path": "/api/sync/hello", "raw_path": b"/api/sync/hello",
        "query_string": b"", "root_path": "", "client": ("127.0.0.1", 9),
        "server": ("testserver", 80), "app": app,
        "headers": [(b"host", b"testserver"), *headers],
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    raised = None
    try:
        asyncio.run(app(scope, receive, send))
    except Exception as exc:
        raised = exc
    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"") for message in sent if message["type"] == "http.response.body")
    kept = tuple((name.lower(), value) for name, value in start.get("headers", [])
                 if name.lower() != b"date")
    return start["status"], body, kept, raised


def _parser_headers(case: str, monkeypatch):
    if case == "superscript":
        headers = _stamp_header("²")
        assert b"\xb2" in headers[0][1]
        return headers
    if case == "digits-4300":
        return _stamp_header("9" * 4300)
    if case == "digits-4301":
        return _stamp_header("9" * 4301)

    def boom(*_args, **_kwargs):
        raise RuntimeError("SENTINEL-PARSE")

    if case == "open_request":
        key = status.read_key()
        header, _wire, _rid = seal.seal_request(key, "GET", "/api/sync/hello", "", b"", "2:x:ab")
        monkeypatch.setattr(seal, "open_request", boom)
        return [(seal.HEADER.lower().encode("ascii"), header.encode("ascii")),
                (b"x-maestro-sync", b"2:x:ab")]
    monkeypatch.setattr(seal, "check_header", boom)
    return [(seal.HEADER.lower().encode("ascii"), b"2.not-a-seal")]


@pytest.mark.parametrize("case", [
    "superscript", "digits-4300", "digits-4301", "check_header", "open_request",
])
def test_a_seal_parser_failure_is_the_same_bare_404_as_sync_off(
        client, sync_on, monkeypatch, tmp_path, caplog, case):
    caplog.set_level(logging.DEBUG)
    headers = _parser_headers(case, monkeypatch)
    on = _http(headers)
    monkeypatch.setattr(settings, "sync_key_file", tmp_path / "absent-key")
    off = _http(headers)
    assert on[3] is None
    assert on[:3] == off[:3]
    assert on[0] == 404 and on[1] == b""
    assert b"SENTINEL-PARSE" not in on[1]
    assert "Traceback" not in caplog.text and "SENTINEL-PARSE" not in caplog.text
    assert "²" not in caplog.text and "9" * 40 not in caplog.text


def test_a_root_path_cannot_send_a_peer_route_down_the_plain_path(
        client, sync_on, monkeypatch):
    """Sealing follows the route template. A root_path that shows up on request.url.path
    must still be a bare 404 with the opened-check in _require_sync gone."""
    real = Request.url.fget

    def prefixed(self):
        found = real(self)
        root = self.scope.get("root_path") or ""
        if root and not found.path.startswith(root + "/"):
            return URL(f"{found.scheme}://{found.netloc}{root}{found.path}")
        return found

    monkeypatch.setattr(Request, "url", property(prefixed))

    def opened_check_removed(request: Request, db: Annotated[Session, Depends(get_db)]):
        return sync_router.PeerInfo("remote-1")

    app.dependency_overrides[sync_router._require_sync] = opened_check_removed
    try:
        prefixed_client = TestClient(app, root_path="/x")
        response = prefixed_client.get("/api/sync/hello")
        off = raw(client, "GET", "/api/sync/hello")
    finally:
        app.dependency_overrides.pop(sync_router._require_sync, None)
    assert response.status_code == 404 and response.content == b""
    assert _shape(response) == _shape(off)
    assert response.content != b'{"detail":"Not Found"}'


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
    # The frozen clock is years before this process. Pull the start back so
    # the 404 is the skew window, not a stamp from before startup.
    monkeypatch.setattr(sync_router, "_STARTED_AT", moment - seal.SKEW_SECONDS - 1)
    header, wire, _rid = seal.seal_request(
        status.read_key(), "GET", "/api/sync/hello", "", b"", peer, now=moment - skew)
    response = _send(client, "GET", "/api/sync/hello", header, peer, wire)
    assert response.status_code == 404 and response.content == b""


def _opened_hello(response, key, rid):
    assert response.status_code == 200
    plain = seal.open_response(key, rid, 200, response.headers[seal.HEADER], response.content)
    assert json.loads(plain)["protocol"] == status.SYNC_PROTOCOL


def test_a_peer_seal_earlier_than_the_process_start_is_a_bare_404(client, sync_on, peer, monkeypatch):
    """Home compares the stamp to this process's start in whole seconds.

    A start half a second into the stamp's second still accepts that stamp.
    A stamp from the previous second is a bare 404, and that refusal does not
    register the rid: the same bytes succeed once the start moves back.
    """
    key = status.read_key()
    header, wire, rid = seal.seal_request(key, "GET", "/api/sync/hello", "", b"", peer)
    stamp = int(header.split(".")[1])
    early_header, early_wire, early_rid = seal.seal_request(
        key, "GET", "/api/sync/hello", "", b"", peer, now=float(stamp - 1))
    monkeypatch.setattr(sync_router, "_STARTED_AT", stamp + 0.5, raising=False)
    _opened_hello(_send(client, "GET", "/api/sync/hello", header, peer, wire), key, rid)
    refused = _send(client, "GET", "/api/sync/hello", early_header, peer, early_wire)
    assert refused.status_code == 404 and refused.content == b""
    assert "x-maestro-seal" not in refused.headers
    monkeypatch.setattr(sync_router, "_STARTED_AT", float(stamp - 1))
    _opened_hello(
        _send(client, "GET", "/api/sync/hello", early_header, peer, early_wire), key, early_rid)


def test_an_enroll_seal_earlier_than_the_process_start_is_a_bare_404(
        client, sync_on, monkeypatch):
    """The previous second is a bare 404 and does not register the rid.

    A start half a second into the stamp's second still accepts that stamp.
    """
    secret = code_digest(show(client))
    header, wire, rid = seal.seal_request(
        secret, "POST", "/api/sync/enroll", "", b"", "peer-2", label=seal.ENROLL_TO_HOME)
    stamp = int(header.split(".")[1])
    monkeypatch.setattr(sync_router, "_STARTED_AT", stamp + 0.5, raising=False)
    opened = _send(client, "POST", "/api/sync/enroll", header, "peer-2", wire)
    assert opened.status_code == 200
    plain = seal.open_response(
        secret, rid, 200, opened.headers[seal.HEADER], opened.content,
        label=seal.ENROLL_TO_REMOTE)
    assert json.loads(plain)["key"] == status.read_key()

    secret = code_digest(show(client))
    early, early_wire, early_rid = seal.seal_request(
        secret, "POST", "/api/sync/enroll", "", b"", "peer-2", label=seal.ENROLL_TO_HOME,
        now=time.time() - 1)
    early_stamp = int(early.split(".")[1])
    monkeypatch.setattr(sync_router, "_STARTED_AT", early_stamp + 1.5, raising=False)
    refused = _send(client, "POST", "/api/sync/enroll", early, "peer-2", early_wire)
    assert refused.status_code == 404 and refused.content == b""
    assert "x-maestro-seal" not in refused.headers
    assert client.get("/api/settings/second-copy").json()["open_until"] is not None
    monkeypatch.setattr(sync_router, "_STARTED_AT", float(early_stamp))
    retried = _send(client, "POST", "/api/sync/enroll", early, "peer-2", early_wire)
    assert retried.status_code == 200
    plain = seal.open_response(
        secret, early_rid, 200, retried.headers[seal.HEADER], retried.content,
        label=seal.ENROLL_TO_REMOTE)
    assert json.loads(plain)["key"] == status.read_key()


def test_a_seal_at_the_window_edge_is_accepted(client, sync_on, peer, monkeypatch):
    moment = 1_700_000_000.0
    monkeypatch.setattr(seal.time, "time", lambda: moment)
    # Same frozen clock. The edge stamp equals this start, so it is not earlier.
    monkeypatch.setattr(sync_router, "_STARTED_AT", moment - seal.SKEW_SECONDS)
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


def test_an_origin_on_a_sealed_peer_route_is_a_bare_404(client, sync_on, peer, monkeypatch, tmp_path):
    """A browser cannot seal. Origin on a peer route is the same empty 404 as sync off, even
    when the seal would have opened. Setup keeps the 403. Enroll is that same bare 404."""
    setup = client.post("/api/sync-setup/enroll", headers={"Origin": ALLOWED_ORIGIN})
    enroll = client.post("/api/sync/enroll", headers={"Origin": ALLOWED_ORIGIN})
    assert setup.status_code == 403
    assert setup.json()["detail"] == "Browser requests can't use this."
    assert enroll.status_code == 404 and enroll.content == b""
    key = status.read_key()
    header, wire, _rid = seal.seal_request(key, "GET", "/api/sync/hello", "", b"", peer)
    headers = {seal.HEADER: header, "X-Maestro-Sync": peer, "Origin": ALLOWED_ORIGIN,
               "Authorization": f"Bearer {BAD_KEY}"}
    on = raw(client, "GET", "/api/sync/hello", content=wire, headers=headers)
    monkeypatch.setattr(settings, "sync_key_file", tmp_path / "absent-key")
    off = raw(client, "GET", "/api/sync/hello", content=wire, headers=headers)
    assert _shape(on) == _shape(off)
    assert on.status_code == 404 and on.content == b""
    assert b"Browser" not in on.content and BAD_KEY.encode() not in on.content


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


def test_the_refusal_log_opens_again_at_exactly_sixty_seconds(client, sync_on, caplog, monkeypatch):
    """Exactly 60 s logs again; 59 s stays quiet. A ``<=`` comparison would swallow the boundary."""
    caplog.set_level(logging.DEBUG)
    clock = {"now": 0.0}
    monkeypatch.setattr(sync_router, "time", SimpleNamespace(monotonic=lambda: clock["now"]))
    sync_router._seal_seen.clear()

    def refuse():
        raw(client, "GET", "/api/sync/hello", headers={
            seal.HEADER: "x", "X-Forwarded-For": "192.0.2.10"})

    refuse()
    clock["now"] = 59.0
    refuse()
    assert caplog.text.count(REFUSED) == 1
    clock["now"] = 60.0
    refuse()
    assert caplog.text.count(REFUSED) == 2
    assert "192.0.2.10" not in caplog.text


def _flood(forwarded_for):
    async def once():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
            for forwarded in forwarded_for:
                await http.get("/api/sync/hello", headers={
                    seal.HEADER: "x", "X-Forwarded-For": forwarded})

    asyncio.run(once())


def test_refusal_logging_keys_the_last_forwarded_hop(client, sync_on, caplog, monkeypatch):
    """The trusted proxy appends the real hop. Spoofed first entries must not each log."""
    caplog.set_level(logging.DEBUG)
    clock = {"now": 8_000.0}
    monkeypatch.setattr(sync_router, "time", SimpleNamespace(monotonic=lambda: clock["now"]))
    sync_router._seal_seen.clear()
    try:
        _flood(f"10.{i}.0.1, 203.0.113.9" for i in range(3000))
        assert caplog.text.count(REFUSED) == 1
        assert len(sync_router._seal_seen) <= 1024
        assert list(sync_router._seal_seen) == ["203.0.113.9"]
        assert "10.0.0.1" not in caplog.text and "203.0.113.9" not in caplog.text
    finally:
        sync_router._seal_seen.clear()


def test_the_refusal_log_keeps_at_most_1024_sources(client, sync_on, monkeypatch):
    clock = {"now": 9_000.0}
    monkeypatch.setattr(sync_router, "time", SimpleNamespace(monotonic=lambda: clock["now"]))
    sync_router._seal_seen.clear()
    try:
        _flood(f"198.51.100.1, hop-{i}" for i in range(1025))
        assert len(sync_router._seal_seen) == 1024
        assert "hop-0" not in sync_router._seal_seen
        assert "hop-1024" in sync_router._seal_seen
    finally:
        sync_router._seal_seen.clear()


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
