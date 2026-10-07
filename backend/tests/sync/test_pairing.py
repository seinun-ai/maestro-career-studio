"""Pairing with a one-time code. The code is shown once; enroll speaks seals."""

import asyncio
import hashlib
import json
import logging
import re
import threading
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_db
from app.main import app
from app.models.setting import Setting
from app.routers import sync as sync_router
from app.services import http_client
from app.services.sync import pairing, seal, status
from app.services.sync import round as sync_round
from tests.sync import test_home_endpoints as home_tests

# Reuse the existing isolated channel fixtures without importing their test cases.
ALLOWED_ORIGIN = home_tests.ALLOWED_ORIGIN
auth, client, home_id = home_tests.auth, home_tests.client, home_tests.home_id
recv, remote_id, sync_off = home_tests.recv, home_tests.remote_id, home_tests.sync_off

WINDOW = "/api/settings/second-copy"
ENROLL = "/api/sync/enroll"
SETUP = "/api/sync-setup/enroll"
CLOSED = "Pairing didn't work. Show a pairing code on your laptop and try again."
HOME_ONLY = "Show a pairing code on your laptop, not on the always-on copy."
TUNNEL = "The laptop's address must be this machine's own tunnel or an https:// address."
UNVERIFIED = "The laptop's answer couldn't be verified."
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
KEY = "SENTINEL-PAIRING-KEY-DO-NOT-PRINT"
CODE_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{4}(?:-[0-9A-HJKMNP-TV-Z]{4}){3}$")
TYPED = "o123 4567 89ab cdef"
NORMAL = "0123456789ABCDEF"
SECRET = hashlib.sha256(NORMAL.encode()).hexdigest()
PEER = "peer-2"
MOMENT = 1_700_000_000


def put_setting(db, name, value):
    row = db.get(Setting, name)
    if row is None:
        db.add(Setting(key=name, value=value))
    else:
        row.value = value
    db.commit()


def digest(code):
    """The enroll secret, computed here so a wrong server normalization cannot hide."""
    cleaned = []
    for char in code.upper():
        if char in " -":
            continue
        cleaned.append({"O": "0", "I": "1", "L": "1"}.get(char, char))
    return hashlib.sha256("".join(cleaned).encode()).hexdigest()


def show(client):
    response = client.post(WINDOW)
    assert response.status_code == 200, response.status_code
    code = response.json()["code"]
    assert CODE_RE.fullmatch(code)
    return code


def values(db):
    db.expire_all()
    return [row.value for row in db.query(Setting).all()]


def bare_of(response):
    headers = tuple(sorted(
        (key.lower(), value) for key, value in response.headers.items()
        if key.lower() not in {"date", "server"}))
    return response.status_code, bytes(response.content), headers


def off_bare(client, monkeypatch, method, path, **kwargs):
    """A sync-off answer for the same method and headers. Callers compare, not hard-code."""
    remembered = settings.sync_key_file
    monkeypatch.setattr(settings, "sync_key_file", remembered.parent / "absent-sync-key")
    try:
        return bare_of(client.request(method, path, **kwargs))
    finally:
        monkeypatch.setattr(settings, "sync_key_file", remembered)


def setting_keys(db):
    db.expire_all()
    return {row.key for row in db.query(Setting)}


def sealed_enroll(client, secret, *, body=b"", peer=PEER, query="", now=None, label=None,
                  header=None, wire=None):
    label = seal.ENROLL_TO_HOME if label is None else label
    if header is None:
        header, wire, rid = seal.seal_request(
            secret, "POST", ENROLL, query, body, peer, label=label, now=now)
    else:
        rid = header.split(".")[2]
    url = f"{ENROLL}?{query}" if query else ENROLL
    response = client.post(url, content=wire, headers={
        seal.HEADER: header, "X-Maestro-Sync": peer})
    return response, rid


def open_enroll(response, secret, rid):
    plain = seal.open_response(
        secret, rid, response.status_code, response.headers[seal.HEADER],
        response.content, label=seal.ENROLL_TO_REMOTE)
    return json.loads(plain)


