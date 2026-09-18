import gzip
import sqlite3

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


def test_backup_refuses_a_missing_file(tmp_path, capsys):
    missing = tmp_path / "not-there.sqlite3"
    out = tmp_path / "backup.sqlite3.gz"

    assert backup_db.main(["--source", str(missing), "--out", str(out)]) == 1

    assert capsys.readouterr().err.startswith(f"error: no database file at {missing}")
    assert not out.exists()
