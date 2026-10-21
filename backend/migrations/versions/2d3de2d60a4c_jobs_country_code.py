"""jobs.country_code, and one spelling per work mode and level

`country_code` is the job's country as one ISO 3166-1 alpha-2 code beside `country`, which keeps
what the posting said. The backfill uses `services/countries.for_job` (the country field, else the
location line): the 249-country list is data, read through its one parser, and that module imports
nothing from the app. Every other rule here is a frozen inline copy, because a revision never
imports app code: `work_mode_key` and `level_key` copy `schemas/job_extraction.py`, and
tests/test_jobs_country_code_migration.py keeps the copies equal.

Stored work modes and levels are re-spelled to their keys ("Onsite" -> on_site, "Sr." -> senior).
Every reader words the keys (knockout, the web app's enum labels, the analytics bars), and the
original text stays in `extracted_json`. Downgrade drops the column and leaves the keys: each was a
spelling of the value it replaced.

Revision ID: 2d3de2d60a4c
Revises: 349b494103b9
"""
import re
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.services import countries


revision: str = "2d3de2d60a4c"
down_revision: Union[str, Sequence[str], None] = "349b494103b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _value_words(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "n/a", "unknown"}:
        return None
    return " ".join(re.sub(r"[^0-9a-z]+", " ", text.casefold()).split()) or None


_ON_SITE = {"onsite", "inoffice", "office", "officebased", "inperson", "onpremises", "onpremise", "onprem"}
_REMOTE = {"remote", "fullyremote", "remotefirst", "workfromhome", "wfh"}
_MODE_WORDS = (
    ("on_site", re.compile(r"\b(?:on ?site|in office|office based|in person|on prem(?:ise|ises)?)\b")),
    ("hybrid", re.compile(r"\bhybrid\b")),
    ("remote", re.compile(r"\b(?:remote|work from home|wfh)\b")),
)
_LEVELS = {
    "intern": "intern", "internship": "intern",
    "entry": "entry", "entry level": "entry", "junior": "entry", "jr": "entry",
    "graduate": "entry", "new grad": "entry", "new graduate": "entry",
    "mid": "mid", "mid level": "mid", "midlevel": "mid", "intermediate": "mid",
    "senior": "senior", "sr": "senior", "senior level": "senior",
    "lead": "lead", "staff": "lead", "principal": "lead",
}


def work_mode_key(value: Any) -> str | None:
    words = _value_words(value)
    if words is None:
        return None
    compact = words.replace(" ", "")
    if compact in _ON_SITE:
        return "on_site"
    if compact == "hybrid":
        return "hybrid"
    if compact in _REMOTE:
        return "remote"
    named = [key for key, pattern in _MODE_WORDS if pattern.search(words)]
    if "hybrid" in named:
        return "hybrid"
    if len(named) == 1:
        return named[0]
    return words.replace(" ", "_")


def level_key(value: Any) -> str | None:
    words = _value_words(value)
    if words is None:
        return None
    return _LEVELS.get(words) or words.replace(" ", "_")


def upgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("country_code", sa.String(length=2), nullable=True))

    # `id` untyped: the stored text is matched back as it was read, whatever its shape.
    jobs = sa.table(
        "jobs",
        sa.column("id"),
        sa.column("country", sa.Text()),
        sa.column("location", sa.Text()),
        sa.column("location_raw", sa.Text()),
        sa.column("work_mode", sa.Text()),
        sa.column("level", sa.Text()),
        sa.column("country_code", sa.String(length=2)),
    )
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(jobs.c.id, jobs.c.country, jobs.c.location, jobs.c.location_raw,
                  jobs.c.work_mode, jobs.c.level)
    ).all()
    for row in rows:
        values = {
            "country_code": countries.for_job(row.country, row.location or row.location_raw),
            "work_mode": work_mode_key(row.work_mode),
            "level": level_key(row.level),
        }
        changed = {
            key: value for key, value in values.items()
            if value != (None if key == "country_code" else getattr(row, key))
        }
        if changed:
            bind.execute(jobs.update().where(jobs.c.id == row.id).values(**changed))


def downgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_column("country_code")