def flipped(secret):
    header, wire, rid = seal.seal_request(
        secret, "POST", ENROLL, "", b"{}", PEER, label=seal.ENROLL_TO_HOME)
    return header, wire[:-1] + bytes([wire[-1] ^ 1]), rid


def post_parts(client, header, wire):
    return client.post(ENROLL, content=wire, headers={
        seal.HEADER: header, "X-Maestro-Sync": PEER})


def window_open(client):
    return client.get(WINDOW).json()["open_until"] is not None


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
    assert response.json()["detail"] == HOME_ONLY
    assert not status.key_path().exists()


def test_unlisted_browser_cannot_opt_in(client, sync_off):
    assert client.post(WINDOW, headers={"Origin": "https://untrusted.example"}).status_code == 403
    assert not status.key_path().exists()


def test_a_shown_code_is_crockford_and_only_its_digest_is_stored(client, sync_on, db_session):
    first, second = show(client), show(client)
    assert first != second
    secret = digest(second)
    stored = values(db_session)
    assert secret in stored
    assert all(first not in (item or "") and second not in (item or "") for item in stored)
    card = client.get(WINDOW)
    assert "code" not in card.json()
    assert first not in card.text and second not in card.text and secret not in card.text


def test_normalization_maps_confusables_and_rejects_anything_else():
    assert pairing.normalize_code("o123 4567-89ab cdef") == NORMAL
    assert pairing.normalize_code("iL10-OOOO-IIII-LLLL") == "1110000011111111"
    assert pairing.normalize_code("0123-4567-89AB-CDEF") == NORMAL
    assert pairing.normalize_code("0123-4567-89AB-CDEU") is None
    assert pairing.normalize_code("0123-4567-89AB-CDE") is None
    assert pairing.normalize_code("0123-4567-89AB-CDEF-0") is None
    assert pairing.normalize_code("") is None


def test_enroll_origin_is_the_bare_404_before_the_key_or_body(client, sync_on, monkeypatch):
    """A valid enroll seal from an allowed Origin is still the sync-off 404, and the key stays."""
    baseline = off_bare(
        client, monkeypatch, "GET", "/api/sync/hello", headers={"Origin": ALLOWED_ORIGIN})
    secret = digest(show(client))
    header, wire, _rid = seal.seal_request(
        secret, "POST", ENROLL, "", b"", PEER, label=seal.ENROLL_TO_HOME)

    def forbidden(*args, **kwargs):
        raise AssertionError("must refuse before touching the sync key or the body")

    read_key = status.read_key
    monkeypatch.setattr(status, "read_key", forbidden)
    monkeypatch.setattr(Request, "body", forbidden)
    monkeypatch.setattr(Request, "stream", forbidden)
    response = client.post(ENROLL, content=wire, headers={
        seal.HEADER: header, "X-Maestro-Sync": PEER, "Origin": ALLOWED_ORIGIN})
    assert bare_of(response) == baseline
    monkeypatch.setattr(status, "read_key", read_key)
    assert window_open(client)


def test_enroll_without_a_key_matches_sync_off_hello(client, sync_off):
    hello = bare_of(client.get("/api/sync/hello"))
    assert bare_of(client.post(ENROLL, content=b"x")) == hello
    origin = {"Origin": ALLOWED_ORIGIN}
    assert bare_of(client.get("/api/sync/hello", headers=origin)) == bare_of(
        client.post(ENROLL, headers=origin, content=b"x"))


def test_generated_codes_use_every_position_of_the_crockford_alphabet():
    """16 Crockford characters is 80 bits. A short code or a stuck column fails here."""
    codes = [pairing._new_code().replace("-", "") for _ in range(300)]
    assert all(len(code) == 16 and set(code) <= set(ALPHABET) for code in codes)
    assert set("".join(codes)) == set(ALPHABET)
    for index, column in enumerate(zip(*codes)):
        assert len(set(column)) >= 8, index


