import json as _json
import os
import secrets
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

import httpx
import pytest
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import make_engine
from app.services.sync import seal, status


@pytest.fixture(autouse=True)
def reset_key_read_warning(monkeypatch):
    monkeypatch.setattr(status, "_KEY_READ_WARNING_LOGGED", False)


@pytest.fixture
def sync_on(tmp_path, monkeypatch):
    """Enable sync in an isolated directory as the home copy."""
    path = tmp_path / "settings" / "secrets" / "sync-key"
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(secrets.token_urlsafe(32) + "\n", encoding="utf-8")
    path.chmod(0o600)
    monkeypatch.setattr(settings, "settings_dir", tmp_path / "settings")
    monkeypatch.setattr(settings, "sync_key_file", path)
    monkeypatch.setattr(settings, "sync_remote_url", "")
    return path


@pytest.fixture
def sync_remote(sync_on, monkeypatch):
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")
    return sync_on


BACKEND = Path(__file__).resolve().parents[2]


def _home_env(root, key_file):
    """Neither migrations nor the backend may inherit the test worker's database."""
    env = os.environ.copy()
    env.pop("TEST_DATABASE_URL", None)
    for name in ("data", "settings", "applications", "base_resumes", "kb_documents", "logs", "exports"):
        directory = root / name
        directory.mkdir(parents=True, exist_ok=True)
        env[f"{name.upper()}_DIR"] = str(directory)
    env.update(DATABASE_URL=f"sqlite:///{root / 'data' / 'home.sqlite3'}",
               SYNC_KEY_FILE=str(key_file), SYNC_REMOTE_URL="",
               OPENAI_API_KEY="", GEMINI_API_KEY="", LANGFUSE_PUBLIC_KEY="",
               LANGFUSE_SECRET_KEY="", LANGFUSE_HOST="", ALLOWED_HOSTS="127.0.0.1,localhost")
    return env


class HomeBackend:
    """One real home process per module, with restart support for the lost-line test."""

    def __init__(self, root, port, key_file):
        self.root, self.port, self.key_file = root, port, key_file
        self.url = f"http://127.0.0.1:{port}"
        self.env = _home_env(root, key_file)
        self.process = None
        self.engine = make_engine(self.env["DATABASE_URL"])
        self.session = sessionmaker(bind=self.engine, autoflush=False)
        self.http = httpx.Client(base_url=self.url, timeout=10, trust_env=False)

    def migrate(self):
        result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                                cwd=BACKEND, env=self.env, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=30)
        if result.returncode:
            pytest.fail("The isolated home migration failed; no subprocess contents are echoed.")

    def start(self):
        self.process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
             "--port", str(self.port), "--no-access-log", "--log-level", "error"],
            cwd=BACKEND, env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                pytest.fail("The isolated home backend exited before becoming healthy.")
            try:
                if self.http.get("/health").status_code == 200:
                    return
            except httpx.TransportError:
                pass
            time.sleep(0.05)
        pytest.fail("The isolated home backend did not become healthy within 20 seconds.")

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=10)

    def close(self):
        self.stop()
        self.http.close()
        self.engine.dispose()


@pytest.fixture(scope="module")
def home_backend(tmp_path_factory):
    """A migrated backend on loopback; intentionally runs even with MAESTRO_SKIP_SLOW."""
    with socket.socket() as available:
        try:
            available.bind(("127.0.0.1", 0))
        except PermissionError:
            pytest.skip("Real two-process sync tests require loopback sockets blocked by this sandbox.")
        port = available.getsockname()[1]
    root = tmp_path_factory.mktemp("sync-home")
    key_file = root / "settings" / "secrets" / "sync-key"
    key_file.parent.mkdir(mode=0o700, parents=True)
    key_file.write_text(secrets.token_urlsafe(32) + "\n", encoding="utf-8")
    key_file.chmod(0o600)
    backend = HomeBackend(root, port, key_file)
    try:
        backend.migrate()
        backend.start()
        yield backend
    finally:
        backend.close()


def _transmit(client, method, path, **kwargs):
    send = getattr(client, "transmit", None)
    if send is None:
        return client.request(method, path, **kwargs)
    return send(method, path, **kwargs)


def _target(path, params):
    base, _, query = path.partition("?")
    if params:
        extra = urlencode(list(params.items()))
        query = f"{query}&{extra}" if query else extra
    return base, query


@dataclass
class _Seal:
    """One sealed call. Bundled so the send helper stays within the parameter cap."""

    method: str
    path: str
    json: object = None
    params: object = None
    key: str | None = None
    peer: str | None = None
    content: bytes | None = None
    headers: dict | None = None


def _payload(call: _Seal) -> bytes:
    if call.json is not None:
        return _json.dumps(call.json).encode()
    if call.content is None:
        return b""
    if isinstance(call.content, bytes):
        return call.content
    raise TypeError("sealed content must be bytes")


def _send_sealed(client, call: _Seal):
    secret = status.read_key() if call.key is None else call.key
    body = _payload(call)
    base, query = _target(call.path, call.params)
    header, wire, rid = seal.seal_request(secret, call.method, base, query, body, call.peer or "")
    send = dict(call.headers or {})
    send[seal.HEADER] = header
    if call.peer:
        send["X-Maestro-Sync"] = call.peer
    url = f"{base}?{query}" if query else base
    response = _transmit(client, call.method, url, content=wire, headers=send)
    return response, rid, secret


def sealed(client, method, path, *, json=None, params=None, key=None, peer=None):
    """Seal a call, send it, and open the response. ``(status, parsed_json)``."""
    response, rid, secret = _send_sealed(
        client, _Seal(method, path, json=json, params=params, key=key, peer=peer))
    if seal.HEADER.lower() not in response.headers:
        raise AssertionError(f"response was not sealed ({response.status_code})")
    plain = seal.open_response(secret, rid, response.status_code,
                               response.headers[seal.HEADER], response.content)
    parsed = _json.loads(plain) if plain else None
    return response.status_code, parsed


def raw(client, method, path, **kwargs):
    """An unsealed call. The response is whatever the server sent."""
    return _transmit(client, method, path, **kwargs)
