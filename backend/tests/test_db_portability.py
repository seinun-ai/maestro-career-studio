"""Pins SYSTEM.md §6 {#inv-single-dialect}: column types come from
app/models/types.py and nothing under app/ imports a SQLAlchemy dialect.

SQLite is the only runtime database. A dialect import anywhere else is how a
Postgres-only type or DDL option creeps back in and breaks the next fresh
install at boot.
"""
import re
from pathlib import Path

import sqlalchemy as sa

from app.db import Base
import app.models  # noqa: F401  registers every table
from app.models.types import UTCDateTime

APP = Path(__file__).resolve().parents[1] / "app"
TYPES_MODULE = APP / "models" / "types.py"
DIALECT_IMPORT = re.compile(r"^\s*(from|import)\s+sqlalchemy\.dialects", re.M)
POSTGRES_ONLY_DDL = re.compile(r"::jsonb|postgresql_where|postgresql_using|postgresql_ops")


def test_no_dialect_imports_outside_types_module():
    offenders = sorted(
        str(p.relative_to(APP))
        for p in APP.rglob("*.py")
        if p != TYPES_MODULE and DIALECT_IMPORT.search(p.read_text(encoding="utf-8"))
    )
    assert offenders == []


def test_no_postgres_only_ddl_in_models():
    offenders = sorted(
        p.name
        for p in (APP / "models").glob("*.py")
        if POSTGRES_ONLY_DDL.search(p.read_text(encoding="utf-8"))
    )
    assert offenders == []


def test_every_datetime_column_is_utcdatetime():
    # A bare sa.DateTime column would come back naive from SQLite and compare
    # unequal (or raise) against the aware datetimes every writer produces.
    bare = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.sorted_tables
        for column in table.columns
        if isinstance(column.type, sa.DateTime)
    ]
    assert bare == []
    assert any(
        isinstance(column.type, UTCDateTime)
        for table in Base.metadata.sorted_tables
        for column in table.columns
    )
