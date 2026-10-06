"""Row and file helpers the job bundle and the profile bundle share.

Both bundles list their tables parents-first, write them in that order and delete in reverse; both
decode, diff and export rows the same way. They differ only in which rows belong to the bundle and
how one row is encoded, so those arrive as arguments. Nothing here echoes a row or file value.
"""

from collections.abc import Callable, Iterable
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.db import Base

LATEX_LEFTOVERS = (".aux", ".log", ".out")  # rebuilt by every compile, never worth sending
INT64_MIN, INT64_MAX = -(2**63), 2**63 - 1  # what a database integer column can hold


def pk_keys(model: type[Base]) -> list[str]:
    mapper = inspect(model)
    return [mapper.get_property_by_column(column).key for column in mapper.primary_key]


def row_pk(spec: Any, row: dict) -> tuple:
    return tuple(row[key] for key in pk_keys(spec.model))


def obj_pk(spec: Any, obj: Base) -> tuple:
    return tuple(getattr(obj, key) for key in pk_keys(spec.model))


def decoded_size(entry: dict) -> int:
    encoded = entry["b64"]
    return len(encoded) // 4 * 3 - encoded.count("=")


def encodable(value: str) -> bool:
    """False for a string with a lone surrogate: it cannot be written, and the error it raises
    carries the whole string."""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def fits_int64(value: int) -> bool:
    return INT64_MIN <= value <= INT64_MAX


def decode_rows(bundle: dict, tables: dict[str, Any], decode_row: Callable) -> dict[str, list[dict]]:
    """Each bundle item decoded under its table; ``tables`` maps a table name to its spec."""
    rows: dict[str, list[dict]] = {name: [] for name in tables}
    for item in bundle["rows"]:
        spec = tables.get(item["table"]) if isinstance(item, dict) else None
        if spec is None:
            raise ValueError("unknown table in bundle")
        rows[spec.name].append(decode_row(spec, item.get("row")))
    return rows


def missing(tables: Iterable, existing: dict, incoming: dict[str, list[dict]]) -> dict[str, list]:
    """What is here but not in the bundle, per table."""
    doomed: dict[str, list] = {}
    for spec in tables:
        keep = {row_pk(spec, row) for row in incoming[spec.name]}
        doomed[spec.name] = [obj for pk, obj in existing[spec.name].items() if pk not in keep]
    return doomed


def delete_rows(db: Session, tables: Iterable, doomed: dict[str, list]) -> None:
    """ORM deletes, children before parents, one flush per table: the flush hook stamps the job and
    the foreign keys never cascade into a row this call also deletes."""
    for spec in reversed(list(tables)):
        for obj in doomed[spec.name]:
            db.delete(obj)
        db.flush()


def export_rows(db: Session, tables: Iterable, where: Callable, export_row: Callable) -> list[dict]:
    """Every table's rows in primary-key order; ``where(spec)`` is the list of clauses that pick
    the bundle's rows."""
    rows = []
    for spec in tables:
        keys = [getattr(spec.model, key) for key in pk_keys(spec.model)]
        query = select(spec.model).where(*where(spec)).order_by(*keys)
        rows.extend(export_row(spec, obj) for obj in db.scalars(query))
    return rows
