"""Move a compose-era Postgres database into the SQLite file.

ONE release only (SYSTEM.md §13 `postgres-to-sqlite`); delete with that row.

Two entry points:
- `import_if_needed(...)` — called by seeding.run_startup() at boot. Idempotent
  (a marker file records success), atomic (one transaction on the target),
  verified (row counts and a per-table content hash, source vs target).
- `python -m app.tools.migrate_from_postgres` — the same thing by hand.

The source is read by reflection (the legacy schema at its head); the target
is written through the app's own metadata, so every value passes through
app.models.types exactly as the app would write it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.types import TypeDecorator

from app.config import normalize_postgres_url, settings
from app.db import Base, make_engine, sqlite_path
import app.models  # noqa: F401  registers every table on Base.metadata

BACKEND_ROOT = Path(__file__).resolve().parents[2]
LEGACY_INI = BACKEND_ROOT / "legacy_postgres" / "alembic.ini"
NEW_INI = BACKEND_ROOT / "alembic.ini"
MARKER_NAME = ".migrated-from-postgres.json"
BATCH = 1000
# Tables whose emptiness means "this target has never held user data".
_USER_DATA_TABLES = ("jobs", "applications", "base_resumes", "kb_entities")

Log = Callable[[str], None]


class ExportError(RuntimeError):
    pass


def normalize_value(value):
    """One canonical form per value so a hash means the same on both sides:
    psycopg hands back dicts, aware datetimes and Decimals; SQLite hands back
    the same through app.models.types."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=UTC)
        return aware.astimezone(UTC).isoformat()
    if isinstance(value, Decimal):
        # Scale-free: Postgres returns an unscaled NUMERIC at whatever scale
        # the writer sent (120000 or 120000.00); SQLite stores it as REAL and
        # SQLAlchemy re-renders it at a fixed 10-digit scale. Same number,
        # different text. Strip trailing fractional zeros so the two agree;
        # any change in VALUE still mismatches.
        text = format(value, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=normalize_value)
    if isinstance(value, bytes):
        return value.hex()
    return value


