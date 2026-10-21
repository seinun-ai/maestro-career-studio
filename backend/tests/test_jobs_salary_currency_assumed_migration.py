"""Migration ff9591f140f7: jobs.salary_currency_assumed, backfilled where capture filled the currency in."""

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import uuid

from alembic import command
from alembic.config import Config

BEFORE = "2d3de2d60a4c"
REVISION = "ff9591f140f7"

# (extracted_json, salary_min, salary_currency) -> salary_currency_assumed
ROWS = [
    ({"salary_currency": None}, 90000, "USD", 1),  # the fallback filled it in
    ({}, 90000, "GBP", 1),
    (None, 90000, "USD", 1),
    ({"salary_currency": "EUR"}, 90000, "EUR", 0),  # the posting said it
    ({"salary_currency": None}, None, None, 0),  # no pay, no currency
]


def _config(path: Path) -> Config:
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    return cfg


def _columns(db) -> set[str]:
    return {row[1] for row in db.execute("PRAGMA table_info(jobs)")}


def test_backfills_the_flag_and_round_trips(tmp_path):
    path = tmp_path / "assumed.sqlite3"
    cfg = _config(path)
    command.upgrade(cfg, BEFORE)
    with closing(sqlite3.connect(path)) as db:
        for i, (extracted, amount, currency, _) in enumerate(ROWS):
            db.execute(
                "INSERT INTO jobs (id, raw_text, raw_text_hash, extracted_json, salary_min,"
                " salary_currency) VALUES (?, ?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, f"jd {i}", f"hash-{i}",
                 None if extracted is None else json.dumps(extracted), amount, currency),
            )
        db.commit()

    command.upgrade(cfg, REVISION)
    with closing(sqlite3.connect(path)) as db:
        for i, (*_, assumed) in enumerate(ROWS):
            got = db.execute(
                "SELECT salary_currency_assumed FROM jobs WHERE raw_text_hash = ?", (f"hash-{i}",)
            ).fetchone()
            assert got == (assumed,), (i, got)
        db.execute("INSERT INTO jobs (id, raw_text, raw_text_hash) VALUES (?, 'new', 'hash-new')",
                   (uuid.uuid4().hex,))
        assert db.execute(
            "SELECT salary_currency_assumed FROM jobs WHERE raw_text_hash = 'hash-new'"
        ).fetchone() == (0,)
        db.commit()

    command.downgrade(cfg, BEFORE)
    with closing(sqlite3.connect(path)) as db:
        assert "salary_currency_assumed" not in _columns(db)
        assert db.execute("SELECT count(*) FROM jobs").fetchone() == (len(ROWS) + 1,)

    command.upgrade(cfg, "head")
    with closing(sqlite3.connect(path)) as db:
        assert "salary_currency_assumed" in _columns(db)