def test_stop_retires_the_digest(client, sync_on, db_session):
    code = show(client)
    secret = digest(code)
    assert client.delete(WINDOW).json() == {"open_until": None}
    assert secret not in values(db_session)
    response, _rid = sealed_enroll(client, secret)
    assert response.status_code == 404 and response.content == b""


def test_enroll_succeeds_once_on_the_code_keys(client, sync_on, caplog):
    caplog.set_level(logging.DEBUG)
    code = show(client)
    secret = digest(code)
    key = status.read_key()
    response, rid = sealed_enroll(client, secret, peer="2:rev:peer-sentinel", query="n=1")
    assert response.status_code == 200
    assert key.encode() not in response.content and code.encode() not in response.content
    assert open_enroll(response, secret, rid) == {"key": key}
    card = client.get(WINDOW).json()
    assert card["open_until"] is None and card["last_paired_at"] is not None
    assert code not in client.get(WINDOW).text and secret not in client.get(WINDOW).text
    again, _rid = sealed_enroll(client, secret, peer="2:rev:peer-sentinel", query="n=1")
    assert again.status_code == 404 and again.content == b""
    assert sum(r.getMessage() == "A copy fetched the sync key." for r in caplog.records) == 1
    assert code not in caplog.text and key not in caplog.text and secret not in caplog.text


def test_the_sync_label_is_not_the_enroll_label(client, sync_on):
    secret = digest(show(client))
    response, _rid = sealed_enroll(client, secret, label=seal.TO_HOME)
    assert response.status_code == 404 and response.content == b""
    assert window_open(client)


def test_five_minutes_is_accepted_and_one_second_past_is_not(client, sync_on, monkeypatch):
    monkeypatch.setattr(seal.time, "time", lambda: float(MOMENT))
    secret = digest(show(client))
    for skew in (301, -301):
        response, _rid = sealed_enroll(client, secret, now=MOMENT + skew)
        assert response.status_code == 404 and response.content == b""
    assert window_open(client)
    response, rid = sealed_enroll(client, secret, now=MOMENT + 300)
    assert open_enroll(response, secret, rid)["key"] == status.read_key()
    secret = digest(show(client))
    response, rid = sealed_enroll(client, secret, now=MOMENT - 300)
    assert open_enroll(response, secret, rid)["key"] == status.read_key()


def test_a_rid_is_registered_only_after_the_mac_verifies(client, sync_on):
    secret = digest(show(client))
    header, wire, rid = seal.seal_request(
        secret, "POST", ENROLL, "", b"", PEER, label=seal.ENROLL_TO_HOME)
    parts = header.split(".")
    parts[4] = "A" * 22
    refused = post_parts(client, ".".join(parts), wire)
    assert refused.status_code == 404 and refused.content == b""
    response = post_parts(client, header, wire)
    assert open_enroll(response, secret, rid)["key"] == status.read_key()


def test_a_bad_mac_does_not_read_the_body(client, sync_on, monkeypatch):
    secret = digest(show(client))
    called = []

    async def stalled(self):
        called.append("body")
        yield b"x"

    monkeypatch.setattr("starlette.requests.Request.stream", stalled)
    header, wire, _rid = seal.seal_request(
        secret, "POST", ENROLL, "", b"{}", PEER, label=seal.ENROLL_TO_HOME)
    parts = header.split(".")
    parts[4] = "A" * 22
    response = post_parts(client, ".".join(parts), wire)
    assert response.status_code == 404 and called == []


def test_a_failed_open_keeps_the_window_and_a_replay_does_not(client, sync_on):
    secret = digest(show(client))
    header, wire, rid = seal.seal_request(
        secret, "POST", ENROLL, "", b"{}", PEER, label=seal.ENROLL_TO_HOME)
    damaged = wire[:-1] + bytes([wire[-1] ^ 1])
    assert post_parts(client, header, damaged).status_code == 404
    replayed = post_parts(client, header, wire)
    assert replayed.status_code == 404 and replayed.content == b""
    for _ in range(3):
        assert post_parts(client, header, damaged).status_code == 404
    assert window_open(client)
    response, fresh = sealed_enroll(client, secret, body=b"{}")
    assert fresh != rid
    assert open_enroll(response, secret, fresh)["key"] == status.read_key()


