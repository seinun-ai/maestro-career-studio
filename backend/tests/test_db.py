import os
import stat
from pathlib import Path

from app.db import make_engine, sqlite_path


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
    make_engine(f"sqlite:///{path}").dispose()
    assert path.exists()
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_sqlite_path_only_for_file_urls():
    assert sqlite_path("sqlite://") is None
    assert sqlite_path("sqlite:///:memory:") is None
    assert sqlite_path("postgresql+psycopg://x/y") is None
    assert sqlite_path("sqlite:////tmp/a.sqlite3") == Path("/tmp/a.sqlite3")
