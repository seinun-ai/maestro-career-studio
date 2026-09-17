"""Engine and session factory.

SQLite is the only runtime database (SYSTEM.md §3). `make_engine` is the ONE
engine constructor: the app, the test suite, the migrations' verify step and
the legacy importer all go through it, so every connection carries the same
pragmas. journal_mode is persisted in the file; the other three are
per-connection state (foreign_keys defaults to OFF). All four are set on every
connection anyway, so a `DELETE` override takes effect and nothing depends on
which connection created the file.
"""
import os
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

DB_FILENAME = "maestro_cs.sqlite3"


def sqlite_path(url: str) -> Path | None:
    """The file behind a sqlite URL, or None for another backend or :memory:."""
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite":
        return None
    if not parsed.database or parsed.database == ":memory:":
        return None
    return Path(parsed.database)


def _prepare_sqlite_file(path: Path) -> None:
    # Pre-create with the mode set rather than chmod-ing after (the
    # llm._log_call precedent): a zero-byte file is a valid empty SQLite
    # database, and the window between sqlite's own create and a chmod is a
    # window in which a world-readable copy of the career record exists.
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
        os.close(fd)


def make_engine(url: str, *, journal_mode: str | None = None) -> Engine:
    """Build an engine for `url` with the SQLite pragmas installed per connection."""
    mode = (journal_mode or settings.sqlite_journal_mode).upper()
    if mode not in {"WAL", "DELETE"}:
        raise ValueError(f"journal_mode must be WAL or DELETE, not {mode!r}")

    connect_args: dict = {}
    path: Path | None = None
    is_sqlite = make_url(url).get_backend_name() == "sqlite"
    if is_sqlite:
        # The DBAPI-level busy wait, in seconds. PRAGMA busy_timeout below is
        # the same knob for connections sqlite3 hands to other code paths.
        connect_args["timeout"] = 30
        path = sqlite_path(url)

    engine = create_engine(url, future=True, connect_args=connect_args)

    if path is not None:
        # Construction must stay inert: the MCP host venv, scripts and dev
        # shells import models (hence this module) without a writable data
        # dir. do_connect fires before the DBAPI opens the file, so the 0600
        # pre-create still wins the race; the cost is one stat per new
        # connection, and a wrong DATA_DIR fails at the first real connection.
        @event.listens_for(engine, "do_connect")
        def _prepare(_dialect, _conn_rec, _cargs, _cparams):
            _prepare_sqlite_file(path)
            return None  # let the default connect proceed

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, _record):
        if not isinstance(dbapi_connection, sqlite3.Connection):
            return
        cursor = dbapi_connection.cursor()
        cursor.execute(f"PRAGMA journal_mode={mode}")
        # 21 relationships rely on ondelete=; without this line they silently
        # stop cascading. Per connection, not per database.
        cursor.execute("PRAGMA foreign_keys=ON")
        # Durable against an app crash; may lose the last transactions on OS
        # crash or power loss. Accepted for a single-user tool with pre-update
        # backups (design §3.3).
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    return engine


# TEST_DATABASE_URL first, on purpose: the suite must never touch the file under
# data/ (tests/conftest.py refuses a URL that resolves there).
_db_url = os.environ.get("TEST_DATABASE_URL") or settings.database_url
engine = make_engine(_db_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    with SessionLocal() as session:
        yield session