def test_wrong_guesses_do_not_retire_the_window(client, sync_on, db_session, monkeypatch):
    baseline = off_bare(client, monkeypatch, "GET", "/api/sync/hello")
    secret = digest(show(client))
    assert "sync.pairing_attempts" not in setting_keys(db_session)
    wrong = digest("ZZZZ-ZZZZ-ZZZZ-ZZZZ")
    for _ in range(100):
        response, _rid = sealed_enroll(client, wrong)
        assert bare_of(response) == baseline
    for _ in range(6):
        header, wire, _rid = flipped(secret)
        assert bare_of(post_parts(client, header, wire)) == baseline
    assert window_open(client)
    assert "sync.pairing_attempts" not in setting_keys(db_session)
    response, rid = sealed_enroll(client, secret)
    assert open_enroll(response, secret, rid)["key"] == status.read_key()


def test_a_new_code_replaces_the_previous_digest(client, sync_on):
    first, second = show(client), show(client)
    refused, _rid = sealed_enroll(client, digest(first))
    assert refused.status_code == 404 and refused.content == b""
    assert window_open(client)
    response, rid = sealed_enroll(client, digest(second))
    assert open_enroll(response, secret := digest(second), rid)["key"] == status.read_key()
    assert digest(first) != secret


def test_a_damaged_window_matches_the_bare_404(client, sync_on, db_session, monkeypatch):
    baseline = off_bare(client, monkeypatch, "GET", "/api/sync/hello")
    secret = digest(show(client))
    put_setting(db_session, "sync.pairing_until", "not-a-time")
    response, _rid = sealed_enroll(client, secret)
    assert bare_of(response) == baseline


def test_an_expired_window_matches_sync_off_and_still_works_once_restored(
        client, sync_on, db_session, monkeypatch):
    baseline = off_bare(client, monkeypatch, "GET", "/api/sync/hello")
    code = show(client)
    secret = digest(code)
    put_setting(db_session, "sync.pairing_until",
                (datetime.now(UTC) - timedelta(seconds=1)).isoformat())
    for _ in range(6):
        response, _rid = sealed_enroll(client, secret)
        assert bare_of(response) == baseline
    put_setting(db_session, "sync.pairing_until",
                (datetime.now(UTC) + timedelta(minutes=10)).isoformat())
    response, rid = sealed_enroll(client, secret)
    assert open_enroll(response, secret, rid)["key"] == status.read_key()


def test_a_closed_window_rejects_the_stand_in_secret(client, sync_on):
    response, _rid = sealed_enroll(client, pairing._STAND_IN)
    assert response.status_code == 404 and response.content == b""
    assert seal.HEADER.lower() not in {name.lower() for name in response.headers}
    assert status.read_key().encode() not in response.content


def _stall_first_enroll_check(monkeypatch):
    """Hold the first enroll mac check. A lock taken before it makes every peer busy."""
    started, release = threading.Event(), threading.Event()
    real = seal.check_header
    gate = {"open": True}
    guard = threading.Lock()

    def slow(*args, **kwargs):
        if kwargs.get("label") == seal.ENROLL_TO_HOME:
            with guard:
                stall = gate["open"]
                gate["open"] = False
            if stall:
                started.set()
                release.wait(8)
        return real(*args, **kwargs)

    monkeypatch.setattr(seal, "check_header", slow)
    return started, release


