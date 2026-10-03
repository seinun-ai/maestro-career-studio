"""The copy-only database guard shared by the scripts that read a COPY of the
live database (the fill evaluation, the fill-trace reader).

A script here never touches the live database: `refusal` turns away any path
that is, or lives beside, a live data directory (compared by file identity, not
spelling); `open_copy` points the app's settings at the copy before app code is
imported; `bind_read_only` binds every session to a read-only connection and
proves a write fails. Nothing the app lazily seeds or writes can reach the live
file.
"""

import os
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_FILENAME = "maestro_cs.sqlite3"


def refused_dirs() -> list[Path]:
    """Where a live database lives: every checkout's `data/` (this one and the
    main checkout, found through git's common dir) and the configured DATA_DIR
    (the running app's, /app/data by default)."""
    roots = {HERE.parents[1]}
    try:
        common = subprocess.run(["git", "-C", str(HERE), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                capture_output=True, text=True, check=True, timeout=10).stdout.strip()
        roots.add(Path(common).parent)
    except (OSError, subprocess.SubprocessError):
        pass
    dirs = [root / "data" for root in roots] + [Path(os.environ.get("DATA_DIR") or "/app/data")]
    return [d.resolve() for d in dirs]


def _identity(path: Path) -> tuple[int, int]:
    st = path.stat()
    return st.st_dev, st.st_ino


def refusal(db: Path) -> str | None:
    """Why `db` may not be evaluated against, or None.

    By file IDENTITY, never by spelling: macOS's filesystem ignores case, so
    ".../DATA/..." names the live directory while no string compare says so,
    and a hard link elsewhere IS the live file. Every directory above `db`
    is compared (device, inode) with each refused directory, and `db` itself
    with every file in them. Only stat is used: nothing is opened."""
    path = db.resolve()
    if not path.is_file():
        return f"{db} is not a file"
    refused = {}
    for d in refused_dirs():
        if d.is_dir():
            refused[_identity(d)] = d
    for parent in path.parents:
        if (d := refused.get(_identity(parent))) is not None:
            return f"{db} is inside {d}, where a live database lives: copy it elsewhere first"
    for d in refused.values():
        for live in d.iterdir():
            if live.is_file() and path.samefile(live):
                return f"{db} is the same file as {live}, a live database: copy it, never link it"
    return None


def bind_read_only(db: Path) -> None:
    """Every session the app's code opens reads `db` through a read-only
    connection; the app's own engine cannot connect at all. Raises unless a
    probe write fails."""
    import sqlite3
    from urllib.parse import quote

    from sqlalchemy import create_engine, event, text
    from sqlalchemy.exc import OperationalError

    from app import db as app_db

    uri = f"file:{quote(str(db.resolve()))}?mode=ro"
    read_only = create_engine("sqlite://", creator=lambda: sqlite3.connect(uri, uri=True, check_same_thread=False))

    @event.listens_for(read_only, "connect")
    def _query_only(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA query_only=ON")

    # insert=True: before make_engine's own do_connect listener, which would
    # pre-create (and chmod) the file its URL names.
    @event.listens_for(app_db.engine, "do_connect", insert=True)
    def _never(*_args):
        raise RuntimeError("the evaluation reads the database only through its read-only session")

    app_db.SessionLocal.configure(bind=read_only)
    with app_db.SessionLocal() as session:
        try:
            session.execute(text("CREATE TABLE eval_write_probe (x INTEGER)"))
            session.commit()
        except OperationalError:
            session.rollback()
        else:
            raise RuntimeError(f"{db} opened writable: stopping before any model call")


def open_copy(db: Path, *, bind: Callable[[Path], None] | None = None) -> None:
    """Point the app at the copy `db` and bind it read-only (`bind`, by default
    `bind_read_only`). Call after `refusal(db)` is None and before the app is
    imported: its settings read these variables once."""
    os.environ["DATABASE_URL"] = f"sqlite:///{db.resolve()}"
    os.environ.pop("TEST_DATABASE_URL", None)
    for name in ("SETTINGS_DIR", "LOGS_DIR"):
        os.environ.setdefault(name, tempfile.mkdtemp(prefix=f"eval-{name.lower()}-"))
    (bind or bind_read_only)(db)
