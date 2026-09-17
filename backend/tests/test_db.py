import os
import stat
import subprocess
import sys
from pathlib import Path

from app.db import make_engine, sqlite_path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_session_factory_creates_session():
    from app.db import SessionLocal

    with SessionLocal() as s:
        assert s is not None


def test_make_engine_applies_sqlite_pragmas_per_connection(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 't.sqlite3'}")
    try:
        with engine.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
            assert conn.exec_driver_sql("PRAGMA journal_mode").scalar().lower() == "wal"
            assert conn.exec_driver_sql("PRAGMA busy_timeout").scalar() == 30000
            assert conn.exec_driver_sql("PRAGMA synchronous").scalar() == 1  # NORMAL
    finally:
        engine.dispose()


def test_make_engine_honours_delete_journal_mode(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 't.sqlite3'}", journal_mode="DELETE")
    try:
        with engine.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA journal_mode").scalar().lower() == "delete"
    finally:
        engine.dispose()


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
    finally:
        engine.dispose()


def test_import_of_app_db_does_not_touch_the_filesystem():
    # The MCP host venv, scripts and dev shells import models (hence app.db)
    # without a writable data dir; a mkdir at import would break all of them.
    result = subprocess.run(
        [sys.executable, "-c", "import app.db"],
        env={**os.environ, "TEST_DATABASE_URL": "sqlite:////nonexistent-root-for-test/x.sqlite3"},
        capture_output=True,
        text=True,
        cwd=BACKEND_DIR,
    )
    assert result.returncode == 0, result.stderr


def test_sqlite_path_only_for_file_urls():
    assert sqlite_path("sqlite://") is None
    assert sqlite_path("sqlite:///:memory:") is None
    assert sqlite_path("postgresql+psycopg://x/y") is None
    assert sqlite_path("sqlite:////tmp/a.sqlite3") == Path("/tmp/a.sqlite3")
