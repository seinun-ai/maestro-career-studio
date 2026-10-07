"""Two real backend processes: allow, fetch privately, then pair."""

import hashlib
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from tests.sync.conftest import HomeBackend


def free_port():
    with socket.socket() as available:
        try:
            available.bind(("127.0.0.1", 0))
        except PermissionError:
            pytest.skip("Real pairing tests require loopback sockets blocked by this sandbox.")
        return available.getsockname()[1]


@pytest.fixture
def copies(tmp_path):
    home_root, remote_root = tmp_path / "home", tmp_path / "remote"
    home = HomeBackend(home_root, free_port(), home_root / "settings/secrets/sync-key")
    remote = HomeBackend(remote_root, free_port(), remote_root / "sync-key")
    remote.env["SYNC_REMOTE_URL"] = home.url
    python = remote_root / "venv/bin/python"
    python.parent.mkdir(parents=True)
    python.symlink_to(sys.executable)
    config = remote_root / "maestro.env"
    config.write_text(f"MAESTRO_PORT={remote.port}\nSYNC_REMOTE_URL={home.url}\n")
    config.chmod(0o600)
    try:
        for backend in (home, remote):
            backend.migrate()
            backend.start()
        yield home, remote
    finally:
        remote.close()
        home.close()


def test_allow_fetch_and_pair_in_one_go(copies):
    home, remote = copies
    assert not home.key_file.exists() and not remote.key_file.exists()
    assert home.http.get("/api/sync/hello").status_code == 404
    opened = home.http.post("/api/settings/second-copy", headers={
        "Origin": "http://localhost:3000"})
    assert opened.status_code == 200
    code = opened.json()["code"]
    script = Path(__file__).resolve().parents[2] / "scripts/native/sync.sh"
    result = subprocess.run(["bash", str(script), "--pair", "--code", code],
                            env={**os.environ, "MAESTRO_HOME": str(remote.root)},
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, "The pairing script failed; subprocess output is withheld."
    assert "Synced." in result.stdout
    output = result.stdout + result.stderr
    assert not (code in output or home.key_file.read_text().strip() in output), (
        "pairing output contained a secret")
    assert hashlib.sha256(remote.key_file.read_bytes()).digest() == hashlib.sha256(
        home.key_file.read_bytes()).digest()
    assert remote.key_file.stat().st_mode & 0o777 == 0o600
    card = home.http.get("/api/settings/second-copy").json()
    assert "code" not in card and code not in home.http.get("/api/settings/second-copy").text
    assert card["open_until"] is None and card["last_paired_at"] is not None
    assert remote.http.post("/api/sync-setup/enroll", json={"code": code}).status_code == 409
