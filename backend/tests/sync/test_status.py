import stat
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.config import Settings, settings
from app.models.setting import Setting


def test_sync_settings_default_to_off(monkeypatch):
    monkeypatch.delenv("SYNC_KEY_FILE", raising=False)
    monkeypatch.delenv("SYNC_REMOTE_URL", raising=False)

    config = Settings(_env_file=None)

    assert config.sync_key_file is None
    assert config.sync_remote_url == ""


def test_sync_settings_read_environment(tmp_path, monkeypatch):
    path = tmp_path / "sync-key"
    monkeypatch.setenv("SYNC_KEY_FILE", str(path))
    monkeypatch.setenv("SYNC_REMOTE_URL", "http://127.0.0.1:8101")

    config = Settings(_env_file=None)

    assert config.sync_key_file == path
    assert config.sync_remote_url == "http://127.0.0.1:8101"


def test_no_key_keeps_sync_off_even_with_remote_url(tmp_path, monkeypatch):
    from app.services.sync import status

    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    monkeypatch.setattr(settings, "sync_key_file", None)
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")

    assert status.key_path() == tmp_path / "secrets" / "sync-key"
    assert status.read_key() is None
    assert status.enabled() is False
    assert status.is_remote() is False
    assert not (tmp_path / "secrets").exists()


@pytest.mark.parametrize("remote_url", ["", "http://127.0.0.1:8101"])
def test_key_enables_sync_on_the_configured_side(sync_on, remote_url, monkeypatch):
    from app.services.sync import status

    monkeypatch.setattr(settings, "sync_remote_url", remote_url)

    assert status.key_path() == sync_on
    assert bool(status.read_key())
    assert status.enabled() is True
    assert status.is_remote() is bool(remote_url)


def test_default_key_path_enables_sync(sync_on, monkeypatch):
    from app.services.sync import status

    monkeypatch.setattr(settings, "sync_key_file", None)

    assert status.key_path() == sync_on
    assert status.enabled() is True


def test_explicit_missing_key_does_not_fall_back(sync_on, tmp_path, monkeypatch):
    from app.services.sync import status

    monkeypatch.setattr(settings, "sync_key_file", tmp_path / "missing")

    assert status.enabled() is False


@pytest.mark.parametrize("content", ["", " \t\n"])
def test_empty_key_stays_off(sync_on, content, monkeypatch):
    from app.services.sync import status

    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")
    sync_on.write_text(content, encoding="utf-8")

    assert status.read_key() is None
    assert status.enabled() is False
    assert status.is_remote() is False


def test_symlinked_key_stays_off(sync_on, tmp_path, monkeypatch):
    from app.services.sync import status

    link = tmp_path / "key-link"
    link.symlink_to(sync_on)
    monkeypatch.setattr(settings, "sync_key_file", link)
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")

    assert status.read_key() is None
    assert status.enabled() is False
    assert status.is_remote() is False


def test_directory_is_not_a_key(tmp_path, monkeypatch):
    from app.services.sync import status

    monkeypatch.setattr(settings, "sync_key_file", tmp_path)

    assert status.read_key() is None
    assert status.enabled() is False


def test_machine_id_is_stable_across_calls_and_sessions(db_session, _test_engine):
    from app.services.sync import status

    first = status.machine_id(db_session)
    assert uuid.UUID(hex=first).hex == first
    assert status.machine_id(db_session) == first
    db_session.commit()

    with Session(_test_engine) as other:
        assert status.machine_id(other) == first
        assert other.get(Setting, "sync.machine_id").value == first


def test_machine_id_creation_does_not_commit_callers_transaction(db_session):
    from app.services.sync import status

    status.machine_id(db_session)
    db_session.rollback()

    assert db_session.get(Setting, "sync.machine_id") is None


def test_machine_id_concurrent_first_use_returns_one_id(db_session, _test_engine):
    from app.services.sync import status

    barrier = Barrier(2)

    def wait_for_both_reads(session, flush_context, instances):
        barrier.wait(timeout=10)

    def first_request():
        with Session(_test_engine, autoflush=False) as session:
            event.listen(session, "before_flush", wait_for_both_reads, once=True)
            result = status.machine_id(session)
            session.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(first_request) for _ in range(2)]
        ids = [future.result(timeout=15) for future in futures]

    assert len(set(ids)) == 1
    rows = db_session.scalars(select(Setting).where(Setting.key == "sync.machine_id")).all()
    assert len(rows) == 1
    assert rows[0].value == ids[0]


def test_create_key_is_private_and_refuses_overwrite(tmp_path, monkeypatch):
    from app.services.sync import status

    monkeypatch.setattr(settings, "settings_dir", tmp_path / "settings")
    monkeypatch.setattr(settings, "sync_key_file", None)

    path = status.create_key()
    assert path == tmp_path / "settings" / "secrets" / "sync-key"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert status.enabled() is True
    original = path.read_bytes()

    with pytest.raises(FileExistsError):
        status.create_key()

    unchanged = path.read_bytes() == original
    assert unchanged


def test_create_key_uses_explicit_path(tmp_path, monkeypatch):
    from app.services.sync import status

    path = tmp_path / "private" / "pairing-key"
    monkeypatch.setattr(settings, "sync_key_file", path)

    assert status.create_key() == path
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
