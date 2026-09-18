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
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from app.config import settings
from app.db import sqlite_path


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
    where sqlite wants the index.
    """
    try:
        live = sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        return sqlite3.connect(source)
    try:
        live.execute("SELECT count(*) FROM sqlite_schema").fetchone()
    except sqlite3.OperationalError:
        live.close()
        return sqlite3.connect(source)
    return live


def snapshot(source: Path, destination: Path) -> None:
    """Write a consistent copy of `source` to `destination`, then verify it.

    Every connection is closed explicitly, in a finally. `with
    sqlite3.connect(...)` commits or rolls back and leaves the connection OPEN
    -- which here would hold a handle on the caller's temp file (Windows cannot
    remove a directory whose files are open) and a read lock on the LIVE
    database for the rest of the process's life.
    """
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

    with tempfile.TemporaryDirectory() as tmp:
        image = Path(tmp) / "snapshot.sqlite3"
        snapshot(source, image)
        if args.stdout:
            with image.open("rb") as handle:
                shutil.copyfileobj(handle, sys.stdout.buffer)
            sys.stdout.buffer.flush()
        else:
            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            with image.open("rb") as handle, gzip.open(out, "wb") as packed:
                shutil.copyfileobj(handle, packed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