def _peer_hello(revision):
    key = status.read_key()
    peer = f"{status.SYNC_PROTOCOL}:{revision}:flood-peer"
    header, _wire, rid = seal.seal_request(key, "GET", "/api/sync/hello", "", b"", peer)
    response = TestClient(app).get("/api/sync/hello", headers={
        seal.HEADER: header, "X-Maestro-Sync": peer})
    try:
        plain = sync_round._opened_answer(response, key, rid)
        return sync_round._interpret(response.status_code, plain)
    except sync_round._Stop as stop:
        return stop


def _without_shared_session():
    return app.dependency_overrides.pop(get_db, None)


def _restore_session(saved):
    if saved is not None:
        app.dependency_overrides[get_db] = saved


def test_a_flood_of_bad_enrolls_does_not_busy_a_peer_or_a_round(
        client, sync_on, db_session, monkeypatch):
    revision = status.schema_revision(db_session)
    db_session.rollback()
    started, release = _stall_first_enroll_check(monkeypatch)
    saved = _without_shared_session()
    holder = {}

    def hold():
        holder["response"] = TestClient(app).post(ENROLL, content=b"x")

    thread = threading.Thread(target=hold)
    thread.start()
    assert started.wait(5), "the bad enroll never reached the mac check"
    try:
        flood = [TestClient(app).post(ENROLL, content=b"x") for _ in range(12)]
        opened = _peer_hello(revision)
    finally:
        release.set()
        thread.join(8)
        _restore_session(saved)
    assert not thread.is_alive()
    assert all(response.status_code != 409 and b"busy" not in response.content for response in flood)
    assert isinstance(opened, dict) and opened.get("protocol") == status.SYNC_PROTOCOL
    assert "already running" not in json.dumps(opened)
    assert not sync_router._LOCK.locked()


