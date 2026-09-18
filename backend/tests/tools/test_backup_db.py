import gzip
import os
import sqlite3
import stat

import pytest
import sqlalchemy as sa

from app.db import make_engine
from app.tools import backup_db


def _db_with_rows(path):
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        conn.executemany("INSERT INTO t (v) VALUES (?)", [("a",), ("b",), ("c",)])
    return path


def test_backup_writes_a_gzipped_consistent_snapshot(tmp_path):
    src = _db_with_rows(tmp_path / "live.sqlite3")
    out = tmp_path / "backup.sqlite3.gz"

    assert backup_db.main(["--source", str(src), "--out", str(out)]) == 0

    restored = tmp_path / "restored.sqlite3"
    restored.write_bytes(gzip.decompress(out.read_bytes()))
    with sqlite3.connect(restored) as conn:
        assert conn.execute("SELECT count(*) FROM t").fetchone()[0] == 3
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_backup_streams_raw_bytes_to_stdout(tmp_path, capsysbinary):
    src = _db_with_rows(tmp_path / "live.sqlite3")

    assert backup_db.main(["--source", str(src), "--stdout"]) == 0

    raw = capsysbinary.readouterr().out
    assert raw.startswith(b"SQLite format 3\x00")


def test_backup_includes_rows_still_in_the_wal(tmp_path):
    """The reason this tool exists: under WAL the newest pages are NOT in the
    database file, so a `cp` of it takes a torn (here, empty) snapshot. The
    online backup API reads through the -wal sidecar."""
    src = tmp_path / "live.sqlite3"
    engine = make_engine(f"sqlite:///{src}", journal_mode="WAL")
    # Held open for the whole test, exactly as the running app holds it: the
    # -wal is folded into the database file only when the LAST connection
    # closes, so while this one lives nothing is checkpointed.
    live = engine.connect()
    out = tmp_path / "backup.sqlite3.gz"
    try:
        live.execute(sa.text("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)"))
        for value in ("a", "b", "c"):
            live.execute(sa.text("INSERT INTO t (v) VALUES (:v)"), {"v": value})
        live.commit()

        wal = tmp_path / "live.sqlite3-wal"
        assert wal.exists() and wal.stat().st_size > 0, "nothing to prove: the WAL is empty"

        assert backup_db.main(["--source", str(src), "--out", str(out)]) == 0
    finally:
        live.close()
        engine.dispose()

    restored = tmp_path / "restored.sqlite3"
    restored.write_bytes(gzip.decompress(out.read_bytes()))
    with sqlite3.connect(restored) as conn:
        assert conn.execute("SELECT count(*) FROM t").fetchone()[0] == 3
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")
def test_backup_output_is_private(tmp_path):
    """A backup holds every row of the career record; it gets the mode the
    database file itself gets."""
    src = _db_with_rows(tmp_path / "live.sqlite3")
    out = tmp_path / "backups" / "db-20260918.sqlite3.gz"

    assert backup_db.main(["--source", str(src), "--out", str(out)]) == 0

    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    assert stat.S_IMODE(out.parent.stat().st_mode) == 0o700


def test_backup_output_is_narrowed_when_it_already_exists(tmp_path):
    """O_CREAT's mode applies only to a file it creates, so a backup an earlier
    run left world-readable must be narrowed, not inherited."""
    src = _db_with_rows(tmp_path / "live.sqlite3")
    out = tmp_path / "backups" / "db-20260918.sqlite3.gz"
    out.parent.mkdir(parents=True)
    out.write_bytes(b"stale")
    out.chmod(0o644)

    assert backup_db.main(["--source", str(src), "--out", str(out)]) == 0

    if os.name == "posix":
        assert stat.S_IMODE(out.stat().st_mode) == 0o600
    assert gzip.decompress(out.read_bytes()).startswith(b"SQLite format 3\x00")


def test_snapshot_refuses_a_missing_source(tmp_path):
    """`sqlite3.connect` CREATES a missing file: unguarded, a mistyped --source
    yields an empty, integrity-clean, entirely plausible backup."""
    missing = tmp_path / "nope.sqlite3"
    dest = tmp_path / "snapshot.sqlite3"

    with pytest.raises(FileNotFoundError):
        backup_db.snapshot(missing, dest)

    assert not missing.exists()
    assert not dest.exists()


def test_connect_source_opens_the_live_database_read_only(tmp_path):
    src = _db_with_rows(tmp_path / "live.sqlite3")

    conn = backup_db._connect_source(src)
    try:
        assert conn.execute("SELECT count(*) FROM t").fetchone()[0] == 3
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("INSERT INTO t (v) VALUES ('d')")
    finally:
        conn.close()


def test_backup_reports_an_unreadable_source_without_a_traceback(tmp_path, capsys):
    """Everything below main() raises; main() is the one place that turns a
    failure into an `error:` line and an exit code."""
    not_a_database = tmp_path / "live.sqlite3"
    not_a_database.write_bytes(b"this is not a database")
    out = tmp_path / "backup.sqlite3.gz"

    assert backup_db.main(["--source", str(not_a_database), "--out", str(out)]) == 1

    assert capsys.readouterr().err.splitlines()[-1].startswith("error: ")
    assert not out.exists()


def test_backup_refuses_a_missing_file(tmp_path, capsys):
    missing = tmp_path / "not-there.sqlite3"
    out = tmp_path / "backup.sqlite3.gz"

    assert backup_db.main(["--source", str(missing), "--out", str(out)]) == 1

    assert capsys.readouterr().err.startswith(f"error: no database file at {missing}")
    assert not out.exists()