def table_hash(rows: list[dict], column_names: list[str]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        line = json.dumps(
            [normalize_value(row[name]) for name in column_names],
            separators=(",", ":"),
            default=str,
        )
        digest.update(line.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _pk_names(table: sa.Table) -> list[str]:
    return [column.name for column in table.primary_key.columns]


def read_rows(conn: sa.Connection, table: sa.Table) -> list[dict]:
    # Sorted in Python by the normalized primary key: a text key sorts by
    # collation in Postgres and by bytes in SQLite, and the hash needs one order.
    rows = [dict(row._mapping) for row in conn.execute(sa.select(table))]
    keys = _pk_names(table)
    rows.sort(key=lambda row: tuple(str(normalize_value(row[key])) for key in keys))
    return rows


def _coerce_for_target(table: sa.Table, row: dict) -> dict:
    """Shape a reflected source row the way the app's types expect it. psycopg
    already hands back uuid.UUID and aware datetimes; a SQLite source (the
    unit tests) hands back 32-hex strings and naive datetimes. Hashing runs
    on the coerced row, so both sides are compared in one representation."""
    out = {}
    for column in table.columns:
        value = row[column.name]
        if value is not None:
            if isinstance(column.type, sa.Uuid) and isinstance(value, str):
                value = uuid.UUID(value)
            elif (
                isinstance(column.type, TypeDecorator)
                and isinstance(value, datetime)
                and value.tzinfo is None
            ):
                value = value.replace(tzinfo=UTC)
        out[column.name] = value
    return out


def copy_database(source_url: str, target_url: str, *, log: Log = print) -> dict[str, dict]:
    """Copy every table in dependency order, in ONE target transaction, then
    verify. Returns {table: {rows, source_hash, target_rows, target_hash, ok}}."""
    # Every Postgres URL reaching create_engine goes through here (app.config):
    # the bare scheme selects psycopg2, which this project does not install.
    source = sa.create_engine(normalize_postgres_url(source_url), future=True)
    target = make_engine(target_url)
    reflected = sa.MetaData()
    report: dict[str, dict] = {}
    try:
        with source.connect() as sconn, target.begin() as tconn:
            # Foreign keys are checked at COMMIT instead of per statement, so a
            # self-referential table (resume_versions.parent_version_id) copies
            # in any row order. Violations still fail the whole transaction.
            tconn.exec_driver_sql("PRAGMA defer_foreign_keys=ON")
            for table in Base.metadata.sorted_tables:
                src_table = sa.Table(table.name, reflected, autoload_with=sconn)
                columns = [column.name for column in table.columns]
                missing = [name for name in columns if name not in src_table.c]
                if missing:
                    raise ExportError(
                        f"{table.name}: source lacks {missing}; the source must be at the "
                        "legacy chain's head (run without --skip-source-upgrade)"
                    )
                rows = [_coerce_for_target(table, row) for row in read_rows(sconn, src_table)]
                for start in range(0, len(rows), BATCH):
                    chunk = rows[start:start + BATCH]
                    tconn.execute(
                        table.insert(), [{name: row[name] for name in columns} for row in chunk]
                    )
                report[table.name] = {"rows": len(rows), "source_hash": table_hash(rows, columns)}
                log(f"  {table.name}: {len(rows)} rows")
        with target.connect() as tconn:
            for table in Base.metadata.sorted_tables:
                columns = [column.name for column in table.columns]
                rows = read_rows(tconn, table)
                entry = report[table.name]
                entry["target_rows"] = len(rows)
                entry["target_hash"] = table_hash(rows, columns)
                entry["ok"] = (
                    entry["rows"] == entry["target_rows"]
                    and entry["source_hash"] == entry["target_hash"]
                )
    finally:
        source.dispose()
        target.dispose()
    return report


def upgrade_legacy_source(source_url: str) -> None:
    """Bring a compose-era database to the legacy chain's head. A user may have
    skipped releases; the chain still knows how to get there."""
    try:
        import psycopg  # noqa: F401
    except ModuleNotFoundError as exc:
        raise ExportError(
            "psycopg is not installed; install the legacy-postgres extra: "
            "pip install -e '.[legacy-postgres]'"
        ) from exc
    cfg = Config(str(LEGACY_INI))
    # ConfigParser interpolation: a bare `%` (a URL-encoded password) is
    # rejected at set time, so escape it. The legacy env reads the option
    # back raw and never writes it (Task 6 follow-up).
    cfg.set_main_option("sqlalchemy.url", normalize_postgres_url(source_url).replace("%", "%%"))
    command.upgrade(cfg, "head")


def create_target_schema(target_url: str) -> None:
    cfg = Config(str(NEW_INI))
    cfg.set_main_option("sqlalchemy.url", target_url.replace("%", "%%"))
    command.upgrade(cfg, "head")


def _source_has_data(source_url: str) -> bool | None:
    """True/False, or None when the source cannot be reached."""
    try:
        engine = sa.create_engine(source_url, future=True)
    except ModuleNotFoundError as exc:  # the postgresql dialect needs psycopg
        raise ExportError(
            "psycopg is not installed; install the legacy-postgres extra: "
            "pip install -e '.[legacy-postgres]'"
        ) from exc
    try:
        with engine.connect() as conn:
            if not sa.inspect(conn).has_table("alembic_version"):
                return False
            for name in _USER_DATA_TABLES:
                if sa.inspect(conn).has_table(name):
                    if conn.execute(sa.text(f"SELECT count(*) FROM {name}")).scalar():
                        return True
            return False
    except sa.exc.SQLAlchemyError:
        return None
    finally:
        engine.dispose()


def _target_is_empty(target_url: str) -> bool:
    engine = make_engine(target_url)
    try:
        with engine.connect() as conn:
            for name in _USER_DATA_TABLES:
                if conn.execute(sa.text(f"SELECT count(*) FROM {name}")).scalar():
                    return False
        return True
    finally:
        engine.dispose()


def import_if_needed(
    source_url: str,
    target_url: str,
    marker: Path,
    *,
    log: Log = print,
    upgrade_source: bool = True,
) -> str:
    """Boot-time entry point. Returns one of: already-imported, no-source,
    source-unreachable, source-empty, target-not-empty, imported. Raises
    ExportError only on a verification mismatch (the transaction has already
    rolled back; the target is left as it was)."""
    if marker.exists():
        return "already-imported"
    if not source_url:
        return "no-source"
    source_url = normalize_postgres_url(source_url)
    has_data = _source_has_data(source_url)
    if has_data is None:
        log("legacy Postgres source is unreachable; will retry at the next boot")
        return "source-unreachable"
    if not has_data:
        _write_marker(marker, {"outcome": "source-empty"})
        return "source-empty"
    if not _target_is_empty(target_url):
        log("SQLite file already holds data and no import marker exists; leaving both alone")
        return "target-not-empty"
    if upgrade_source:
        log("bringing the Postgres source to the legacy chain's head")
        upgrade_legacy_source(source_url)
    log("importing the Postgres database into the SQLite file")
    report = copy_database(source_url, target_url, log=log)
    bad = sorted(name for name, entry in report.items() if not entry["ok"])
    if bad:
        raise ExportError(f"import verification failed for {bad}; nothing was kept")
    _write_marker(marker, {"outcome": "imported", "tables": report})
    total = sum(entry["rows"] for entry in report.values())
    log(f"imported {total} rows from Postgres; the pgdata volume is no longer read")
    return "imported"


def _write_marker(marker: Path, payload: dict) -> None:
    marker.parent.mkdir(parents=True, exist_ok=True)
    payload = {"at": datetime.now(UTC).isoformat(), **payload}
    marker.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--source",
        default=os.environ.get("LEGACY_DATABASE_URL"),
        help="postgresql://… (default: $LEGACY_DATABASE_URL)",
    )
    parser.add_argument(
        "--target",
        default=settings.database_url,
        help="sqlite:///… (default: the app's database_url)",
    )
    parser.add_argument(
        "--replace", action="store_true", help="move a non-empty target aside first"
    )
    parser.add_argument(
        "--skip-source-upgrade",
        action="store_true",
        help="do not run the legacy chain on the source",
    )
    args = parser.parse_args(argv)
    if not args.source:
        parser.error("--source or LEGACY_DATABASE_URL is required")
    path = sqlite_path(args.target)
    if path is None:
        parser.error("--target must be a sqlite:/// file URL")

    if path.exists() and path.stat().st_size > 0:
        if not args.replace:
            print(f"refusing: {path} exists and is not empty (pass --replace to move it aside)")
            return 2
        aside = path.with_name(f"{path.name}.replaced-{datetime.now(UTC):%Y%m%dT%H%M%S}")
        path.rename(aside)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{path}{suffix}")
            if sidecar.exists():
                sidecar.unlink()
        print(f"moved {path} -> {aside}")

    try:
        if not args.skip_source_upgrade:
            print("upgrading the source through the legacy migration chain")
            upgrade_legacy_source(args.source)
        print(f"creating the SQLite schema at {path}")
        create_target_schema(args.target)
        print("copying tables")
        report = copy_database(normalize_postgres_url(args.source), args.target)
    except ExportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    width = max(len(name) for name in report)
    for name, entry in report.items():
        flag = "ok" if entry["ok"] else "MISMATCH"
        print(f"{name:<{width}}  {entry['rows']:>7} -> {entry['target_rows']:>7}  {flag}")
    if all(entry["ok"] for entry in report.values()):
        _write_marker(path.parent / MARKER_NAME, {"outcome": "imported", "tables": report})
        print("verified: every table matches by count and content hash")
        return 0
    print("verification FAILED; the target was left in place for inspection", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
