"""The published hostname is accepted only under /api/sync/ (sealed-sync Task 4).

A path is under that prefix only when it starts with ``/api/sync/`` and still does
after normalization. ``/api/sync`` with no further segment, ``/api/sync-setup``,
and anything that can climb out (``..``, a percent-encoded segment, ``//``) are
the same host refusal TrustedHostMiddleware already returns.
"""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, settings
from app.db import get_db
from app.main import app
from app.services.sync import seal, status
from tests.sync.conftest import raw

PUBLIC = "mac.tailnet.ts.net"
INVALID = "Invalid host header"
REFUSED_PATHS = (
    "/",
    "/health",
    "/api/health",
    "/docs",
    "/openapi.json",
    "/api/jobs",
    "/api/settings/persona",
    "/api/sync",
    "/api/sync/",
    "/api/sync-setup/enroll",
    "/api/syncology",
    "/API/sync/hello",
    "/not/api/sync/hello",
    "/health?p=/api/sync/hello",
)
LOOKALIKE_HOSTS = (
    "xmac.tailnet.ts.net",
    "mac.tailnet.ts.net.evil.test",
    "mac.tailnet.ts.net:443.evil.test",
    "mac.tailnet.ts.net:443:80",
    "mac.tailnet.ts.net:",
    "mac.tailnet.ts.net:abc",
    "not-the-host.example",
)
# Sent raw so the client cannot collapse ``..`` or ``//`` before the app sees them.
RAW_PATHS = (
    "/api/sync/../docs",
    "/api/sync/../openapi.json",
    "/api/sync/%2e%2e/docs",
    "/api/sync//hello",
    "/api/sync\\../docs",
)


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


@pytest.fixture
def publish(monkeypatch):
    monkeypatch.setattr(settings, "sync_public_host", PUBLIC)
    return PUBLIC


def _assert_refused(response) -> None:
    assert response.status_code == 400
    assert response.text == INVALID
    assert "access-control-allow-origin" not in {name.lower() for name in response.headers}


def _sealed_hello(client, peer, host):
    secret = status.read_key()
    header, wire, rid = seal.seal_request(secret, "GET", "/api/sync/hello", "", b"", peer)
    response = raw(client, "GET", "/api/sync/hello", content=wire, headers={
        seal.HEADER: header, "X-Maestro-Sync": peer, "Host": host,
    })
    assert response.status_code == 200, response.content
    assert seal.HEADER.lower() in response.headers
    plain = seal.open_response(
        secret, rid, response.status_code, response.headers[seal.HEADER], response.content)
    return json.loads(plain)


