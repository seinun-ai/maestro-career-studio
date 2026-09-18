"""SQLite online backup, for scripts/update.sh and by hand.

Never copy a live database file: pages not yet checkpointed live in the -wal
sidecar, and a plain cp takes a torn snapshot. sqlite3's backup API copies a
consistent image while the app keeps running.

    python -m app.tools.backup_db --out backups/db-<ts>.sqlite3.gz
    python -m app.tools.backup_db --stdout | gzip > backups/db-<ts>.sqlite3.gz
"""
from __future__ import annotations

import argparse
import gzip
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from app.config import settings
from app.db import sqlite_path

# Seconds to wait behind a writer, matching the app's own connections
# (app/db.py `connect_args["timeout"]`). sqlite3's default is 5, which under
# SQLITE_JOURNAL_MODE=DELETE makes the read-only probe below lose to a
# concurrent writer and silently downgrade the backup to a read-write open.
BUSY_TIMEOUT = 30

# The only failures that mean "this database cannot be opened read-only".
# Anything else is a real error and must not be papered over by reopening the
# live database read-write.
_READ_ONLY_FAILURES = ("readonly", "unable to open")


def _fall_back_to_read_write(source: Path, exc: sqlite3.OperationalError) -> sqlite3.Connection:
    if not any(sign in str(exc).lower() for sign in _READ_ONLY_FAILURES):
        raise exc
    print(f"warning: opened the database read-write for the backup ({exc})", file=sys.stderr)
    return sqlite3.connect(source, timeout=BUSY_TIMEOUT)


def _connect_source(source: Path) -> sqlite3.Connection:
    """Open the live database read-only where the platform allows it.

    A backup must never be able to write to the database it is copying, and a
    read-only connection still reads THROUGH the -wal sidecar, so the snapshot
    stays complete. `as_uri()` rather than an f-string: a data dir containing a
    space, `#` or `?` would otherwise produce a URI sqlite parses as something
    else entirely.

    One case falls back: reading a WAL database needs the -shm shared-memory
    index, which a read-only connection cannot CREATE. The app holds the
    database open, so the sidecar is there -- but after an unclean shutdown a
    hand-run backup would otherwise fail on a file it can read perfectly well.
    The probe below is what surfaces that: opening succeeds, the first read is
    where sqlite wants the index. `sqlite_master` rather than its modern alias
    `sqlite_schema`, which needs sqlite >= 3.33.
    """
    try:
        live = sqlite3.connect(
            f"{source.resolve().as_uri()}?mode=ro", uri=True, timeout=BUSY_TIMEOUT
        )
    except sqlite3.OperationalError as exc:
        return _fall_back_to_read_write(source, exc)
    try:
        live.execute("SELECT count(*) FROM sqlite_master").fetchone()
    except sqlite3.OperationalError as exc:
        live.close()
        return _fall_back_to_read_write(source, exc)
    except sqlite3.Error:
        # Corrupt, or not a database at all: there is nothing to fall back to,
        # but the handle still has to go back.
        live.close()
        raise
    return live


def snapshot(source: Path, destination: Path) -> None:
    """Write a consistent copy of `source` to `destination`, then verify it.

    Every connection is closed explicitly, in a finally. `with
    sqlite3.connect(...)` commits or rolls back and leaves the connection OPEN
    -- which here would hold a handle on the caller's temp file (Windows cannot
    remove a directory whose files are open) and a read lock on the LIVE
    database for the rest of the process's life.
    """
    # Checked before anything opens the path: `sqlite3.connect` CREATES a
    # missing file, so without this a mistyped --source produced an empty,
    # integrity-clean, plausible-looking backup -- the one failure mode a
    # backup tool must not have.
    if not source.is_file():
        raise FileNotFoundError(source)

    live = _connect_source(source)
    try:
        copy = sqlite3.connect(destination)
        try:
            live.backup(copy)
        finally:
            copy.close()
    finally:
        live.close()

    check = sqlite3.connect(destination)
    try:
        verdict = check.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        check.close()
    if verdict != "ok":
        raise RuntimeError(f"snapshot failed integrity_check: {verdict}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--source", default=None, help="database file (default: the app's database_url)"
    )
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument("--out", help="write a gzipped snapshot here")
    output.add_argument(
        "--stdout", action="store_true", help="write the raw snapshot bytes to stdout"
    )
    args = parser.parse_args(argv)

    source = Path(args.source) if args.source else sqlite_path(settings.database_url)
    if source is None:
        print(
            f"error: no database file to back up: {settings.database_url} names none",
            file=sys.stderr,
        )
        return 1
    if not source.exists():
        print(f"error: no database file at {source}", file=sys.stderr)
        return 1

    try:
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "snapshot.sqlite3"
            snapshot(source, image)
            if args.stdout:
                _stream(image)
            else:
                _write_gzip(image, Path(args.out))
    except BrokenPipeError:
        # `--stdout | head` closes the pipe early. Point stdout at devnull so
        # the interpreter's flush at exit does not raise this a second time and
        # print "Exception ignored" after we have already returned.
        _silence_stdout()
        return 1
    except (RuntimeError, sqlite3.Error, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _stream(image: Path) -> None:
    with image.open("rb") as handle:
        shutil.copyfileobj(handle, sys.stdout.buffer)
    sys.stdout.buffer.flush()


def _write_gzip(image: Path, out: Path) -> None:
    """Write the snapshot to `out` as gzip, 0600 in a 0700 directory.

    A backup holds every row of the career record, so it gets the mode the
    database itself gets (app.db.prepare_sqlite_file). Created WITH the mode
    rather than chmod-ed after, which would leave a world-readable window; the
    fchmod narrows a backup an earlier, wider-umask run left behind, since
    O_CREAT's mode applies only to a file it actually creates.
    """
    out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    # Both handles are closed, innermost first: GzipFile.close() writes the
    # trailer but does NOT close the file it was handed.
    with os.fdopen(fd, "wb") as raw:
        if os.name == "posix":
            os.fchmod(fd, 0o600)
        with gzip.GzipFile(fileobj=raw, mode="wb") as packed, image.open("rb") as handle:
            shutil.copyfileobj(handle, packed)


def _silence_stdout() -> None:
    try:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    except (OSError, ValueError):
        # No real fd behind stdout (pytest's capture, a StringIO): nothing to
        # silence, and nothing that can raise at exit either.
        pass


if __name__ == "__main__":
    sys.exit(main())
