import logging
import os
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from app.db import make_engine, prepare_sqlite_file, sqlite_path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _pragma(conn, name):
    return conn.exec_driver_sql(f"PRAGMA {name}").scalar()


def test_session_factory_creates_session():
    from app.db import SessionLocal

    with SessionLocal() as s:
        assert s is not None


def test_make_engine_applies_sqlite_pragmas_per_connection(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 't.sqlite3'}")
    try:
        with engine.connect() as conn:
            assert _pragma(conn, "foreign_keys") == 1
            assert _pragma(conn, "journal_mode").lower() == "wal"
            assert _pragma(conn, "busy_timeout") == 30000
            assert _pragma(conn, "synchronous") == 1  # NORMAL
        # A fresh DBAPI connection (the pool was emptied) gets them again.
        engine.dispose()
        with engine.connect() as conn:
            assert _pragma(conn, "foreign_keys") == 1
    finally:
        engine.dispose()


def test_make_engine_honours_delete_journal_mode(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 't.sqlite3'}", journal_mode="DELETE")
    try:
        with engine.connect() as conn:
            assert _pragma(conn, "journal_mode").lower() == "delete"
            assert _pragma(conn, "synchronous") == 2  # FULL: no WAL to make NORMAL safe
    finally:
        engine.dispose()


def test_make_engine_accepts_lowercase_journal_mode(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 't.sqlite3'}", journal_mode="wal")
    try:
        with engine.connect() as conn:
            assert _pragma(conn, "journal_mode").lower() == "wal"
    finally:
        engine.dispose()


def test_make_engine_refuses_other_journal_modes(tmp_path):
    with pytest.raises(ValueError, match="WAL or DELETE"):
        make_engine(f"sqlite:///{tmp_path / 't.sqlite3'}", journal_mode="TRUNCATE")


def test_make_engine_creates_the_file_with_mode_0600(tmp_path):
    path = tmp_path / "nested" / "t.sqlite3"
    engine = make_engine(f"sqlite:///{path}")
    try:
        # Construction is inert: the file (and its directory) appear on the
        # first real connection, not at import.
        assert not path.exists()
        with engine.connect():
            pass
        assert path.exists()
        if os.name == "posix":
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
            assert not stat.S_IMODE(path.parent.stat().st_mode) & 0o077
    finally:
        engine.dispose()


@pytest.mark.skipif(os.name != "posix", reason="file modes are posix-only")
def test_make_engine_narrows_a_wide_mode_on_connect(tmp_path, caplog):
    # A file created by a plain create_engine (alembic, first boot) or restored
    # from an archive is 0644; the next connection through make_engine repairs it.
    path = tmp_path / "t.sqlite3"
    path.touch()
    os.chmod(path, 0o644)
    engine = make_engine(f"sqlite:///{path}")
    try:
        with caplog.at_level(logging.WARNING, logger="app.db"):
            with engine.connect():
                pass
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert any(str(path) in r.getMessage() for r in caplog.records)
    finally:
        engine.dispose()


@pytest.mark.skipif(os.name != "posix", reason="file modes are posix-only")
def test_make_engine_still_connects_when_the_0600_repair_is_refused(tmp_path, caplog, monkeypatch):
    # A uid-mismatched bind mount or a host-created file cannot be chmod-ed by
    # this process; the repair is logged and the connection proceeds regardless.
    path = tmp_path / "t.sqlite3"
    path.touch()
    os.chmod(path, 0o644)

    def refuse(*_args, **_kwargs):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "chmod", refuse)
    engine = make_engine(f"sqlite:///{path}")
    try:
        with caplog.at_level(logging.ERROR, logger="app.db"):
            with engine.connect() as conn:
                assert _pragma(conn, "foreign_keys") == 1
        assert stat.S_IMODE(path.stat().st_mode) == 0o644  # left as found
        assert any(
            r.levelno == logging.ERROR and str(path) in r.getMessage() for r in caplog.records
        )
    finally:
        engine.dispose()


def test_prepare_sqlite_file_accepts_url_or_path(tmp_path):
    assert prepare_sqlite_file("sqlite://") is None
    assert prepare_sqlite_file("sqlite:///:memory:") is None
    assert prepare_sqlite_file("postgresql+psycopg://x/y") is None
    by_url = tmp_path / "a" / "u.sqlite3"
    by_path = tmp_path / "b" / "p.sqlite3"
    assert prepare_sqlite_file(f"sqlite:///{by_url}") == by_url
    assert prepare_sqlite_file(by_path) == by_path
    assert by_url.exists() and by_path.exists()
    assert prepare_sqlite_file(by_path) == by_path  # idempotent on an existing file


def test_make_engine_refuses_to_switch_journal_mode_under_a_holder(tmp_path):
    path = tmp_path / "t.sqlite3"
    holder = sqlite3.connect(path, isolation_level=None)  # manual transactions
    holder.execute("PRAGMA journal_mode=WAL")
    # An open read transaction holds the WAL read-mark on every SQLite
    # version; an idle connection that never read does not block the switch.
    holder.execute("BEGIN")
    holder.execute("SELECT count(*) FROM sqlite_master").fetchall()
    engine = make_engine(f"sqlite:///{path}", journal_mode="DELETE")
    try:
        with pytest.raises(RuntimeError, match="switching journal mode"):
            engine.connect()
    finally:
        engine.dispose()
        holder.close()


def test_import_of_app_db_does_not_touch_the_filesystem(tmp_path):
    # The MCP host venv, scripts and dev shells import models (hence app.db)
    # without a writable data dir; a mkdir at import would break all of them.
    result = subprocess.run(
        [sys.executable, "-c", "import app.db"],
        env={**os.environ, "TEST_DATABASE_URL": f"sqlite:///{tmp_path}/nested/x.sqlite3"},
        capture_output=True,
        text=True,
        cwd=BACKEND_DIR,
    )
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "nested").exists()


def test_sqlite_path_only_for_file_urls():
    assert sqlite_path("sqlite://") is None
    assert sqlite_path("sqlite:///:memory:") is None
    assert sqlite_path("postgresql+psycopg://x/y") is None
    assert sqlite_path("sqlite:////tmp/a.sqlite3") == Path("/tmp/a.sqlite3")
