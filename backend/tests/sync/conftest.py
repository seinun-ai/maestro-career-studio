import secrets

import pytest

from app.config import settings
from app.services.sync import status


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
