import asyncio
import os
import stat
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Thread

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


def test_key_enables_sync_on_the_home_side(sync_on):
    from app.services.sync import status

    assert status.key_path() == sync_on
    assert bool(status.read_key())
    assert status.enabled() is True
    assert status.is_remote() is False


def test_key_enables_sync_on_the_remote_side(sync_remote):
    from app.services.sync import status

    assert status.key_path() == sync_remote
    assert status.enabled() is True
    assert status.is_remote() is True


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


def test_fifo_key_returns_without_waiting_for_a_writer(tmp_path, monkeypatch):
    from app.services.sync import status

    path = tmp_path / "sync-key"
    os.mkfifo(path)
    monkeypatch.setattr(settings, "sync_key_file", path)
    results = []
    reader = Thread(target=lambda: results.append(status.read_key()), daemon=True)
    reader.start()
    reader.join(2)
    finished = not reader.is_alive()
    if not finished:
        # Release the blocking reader on a red run so it cannot outlive the test.
        writer = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
        os.close(writer)
        reader.join(2)

    assert finished
    assert results == [None]


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

    def first_request():
        with Session(_test_engine, autoflush=False) as session:
            barrier.wait(timeout=10)
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


def _machine_id_race_listener(engine, winner_id, attempted_creation):
    from app.services.sync import status

    winner_committed = False

    def commit_winner_after_first_read(*args):
        nonlocal winner_committed
        statement, parameters = args[2:4]
        if "ON CONFLICT(key) DO NOTHING" in statement:
            attempted_creation.append(True)
        if winner_committed:
            return
        if not statement.startswith("SELECT settings.value") or parameters != (status.MACHINE_ID_KEY,):
            return
        with Session(engine, autoflush=False) as winner:
            winner.add(Setting(key=status.MACHINE_ID_KEY, value=winner_id))
            winner.commit()
        winner_committed = True

    return commit_winner_after_first_read


def test_machine_id_race_preserves_callers_pending_setting(db_session, _test_engine):
    from app.services.sync import status

    winner_id = uuid.uuid4().hex
    db_session.add(Setting(key="caller.pending", value="must-survive"))
    attempted_creation = []
    listener = _machine_id_race_listener(_test_engine, winner_id, attempted_creation)
    connection = db_session.connection()
    event.listen(connection, "after_cursor_execute", listener)
    try:
        machine_id = status.machine_id(db_session)
        db_session.commit()
    finally:
        event.remove(connection, "after_cursor_execute", listener)

    assert attempted_creation == [True]
    assert machine_id == winner_id
    with Session(_test_engine) as observer:
        pending = observer.get(Setting, "caller.pending")
        assert pending is not None
        assert pending.value == "must-survive"


def test_machine_id_works_inside_before_flush_on_first_use(db_session):
    from app.services.sync import status

    machine_ids = []

    def load_machine_id(session, flush_context, instances):
        machine_ids.append(status.machine_id(session))

    event.listen(db_session, "before_flush", load_machine_id)
    try:
        db_session.add(Setting(key="before-flush.trigger", value="write"))
        db_session.flush()
    finally:
        event.remove(db_session, "before_flush", load_machine_id)

    db_session.commit()
    assert len(machine_ids) == 1
    assert db_session.get(Setting, "sync.machine_id").value == machine_ids[0]


def test_ensure_machine_id_is_noop_when_sync_is_off(db_session):
    from app.services.sync import status

    assert status.ensure_machine_id() is None
    assert db_session.get(Setting, "sync.machine_id") is None


def test_ensure_machine_id_commits_when_sync_is_on(sync_on, db_session):
    from app.services.sync import status

    machine_id = status.ensure_machine_id()

    assert uuid.UUID(hex=machine_id).hex == machine_id
    assert db_session.get(Setting, "sync.machine_id").value == machine_id


