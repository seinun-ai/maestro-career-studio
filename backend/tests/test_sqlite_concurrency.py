"""A second writer waits for the first (busy_timeout), it does not fail.

The design (§3.1) buys concurrency with two pragmas rather than a lock
discipline: `busy_timeout=30000` makes a blocked WRITER wait, and WAL keeps
READERS out of the queue entirely. Both tests hold a real write lock open on
one thread and observe a second connection from the same engine.

Every thread body reports through `errors`, and the main thread asserts the
lock was actually taken: a first writer that dies before `INSERT` would
otherwise leave the observer with nothing to wait behind and pass the test
for the wrong reason.
"""
import threading
import time

import pytest
import sqlalchemy as sa

from app.db import make_engine

HOLD_SECONDS = 1.0


@pytest.fixture
def engine(tmp_path):
    """One engine per test, pinned to WAL whatever SQLITE_JOURNAL_MODE says.

    The journal mode is the thing under test, so it is asserted here rather
    than inherited from the environment — under DELETE the reader test below
    would be asserting the opposite of WAL's contract.
    """
    engine = make_engine(f"sqlite:///{tmp_path / 'c.sqlite3'}", journal_mode="WAL")
    try:
        with engine.begin() as conn:
            assert conn.exec_driver_sql("PRAGMA journal_mode").scalar().lower() == "wal"
            conn.exec_driver_sql("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        yield engine
    finally:
        engine.dispose()


def _run(threads, first_holds_lock, errors):
    """Start both threads, prove the lock was taken, and join them cleanly."""
    for thread in threads:
        thread.start()
    try:
        assert first_holds_lock.wait(5), "the first writer never took the write lock"
    finally:
        for thread in threads:
            thread.join(30)
    for thread in threads:
        assert not thread.is_alive(), f"{thread.name} did not finish within 30 s"
    assert errors == []


def test_second_writer_waits_instead_of_failing(engine):
    errors: list[Exception] = []
    first_holds_lock = threading.Event()

    def first_writer():
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql("INSERT INTO t (v) VALUES ('a')")  # takes the write lock
                first_holds_lock.set()
                time.sleep(HOLD_SECONDS)  # hold it across the second writer's attempt
        except Exception as exc:  # noqa: BLE001  the assertion below reports it
            errors.append(exc)
            # Deliberately NOT setting the event here: a writer that died
            # before its INSERT never took the lock, and `_run`'s wait says so.

    def second_writer():
        first_holds_lock.wait(5)
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql("INSERT INTO t (v) VALUES ('b')")
        except Exception as exc:  # noqa: BLE001  the assertion below reports it
            errors.append(exc)

    _run(
        [threading.Thread(target=first_writer), threading.Thread(target=second_writer)],
        first_holds_lock,
        errors,
    )

    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM t")).scalar() == 2


def test_readers_never_block_behind_a_writer(engine):
    """WAL's whole point: a reader sees the last committed snapshot at once."""
    with engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO t (v) VALUES ('committed')")

    read_count: list[int] = []
    read_elapsed: list[float] = []
    errors: list[Exception] = []
    first_holds_lock = threading.Event()
    writer_may_finish = threading.Event()

    def first_writer():
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql("INSERT INTO t (v) VALUES ('uncommitted')")
                first_holds_lock.set()
                # Hold the lock until the reader has answered (or the cap
                # expires), so the read provably races a held write lock.
                writer_may_finish.wait(HOLD_SECONDS)
        except Exception as exc:  # noqa: BLE001  the assertion below reports it
            errors.append(exc)  # see the note in the test above: no set() here

    def reader():
        first_holds_lock.wait(5)
        started = time.monotonic()
        try:
            with engine.connect() as conn:
                read_count.append(conn.execute(sa.text("SELECT count(*) FROM t")).scalar())
        except Exception as exc:  # noqa: BLE001  the assertion below reports it
            errors.append(exc)
        read_elapsed.append(time.monotonic() - started)
        writer_may_finish.set()

    _run(
        [threading.Thread(target=first_writer), threading.Thread(target=reader)],
        first_holds_lock,
        errors,
    )

    # Answered while the writer still held the lock, on the pre-write snapshot.
    # A blocked reader could only be released by the writer, which is itself
    # waiting on the reader, so it would spend the whole HOLD_SECONDS cap here.
    assert read_elapsed[0] < HOLD_SECONDS / 2
    assert read_count == [1]
