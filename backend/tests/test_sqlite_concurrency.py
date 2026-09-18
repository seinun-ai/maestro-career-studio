"""A second writer waits for the first (busy_timeout), it does not fail.

The design (§3.1) buys concurrency with two pragmas rather than a lock
discipline: `busy_timeout=30000` makes a blocked WRITER wait, and WAL keeps
READERS out of the queue entirely. Both tests hold a real write lock open for
two seconds on one thread and observe a second connection from the same engine.
"""
import threading
import time

import sqlalchemy as sa

from app.db import make_engine

HOLD_SECONDS = 2.0


def _engine_with_table(tmp_path, name):
    engine = make_engine(f"sqlite:///{tmp_path / name}")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    return engine


def test_second_writer_waits_instead_of_failing(tmp_path):
    engine = _engine_with_table(tmp_path, "c.sqlite3")
    try:
        errors: list[Exception] = []
        first_holds_lock = threading.Event()

        def first_writer():
            with engine.begin() as conn:
                conn.exec_driver_sql("INSERT INTO t (v) VALUES ('a')")  # takes the write lock
                first_holds_lock.set()
                time.sleep(HOLD_SECONDS)  # hold it across the second writer's attempt

        def second_writer():
            first_holds_lock.wait(5)
            try:
                with engine.begin() as conn:
                    conn.exec_driver_sql("INSERT INTO t (v) VALUES ('b')")
            except Exception as exc:  # noqa: BLE001  the assertion below reports it
                errors.append(exc)

        threads = [threading.Thread(target=first_writer), threading.Thread(target=second_writer)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)

        assert errors == []
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT count(*) FROM t")).scalar() == 2
    finally:
        engine.dispose()


def test_readers_never_block_behind_a_writer(tmp_path):
    """WAL's whole point: a reader sees the last committed snapshot at once."""
    engine = _engine_with_table(tmp_path, "r.sqlite3")
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("INSERT INTO t (v) VALUES ('committed')")

        read_count: list[int] = []
        read_elapsed: list[float] = []
        errors: list[Exception] = []
        first_holds_lock = threading.Event()

        def first_writer():
            with engine.begin() as conn:
                conn.exec_driver_sql("INSERT INTO t (v) VALUES ('uncommitted')")
                first_holds_lock.set()
                time.sleep(HOLD_SECONDS)

        def reader():
            first_holds_lock.wait(5)
            started = time.monotonic()
            try:
                with engine.connect() as conn:
                    read_count.append(conn.execute(sa.text("SELECT count(*) FROM t")).scalar())
            except Exception as exc:  # noqa: BLE001  the assertion below reports it
                errors.append(exc)
            read_elapsed.append(time.monotonic() - started)

        threads = [threading.Thread(target=first_writer), threading.Thread(target=reader)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)

        assert errors == []
        # Returned while the writer still held the lock, on the pre-write snapshot.
        assert read_elapsed[0] < 1.0
        assert read_count == [1]
    finally:
        engine.dispose()