@pytest.mark.parametrize("sync_configured", [False, True])
def test_lifespan_persists_machine_id_only_when_sync_is_on(
    sync_on, db_session, monkeypatch, sync_configured
):
    from app import main
    from app.services.sync import status

    if not sync_configured:
        sync_on.unlink()
    startup_id_present = []

    def record_id_presence():
        startup_id_present.append(db_session.get(Setting, status.MACHINE_ID_KEY) is not None)

    monkeypatch.setattr(main.http_client, "repair_proxy_env", lambda: None)
    monkeypatch.setattr(main.seeding, "run_startup", record_id_presence)
    monkeypatch.setattr(main, "_log_llm_config", record_id_presence)
    monkeypatch.setattr(main.automation_prompts, "load_cards", lambda: None)
    monkeypatch.setattr(main.tracing, "shutdown", lambda: None)

    async def run_lifespan():
        async with main.lifespan(main.app):
            pass

    asyncio.run(run_lifespan())

    assert startup_id_present == [False, sync_configured]
    row = db_session.get(Setting, status.MACHINE_ID_KEY)
    assert (row is not None) == sync_configured
    if sync_configured:
        first_id = status.machine_id(db_session)
        db_session.rollback()
        assert status.machine_id(db_session) == first_id


@pytest.mark.parametrize("unreadable", ["key", "parent"])
def test_unreadable_key_fails_closed_and_logs_one_safe_warning(
    sync_on, monkeypatch, caplog, unreadable
):
    import logging

    from app.services.sync import status

    sync_on.write_text("test-private-key-sentinel", encoding="utf-8")
    denied_path = {"key": sync_on, "parent": sync_on.parent}[unreadable]
    previous_mode = stat.S_IMODE(denied_path.stat().st_mode)
    denied_path.chmod(0)
    real_open = status.os.open

    def deny_key_open(candidate, flags, *args, **kwargs):
        if Path(candidate) in {denied_path, denied_path / sync_on.name}:
            raise PermissionError("permission denied")
        return real_open(candidate, flags, *args, **kwargs)

    monkeypatch.setattr(status.os, "open", deny_key_open)
    try:
        with caplog.at_level(logging.WARNING, logger=status.__name__):
            first_read_off = status.enabled() is False
            second_read_off = status.enabled() is False
    finally:
        denied_path.chmod(previous_mode)

    warnings = [record for record in caplog.records if "sync key file" in record.message]
    safe_log = all(
        (
            "test-private-key-sentinel" not in caplog.text,
            str(sync_on) not in caplog.text,
            *(
                record.message == "The sync key file can't be read; sync is off."
                for record in warnings
            ),
        )
    )
    assert first_read_off and second_read_off
    assert len(warnings) == 1
    assert safe_log


@pytest.mark.parametrize("invalid_bytes", [b"\xff\xfe", b"\xff"])
def test_invalid_utf8_key_fails_closed_and_warns_once(sync_on, caplog, invalid_bytes):
    import logging

    from app.services.sync import status

    sync_on.write_bytes(invalid_bytes)

    with caplog.at_level(logging.WARNING, logger=status.__name__):
        first_read_off = status.enabled() is False
        second_read_off = status.enabled() is False

    assert first_read_off and second_read_off
    assert sum("sync key file" in record.message for record in caplog.records) == 1


def test_symlink_swap_between_check_and_open_is_refused(sync_on, tmp_path, monkeypatch, caplog):
    import logging

    from app.services.sync import status

    target = tmp_path / "key-target"
    target.write_text("test-private-key-sentinel", encoding="utf-8")
    real_open = status.os.open
    swapped = False

    def swap_then_open(candidate, flags, *args, **kwargs):
        nonlocal swapped
        if Path(candidate) == sync_on and not swapped:
            sync_on.unlink()
            sync_on.symlink_to(target)
            swapped = True
        return real_open(candidate, flags, *args, **kwargs)

    monkeypatch.setattr(status.os, "open", swap_then_open)
    with caplog.at_level(logging.WARNING, logger=status.__name__):
        sync_is_off = status.enabled() is False

    safe_log = "test-private-key-sentinel" not in caplog.text
    assert swapped
    assert sync_is_off
    assert safe_log


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


def test_create_key_repairs_existing_parent_permissions(tmp_path, monkeypatch):
    from app.services.sync import status

    parent = tmp_path / "settings" / "secrets"
    parent.mkdir(mode=0o755, parents=True)
    parent.chmod(0o755)
    monkeypatch.setattr(settings, "sync_key_file", parent / "sync-key")

    status.create_key()

    assert stat.S_IMODE(parent.stat().st_mode) == 0o700
