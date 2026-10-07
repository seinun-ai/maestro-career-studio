"""The published hostname is accepted only under /api/sync/ (sealed-sync Task 4).

A path is under that prefix only when it starts with ``/api/sync/`` and still does
after normalization. ``/api/sync`` with no further segment, ``/api/sync-setup``,
and anything that can climb out (``..``, a percent-encoded segment, ``//``) are
the same host refusal TrustedHostMiddleware already returns.
"""

import asyncio
import json
from pathlib import Path

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


def _exchange(method: str, path: str, headers: list[tuple[bytes, bytes]]) -> tuple:
    """Status, body, and response headers, as the app sent them."""
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
        "scheme": "http", "path": path, "raw_path": path.encode("ascii"), "query_string": b"",
        "headers": headers, "client": ("127.0.0.1", 9), "server": ("testserver", 80),
    }
    asyncio.run(app(scope, receive, send))
    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")
    kept = tuple((name.lower(), value) for name, value in start.get("headers", []))
    return start["status"], body, kept


def _raw_http(path: str, headers: list[tuple[bytes, bytes]]) -> tuple[int, bytes]:
    status_code, body, _headers = _exchange("GET", path, headers)
    return status_code, body


def test_sync_public_host_defaults_to_empty():
    field = Settings.model_fields.get("sync_public_host")
    assert field is not None and field.default == ""
    assert settings.sync_public_host == ""


def test_compose_forwards_sync_public_host_to_the_backend():
    """An empty shell value must reach the container as empty, not as an unset name."""
    text = (Path(__file__).resolve().parents[3] / "docker-compose.yml").read_text()
    backend, _sep, _frontend = text.partition("\n  frontend:\n")
    assert "\n      SYNC_PUBLIC_HOST: ${SYNC_PUBLIC_HOST:-}\n" in backend


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


# The reference is an allowed host, so it never enters the public-name wrapper.
# Comparing two public-name responses to each other would pass a wrapper that
# invented its own 404.
_BARE = (404, b"", ((b"content-length", b"0"),))


@pytest.mark.parametrize(("method", "path", "extra"), [
    ("GET", "/api/sync/nope", ()),
    ("POST", "/api/sync/hello", ()),
    ("GET", "/api/sync/hello/", ()),
    ("GET", "/api/sync/hello", ((b"origin", b"https://evil.example"),)),
    ("GET", "/api/sync/hello", ((b"origin", b"http://localhost:3000"),)),
    ("GET", "/api/sync/hello", ()),
    # A seal on the request must not preserve the response. The header that matters
    # is the one on the way out.
    ("GET", "/api/sync/nope", ((b"x-maestro-seal", b"2.not-a-seal"),)),
])
def test_the_public_host_matches_the_sync_routes_bare_404(
        client, sync_on, publish, method, path, extra):
    """Unknown paths, the wrong method, a slash redirect, and any Origin are the empty 404.

    Compared with an unsealed hello on an allowed host, so a JSON 404, a 405, a 307,
    the origin guard's 403, or CORS headers on an empty 404 all fail. A seal header on
    the request does not count; only the response header lets a body through.
    """
    reference = _exchange("GET", "/api/sync/hello", [(b"host", b"testserver")])
    assert reference == _BARE
    seen = _exchange(method, path, [(b"host", PUBLIC.encode("ascii")), *extra])
    assert seen == reference


def test_a_sealed_refusal_on_the_public_host_keeps_the_seal(client, sync_on, peer, publish):
    """A sealed non-200 (version mismatch) stays sealed. Rewriting every non-200 would drop it."""
    protocol, revision, remote = peer.split(":")
    bad = f"{int(protocol) + 1}:{revision}:{remote}"
    secret = status.read_key()
    header, wire, rid = seal.seal_request(secret, "GET", "/api/sync/hello", "", b"", bad)
    response = raw(client, "GET", "/api/sync/hello", content=wire, headers={
        seal.HEADER: header, "X-Maestro-Sync": bad, "Host": PUBLIC,
    })
    assert response.status_code == 409
    plain = seal.open_response(secret, rid, 409, response.headers[seal.HEADER], response.content)
    assert json.loads(plain)["reason"] == "version"


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


@pytest.mark.parametrize("headers", [
    [],
    [(b"host", b"evil.example"), (b"host", b"also.example")],
    [(b"host", b"evil.example:abc")],
])
def test_an_empty_setting_refuses_a_host_that_normalizes_blank(monkeypatch, headers):
    """No Host, two Hosts, and a non-numeric port all normalize to the empty name.

    That empty name must not match an empty SYNC_PUBLIC_HOST, or dropping the
    'not configured' guard would admit them onto /api/sync/hello.
    """
    monkeypatch.setattr(settings, "sync_public_host", "")
    code, body = _raw_http("/api/sync/hello", headers)
    assert (code, body) == (400, INVALID.encode())


def test_loopback_hosts_stay_allowed(client, sync_on, peer, publish):
    assert client.get("/health").status_code == 200
    assert client.get("/health", headers={"Host": "localhost"}).status_code == 200
    assert client.get("/health", headers={"Host": "127.0.0.1:8001"}).status_code == 200
    body = _sealed_hello(client, peer, "testserver")
    assert body["protocol"] == status.SYNC_PROTOCOL
