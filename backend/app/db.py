"""Engine and session factory.

SQLite is the only runtime database (SYSTEM.md §3). `make_engine` is the ONE
engine constructor: the app, the test suite, the migrations' verify step and
the legacy importer all go through it, so every connection carries the same
pragmas. journal_mode is persisted in the file; the other three are
per-connection state (foreign_keys defaults to OFF). All four are set on every
connection anyway, so nothing depends on which connection created the file. A
`DELETE` override takes effect on the first connection made while no other
connection holds the file; until then `make_engine` refuses loudly rather than
run in the wrong mode.
"""
import logging
import os
import sqlite3
import stat
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DB_FILENAME, settings

__all__ = [
    "Base",
    "DB_FILENAME",
    "SessionLocal",
    "engine",
    "get_db",
    "make_engine",
    "prepare_sqlite_file",
    "sqlite_path",
]

logger = logging.getLogger(__name__)

_JOURNAL_MODES = {"WAL", "DELETE"}


def _file_of(parsed: URL) -> Path | None:
    if parsed.get_backend_name() != "sqlite":
        return None
    if not parsed.database or parsed.database == ":memory:":
        return None
    return Path(parsed.database)


def sqlite_path(url: str) -> Path | None:
    """The file behind a sqlite URL, or None for another backend or :memory:."""
    return _file_of(make_url(url))


def prepare_sqlite_file(url_or_path: str | Path) -> Path | None:
    """Create the database file 0600 (directory 0700) if absent; narrow a wider
    mode if present. Returns the path, or None when the URL names no file
    (another backend, :memory:).

    Callers that connect through a plain `create_engine` -- alembic's env.py,
    the first-boot path -- call this before connecting; `make_engine` does it
    on every new connection. Pre-create with the mode set rather than
    chmod-ing after (the llm._log_call precedent): a zero-byte file is a valid
    empty SQLite database, and O_EXCL leaves no window in which a
    world-readable copy of the career record exists. A file created by a plain
    engine or restored from an archive is 0644, hence the repair.
    """
    path = url_or_path if isinstance(url_or_path, Path) else sqlite_path(url_or_path)
    if path is None:
        return None
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    except FileExistsError:
        if os.name == "posix":
            mode = stat.S_IMODE(path.stat().st_mode)
            if mode & ~0o600:
                os.chmod(path, 0o600)
                logger.warning("narrowed %s from %#o to 0600", path, mode)
    return path


def _set_journal_mode(cursor, mode: str, path: Path | None) -> None:
    try:
        got = cursor.execute(f"PRAGMA journal_mode={mode}").fetchone()[0]
    except sqlite3.OperationalError as exc:
        raise RuntimeError(
            f"could not set journal_mode={mode} on {path}: stop the backend and any "
            f"other process holding {path} before switching journal mode"
        ) from exc
    # An in-memory database answers "memory" whatever was asked: journal mode
    # is meaningless there, so there is nothing to verify.
    if path is not None and got.lower() != mode.lower():
        hint = " (a filesystem that cannot do WAL needs SQLITE_JOURNAL_MODE=DELETE)"
        raise RuntimeError(
            f"PRAGMA journal_mode={mode} left {path} in {got!r}: stop the backend and "
            f"any other process holding {path} before switching journal mode"
            + (hint if mode == "WAL" else "")
        )


def make_engine(url: str, *, journal_mode: str | None = None) -> Engine:
    """Build an engine for `url` with the SQLite pragmas installed per connection."""
    mode = (journal_mode or settings.sqlite_journal_mode).upper()
    if mode not in _JOURNAL_MODES:
        raise ValueError(f"journal_mode must be WAL or DELETE, not {mode!r}")

    parsed = make_url(url)
    is_sqlite = parsed.get_backend_name() == "sqlite"
    path = _file_of(parsed)
    connect_args: dict = {}
    if is_sqlite:
        # The DBAPI-level busy wait, in seconds: a second writer waits rather
        # than fails (design §3.3).
        connect_args["timeout"] = 30

    engine = create_engine(url, future=True, connect_args=connect_args)
    if not is_sqlite:
        return engine

    if path is not None:
        # Construction must stay inert: the MCP host venv, scripts and dev
        # shells import models (hence this module) without a writable data
        # dir. do_connect fires before the DBAPI opens the file, so the 0600
        # pre-create still wins the race; the cost is one stat per new
        # connection, and a wrong DATA_DIR fails at the first real connection.
        @event.listens_for(engine, "do_connect")
        def _prepare(_dialect, _conn_rec, _cargs, _cparams):
            prepare_sqlite_file(path)
            return None  # let the default connect proceed

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, _record):
        if not isinstance(dbapi_connection, sqlite3.Connection):
            raise TypeError(
                "make_engine installs pragmas through sqlite3.Connection, got "
                f"{type(dbapi_connection).__name__}"
            )
        cursor = dbapi_connection.cursor()
        try:
            _set_journal_mode(cursor, mode, path)
            # 21 relationships rely on ondelete=; without this line they
            # silently stop cascading. Per connection, not per database.
            cursor.execute("PRAGMA foreign_keys=ON")
            # Under WAL, NORMAL is durable against an app crash and may lose
            # the last transactions on OS crash or power loss -- accepted for a
            # single-user tool with pre-update backups (design §3.3, WAL only).
            # DELETE is the escape hatch for filesystems we already distrust,
            # so it pays for FULL.
            cursor.execute(f"PRAGMA synchronous={'NORMAL' if mode == 'WAL' else 'FULL'}")
            # Redundant with connect_args["timeout"] above (sqlite3 installs
            # the same busy handler); kept as belt-and-braces so the value is
            # visible to `PRAGMA busy_timeout` and does not depend on the
            # driver honouring the kwarg.
            cursor.execute("PRAGMA busy_timeout=30000")
        finally:
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
