import secrets

import pytest

from app.config import settings


@pytest.fixture
def sync_on(tmp_path, monkeypatch, remote_url=""):
    """Enable sync in an isolated directory, optionally as the always-on copy."""
    path = tmp_path / "settings" / "secrets" / "sync-key"
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(secrets.token_urlsafe(32) + "\n", encoding="utf-8")
    path.chmod(0o600)
    monkeypatch.setattr(settings, "settings_dir", tmp_path / "settings")
    monkeypatch.setattr(settings, "sync_key_file", path)
    monkeypatch.setattr(settings, "sync_remote_url", remote_url)
    return path
