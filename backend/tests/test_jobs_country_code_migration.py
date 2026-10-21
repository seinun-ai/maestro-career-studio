"""Migration 2d3de2d60a4c: jobs.country_code, backfilled, and one spelling per work mode and level."""

from contextlib import closing
from pathlib import Path
import sqlite3
import uuid

import pytest
from alembic import command
from alembic.config import Config

from app.schemas.job_extraction import level_key, work_mode_key

BEFORE = "349b494103b9"
REVISION = "2d3de2d60a4c"

# (country, location, work_mode, level) as an older copy stored them -> (country_code, work_mode, level).
ROWS = [
    (("United States", None, "Onsite", "Senior"), ("US", "on_site", "senior")),
    ((None, "Toronto, ON, Canada", "hybrid ", "Sr."), ("CA", "hybrid", "senior")),
    (("Remote", "London, UK", "REMOTE", "junior"), ("GB", "remote", "entry")),
    ((None, "San Francisco, CA", "Field-based", "Director"), (None, "field_based", "director")),
    ((None, None, None, None), (None, None, None)),
]


def _config(path: Path) -> Config:
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    return cfg


def _columns(db) -> set[str]:
    return {row[1] for row in db.execute("PRAGMA table_info(jobs)")}


def test_backfills_country_code_and_one_spelling_then_round_trips(tmp_path):
    path = tmp_path / "country_code.sqlite3"
    cfg = _config(path)
    command.upgrade(cfg, BEFORE)
    with closing(sqlite3.connect(path)) as db:
        for i, ((country, location, mode, level), _) in enumerate(ROWS):
            db.execute(
                "INSERT INTO jobs (id, raw_text, raw_text_hash, country, location, location_raw,"
                " work_mode, level) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, f"jd {i}", f"hash-{i}", country, location, location, mode, level),
            )
        db.commit()

    command.upgrade(cfg, REVISION)
    with closing(sqlite3.connect(path)) as db:
        assert "country_code" in _columns(db)
        for i, ((country, location, _, _), expected) in enumerate(ROWS):
            row = db.execute(
                "SELECT country_code, work_mode, level, country, location FROM jobs"
                " WHERE raw_text_hash = ?", (f"hash-{i}",),
            ).fetchone()
            assert row[:3] == expected, row
            assert row[3:] == (country, location)  # what the posting said stays as written

    # Down: the column goes; the re-spelled values stay (each was a variant of the same value).
    command.downgrade(cfg, BEFORE)
    with closing(sqlite3.connect(path)) as db:
        assert "country_code" not in _columns(db)
        assert db.execute("SELECT work_mode FROM jobs WHERE raw_text_hash = 'hash-0'").fetchone() == (
            "on_site",
        )

    command.upgrade(cfg, "head")
    with closing(sqlite3.connect(path)) as db:
        assert db.execute(
            "SELECT country_code FROM jobs WHERE raw_text_hash = 'hash-1'"
        ).fetchone() == ("CA",)


@pytest.mark.parametrize("value", [
    "Onsite", "On-site", "on site", "In office", "in-person", "Hybrid", "hybrid (2 days in office)",
    "Remote", "Remote (US)", "work from home", "Remote or on-site", "Field-based", "on_site", "",
    "unknown", None,
])
def test_the_frozen_work_mode_copy_matches_the_schema(value):
    module = __import__(f"migrations.versions.{REVISION}_jobs_country_code", fromlist=["work_mode_key"])
    assert module.work_mode_key(value) == work_mode_key(value)


@pytest.mark.parametrize("value", [
    "Senior", "Sr.", "Junior", "Entry-level", "New grad", "Mid-level", "Intermediate", "Internship",
    "Staff", "Principal", "Lead", "Director", "Mid-Senior level", "", "unknown", None,
])
def test_the_frozen_level_copy_matches_the_schema(value):
    module = __import__(f"migrations.versions.{REVISION}_jobs_country_code", fromlist=["level_key"])
    assert module.level_key(value) == level_key(value)
