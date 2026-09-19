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
INIT_MODULE = APP / "models" / "__init__.py"
DIALECT_IMPORT = re.compile(r"^\s*(from|import)\s+sqlalchemy\.dialects", re.M)
POSTGRES_ONLY_DDL = re.compile(r"::jsonb|postgresql_[a-z_]+")


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


def test_every_model_module_is_registered():
    # Base.metadata only knows a table once its module is imported. A model
    # left out of app/models/__init__.py is invisible to alembic and to the
    # test below (sorted_tables raises on a foreign key to an absent table).
    registry = INIT_MODULE.read_text(encoding="utf-8")
    missing = sorted(
        p.stem
        for p in (APP / "models").glob("*.py")
        if p.stem not in {"__init__", "types"}
        and f"from app.models.{p.stem} import" not in registry
    )
    assert missing == []


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


def test_boolean_server_defaults_are_expressions_not_strings():
    # SQLite has no boolean type. server_default="false" is stored as the TEXT
    # 'false', which SQLAlchemy reads back truthy while `IS 1` never matches;
    # expression.false() compiles to DEFAULT 0 and round-trips as False.
    string_defaults = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.sorted_tables
        for column in table.columns
        if isinstance(column.type, sa.Boolean)
        and column.server_default is not None
        and isinstance(getattr(column.server_default, "arg", None), str)
    ]
    assert string_defaults == []


def test_every_server_default_timestamp_also_has_a_python_default():
    # SQLite's CURRENT_TIMESTAMP writes "YYYY-MM-DD HH:MM:SS" while the ORM
    # binds "YYYY-MM-DD HH:MM:SS.ffffff"; the two shapes compare as strings,
    # so rows written within one second tie (or misorder) against each other.
    # One writer, the app, means one on-disk format: every UTCDateTime column
    # with a server_default (kept for DDL parity) also carries utcnow. The
    # default has to be PYTHON-side (is_callable) — default=func.now() is a SQL
    # expression too, so it writes the same 19-char form and would slip past a
    # bare `is not None`.
    missing = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.sorted_tables
        for column in table.columns
        if isinstance(column.type, UTCDateTime)
        and column.server_default is not None
        and (column.default is None or not column.default.is_callable)
    ]
    assert missing == []


def test_every_onupdate_is_python_side():
    # Same reason as above for the update path: onupdate=func.now() would put
    # a second-precision string on a row the app otherwise timestamps itself.
    # Read SQLAlchemy's own is_callable (the flag it sets when it wrapped a
    # callable, and the same one the rule above uses) rather than re-deriving it
    # with callable() over .arg, which not every default carries.
    sql_side = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.sorted_tables
        for column in table.columns
        if column.onupdate is not None and not column.onupdate.is_callable
    ]
    assert sql_side == []