def _raw_http(path: str, headers: list[tuple[bytes, bytes]]) -> tuple[int, bytes]:
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
        "scheme": "http", "path": path, "raw_path": path.encode("ascii"), "query_string": b"",
        "headers": headers, "client": ("127.0.0.1", 9), "server": ("testserver", 80),
    }
    asyncio.run(app(scope, receive, send))
    status_code = next(message["status"] for message in sent if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")
    return status_code, body


def test_sync_public_host_defaults_to_empty():
    field = Settings.model_fields.get("sync_public_host")
    assert field is not None and field.default == ""
    assert settings.sync_public_host == ""


@pytest.mark.parametrize("case", [
    (PUBLIC, PUBLIC),
    (PUBLIC, "Mac.Tailnet.TS.net"),
    ("Mac.Tailnet.TS.net", PUBLIC),
    (PUBLIC, f"{PUBLIC}:443"),
    (PUBLIC, "Mac.Tailnet.TS.net:8443"),
])
def test_a_sealed_hello_on_the_public_host_succeeds(client, sync_on, peer, monkeypatch, case):
    configured, host = case
    monkeypatch.setattr(settings, "sync_public_host", configured)
    body = _sealed_hello(client, peer, host)
    assert body["protocol"] == status.SYNC_PROTOCOL
    assert body["machine_id"] and body["machine_id"] != "remote-1"
    assert PUBLIC not in settings.allowed_hosts
    # The same Host is still refused off /api/sync/, including after a sync call
    # that a buggy allowlist append would have just admitted.
    _assert_refused(client.get("/health", headers={"Host": host}))


def test_the_public_host_is_read_on_each_request(client, sync_on, peer, monkeypatch):
    """main.py captured allowed_hosts at import. This setting must not be."""
    monkeypatch.setattr(settings, "sync_public_host", "")
    _assert_refused(client.get("/api/sync/hello", headers={"Host": PUBLIC}))
    monkeypatch.setattr(settings, "sync_public_host", PUBLIC)
    body = _sealed_hello(client, peer, PUBLIC)
    assert body["protocol"] == status.SYNC_PROTOCOL
    monkeypatch.setattr(settings, "sync_public_host", "other.example.test")
    _assert_refused(client.get("/api/sync/hello", headers={"Host": PUBLIC}))


def test_an_unsealed_hello_on_the_public_host_is_the_bare_404(client, sync_on, publish):
    response = client.get("/api/sync/hello", headers={"Host": PUBLIC})
    assert response.status_code == 404
    assert response.content == b""


def test_the_round_route_is_refused_on_the_public_host(client, publish):
    # /round is the always-on copy's own loopback call; the published name never reaches it.
    _assert_refused(client.post("/api/sync/round", headers={"Host": PUBLIC}, json={}))
    _assert_refused(client.get("/api/sync/round/", headers={"Host": PUBLIC}))


def test_enroll_is_not_a_host_refusal_on_the_public_host(client, publish):
    # Pairing through the published name needs /enroll.
    response = client.post("/api/sync/enroll", headers={"Host": PUBLIC})
    assert response.text != INVALID


@pytest.mark.parametrize("path", REFUSED_PATHS)
def test_the_public_host_is_refused_off_the_sync_tree(client, publish, path):
    _assert_refused(client.get(path, headers={"Host": PUBLIC}))


def test_setup_enroll_on_the_public_host_is_refused(client, publish):
    _assert_refused(client.post("/api/sync-setup/enroll", headers={"Host": PUBLIC}))


@pytest.mark.parametrize("host", LOOKALIKE_HOSTS)
def test_a_lookalike_host_is_refused_on_a_sync_path(client, publish, host):
    _assert_refused(client.get("/api/sync/hello", headers={"Host": host}))


@pytest.mark.parametrize("configured", ["*", "*.tailnet.ts.net", "mac.tailnet.ts.net.evil.test"])
def test_the_public_host_is_one_name_not_a_pattern(client, monkeypatch, configured):
    monkeypatch.setattr(settings, "sync_public_host", configured)
    _assert_refused(client.get("/api/sync/hello", headers={"Host": PUBLIC}))
    _assert_refused(client.get("/health", headers={"Host": "evil.example"}))


@pytest.mark.parametrize("path", RAW_PATHS)
def test_a_sync_prefix_that_escapes_is_refused(publish, path):
    code, body = _raw_http(path, [(b"host", PUBLIC.encode("ascii"))])
    assert (code, body) == (400, INVALID.encode())


def test_two_host_headers_are_refused(publish):
    code, body = _raw_http("/api/sync/hello", [
        (b"host", PUBLIC.encode("ascii")),
        (b"host", b"evil.example"),
    ])
    assert (code, body) == (400, INVALID.encode())


@pytest.mark.parametrize("path", ["/", "/health", "/docs", "/openapi.json", "/api/sync/hello", "/api/jobs"])
def test_without_the_setting_the_public_host_is_refused(client, path):
    assert getattr(settings, "sync_public_host", "") == ""
    _assert_refused(client.get(path, headers={"Host": PUBLIC}))


def test_loopback_hosts_stay_allowed(client, sync_on, peer, publish):
    assert client.get("/health").status_code == 200
    assert client.get("/health", headers={"Host": "localhost"}).status_code == 200
    assert client.get("/health", headers={"Host": "127.0.0.1:8001"}).status_code == 200
    body = _sealed_hello(client, peer, "testserver")
    assert body["protocol"] == status.SYNC_PROTOCOL