def test_two_concurrent_correct_enrolls_hand_the_key_over_once(
        client, sync_on, db_session, monkeypatch):
    baseline = off_bare(client, monkeypatch, "GET", "/api/sync/hello")
    secret = digest(show(client))
    key = status.read_key()
    seals = [
        seal.seal_request(secret, "POST", ENROLL, "", b"", PEER, label=seal.ENROLL_TO_HOME)
        for _ in range(2)]
    real = pairing.complete_pairing
    barrier = threading.Barrier(2)

    def gated(db, digest_value):
        barrier.wait(5)
        return real(db, digest_value)

    monkeypatch.setattr(pairing, "complete_pairing", gated)
    db_session.rollback()
    saved = _without_shared_session()
    results = [None, None]

    def post(index):
        header, wire, rid = seals[index]
        results[index] = (TestClient(app).post(ENROLL, content=wire, headers={
            seal.HEADER: header, "X-Maestro-Sync": PEER}), rid)

    threads = [threading.Thread(target=post, args=(index,)) for index in range(2)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
    finally:
        _restore_session(saved)
    assert all(item is not None and not isinstance(item, Exception) for item in results)
    statuses = sorted(item[0].status_code for item in results)
    assert statuses == [200, 404]
    for response, rid in results:
        if response.status_code == 200:
            assert open_enroll(response, secret, rid)["key"] == key
        else:
            assert bare_of(response) == baseline
    db_session.expire_all()
    assert client.get(WINDOW).json()["open_until"] is None
    again, _rid = sealed_enroll(client, secret)
    assert bare_of(again) == baseline


def test_health_answers_while_enroll_here_is_stuck(client, remote_setup, monkeypatch):
    started, release = threading.Event(), threading.Event()
    outcome = {}

    def stuck(request):
        started.set()
        release.wait(10)
        return httpx.Response(404)

    fake_route(monkeypatch, stuck, trust_env=False)

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
            loop = asyncio.get_running_loop()

            def probe():
                if not started.wait(3):
                    outcome["blocked"] = "never"
                    release.set()
                    return
                future = asyncio.run_coroutine_threadsafe(http.get("/health"), loop)
                try:
                    health = future.result(timeout=1)
                except TimeoutError:
                    outcome["blocked"] = "loop"
                    release.set()
                    return
                outcome["health"] = (health.status_code, health.json())
                release.set()

            enroll = asyncio.create_task(http.post(SETUP, json={"code": TYPED}))
            watcher = threading.Thread(target=probe)
            watcher.start()
            await enroll
            watcher.join(5)

    try:
        asyncio.run(scenario())
    finally:
        release.set()
    assert outcome.get("blocked") is None
    assert outcome.get("health") == (200, {"status": "ok"})


@pytest.fixture
def remote_setup(sync_off, monkeypatch):
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")
    return status.key_path()


def fake_route(monkeypatch, handler, *, trust_env):
    calls = []

    def build(**kwargs):
        assert kwargs["trust_env"] is trust_env
        assert kwargs["follow_redirects"] is False
        assert kwargs["verify"] is True
        return httpx.Client(**kwargs, transport=httpx.MockTransport(
            lambda request: (calls.append(request), handler(request))[1]))

    monkeypatch.setattr(http_client, "new_client", build)
    return calls


def seal_answer(request, payload):
    rid = request.headers[seal.HEADER].split(".")[2]
    raw = json.dumps(payload).encode()
    header, wire = seal.seal_response(
        SECRET, rid, 200, raw, label=seal.ENROLL_TO_REMOTE)
    return httpx.Response(200, content=wire, headers={seal.HEADER: header})


def home_accepts(request):
    try:
        ok = seal.check_header(
            SECRET, request.method, request.url.path, request.url.query.decode(),
            request.headers.get(seal.HEADER, ""), request.headers.get("x-maestro-sync", ""),
            replay=None, label=seal.ENROLL_TO_HOME)
        seal.open_request(SECRET, ok, request.content, label=seal.ENROLL_TO_HOME)
    except seal.Broken:
        return httpx.Response(404)
    assert TYPED not in str(request.url)
    assert NORMAL.encode() not in request.content
    return seal_answer(request, {"key": KEY})


def test_remote_fetch_stores_private_key_and_returns_only_ok(
        client, remote_setup, db_session, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    calls = fake_route(monkeypatch, home_accepts, trust_env=False)
    response = client.post(SETUP, json={"code": TYPED})
    assert response.status_code == 200 and response.json() == {"ok": True}
    assert remote_setup.read_text().strip() == KEY
    assert remote_setup.stat().st_mode & 0o777 == 0o600
    assert remote_setup.parent.stat().st_mode & 0o777 == 0o700
    assert len(calls) == 1 and calls[0].url.path == ENROLL
    assert "authorization" not in calls[0].headers
    assert calls[0].headers["x-maestro-sync"].startswith(
        f"{status.SYNC_PROTOCOL}:{status.schema_revision(db_session)}:")
    assert KEY not in response.text + caplog.text
    assert TYPED not in response.text + caplog.text and NORMAL not in caplog.text
    assert client.post(SETUP, json={"code": TYPED}).status_code == 409 and len(calls) == 1


def test_https_enroll_trusts_the_environment_proxy(client, remote_setup, monkeypatch):
    monkeypatch.setattr(settings, "sync_remote_url", "https://outside.example")
    calls = fake_route(monkeypatch, home_accepts, trust_env=True)
    response = client.post(SETUP, json={"code": TYPED})
    assert response.status_code == 200 and response.json() == {"ok": True}
    assert len(calls) == 1 and TYPED not in str(calls[0].url)


@pytest.mark.parametrize("kind", ["regular", "empty", "symlink"])
def test_remote_refuses_any_existing_key_path(client, remote_setup, monkeypatch, kind):
    remote_setup.parent.mkdir(parents=True, exist_ok=True)
    if kind == "symlink":
        remote_setup.symlink_to(remote_setup.parent / "missing")
    else:
        remote_setup.write_text(KEY if kind == "regular" else "")
    calls = fake_route(monkeypatch, lambda request: pytest.fail("must not fetch"), trust_env=False)
    assert client.post(SETUP).status_code == 409 and not calls


def test_remote_write_is_exclusive_even_when_file_appears_during_fetch(
        client, remote_setup, monkeypatch):
    def reply(request):
        remote_setup.parent.mkdir(parents=True, exist_ok=True)
        remote_setup.write_text("existing-key")
        return home_accepts(request)
    fake_route(monkeypatch, reply, trust_env=False)
    assert client.post(SETUP, json={"code": TYPED}).status_code == 409
    assert remote_setup.read_text() == "existing-key"


@pytest.mark.parametrize("url", [
    "http://outside.example",
    "https://outside.example/extra",
    "http://127.0.0.1.outside.example",
])
def test_remote_refuses_an_unsealable_address_before_fetch(client, remote_setup, monkeypatch, url):
    monkeypatch.setattr(settings, "sync_remote_url", url)
    calls = fake_route(monkeypatch, lambda request: pytest.fail("must not fetch"), trust_env=False)
    response = client.post(SETUP, json={"code": TYPED})
    assert response.status_code == 409 and response.json()["outcome"] == "needs_person"
    assert response.json()["detail"] == TUNNEL
    assert not calls and not remote_setup.exists()


def test_a_rejected_character_never_calls_home_or_is_logged(client, remote_setup, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    calls = fake_route(monkeypatch, lambda request: pytest.fail("must not fetch"), trust_env=False)
    response = client.post(SETUP, json={"code": "0123-4567-89AB-CDEU"})
    assert response.json()["outcome"] == "needs_person"
    assert "CDEU" not in response.text + caplog.text
    assert not calls and not remote_setup.exists()


def test_remote_origin_is_refused_before_key_or_fetch(client, remote_setup, monkeypatch):
    monkeypatch.setattr(status, "read_key", lambda: pytest.fail("must not read"))
    calls = fake_route(monkeypatch, lambda request: pytest.fail("must not fetch"), trust_env=False)
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
    (404, "needs_person", CLOSED),
    (429, "needs_person", UNVERIFIED),
    (503, "transient", "Laptop unreachable."),
    (307, "needs_person", UNVERIFIED),
])
def test_remote_failures_have_fixed_sentences(client, remote_setup, monkeypatch, case):
    code, outcome, detail = case
    fake_route(monkeypatch, lambda request: httpx.Response(
        code, content=KEY.encode(), headers={"Location": "https://outside.example"}), trust_env=False)
    response = client.post(SETUP, json={"code": TYPED})
    assert response.json()["ok"] is False and response.json()["outcome"] == outcome
    assert response.json()["detail"] == detail
    assert KEY not in response.text and TYPED not in response.text
    assert not remote_setup.exists()


def test_remote_unreachable_is_transient_without_exception_text(client, remote_setup, monkeypatch):
    def unreachable(request):
        raise httpx.ConnectError(KEY)
    fake_route(monkeypatch, unreachable, trust_env=False)
    response = client.post(SETUP, json={"code": TYPED})
    assert response.json() == {"ok": False, "outcome": "transient", "detail": "Laptop unreachable."}
    assert TYPED not in response.text and not remote_setup.exists()


@pytest.mark.parametrize("body", [{"key": ""}, {"key": "a\nb"}, {"key": 3}, [], {"key": "x" * 9000}])
def test_remote_rejects_unusable_answers_without_writing(client, remote_setup, monkeypatch, body):
    fake_route(monkeypatch, lambda request: seal_answer(request, body), trust_env=False)
    response = client.post(SETUP, json={"code": TYPED})
    assert response.json()["outcome"] == "needs_person" and not remote_setup.exists()
    assert KEY not in response.text and TYPED not in response.text


def test_web_card_contract_and_rendering():
    from tests.node_ts import run_node_test
    result = run_node_test("components/settings/second-copy-section.test.mjs")
    assert result.returncode == 0, result.stdout + result.stderr


def test_setup_docs_and_settings_mount():
    from tests.node_ts import FRONTEND
    assert "<SecondCopySection />" in (FRONTEND / "app/settings/page.tsx").read_text()
    assert '"second-copy"' in (FRONTEND / "lib/settings-tabs.ts").read_text()
