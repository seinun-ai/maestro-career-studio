"""Catch a model shipped without its migration.

The suite migrates its file through alembic and only ever DELETEs, so a new
column on a model would otherwise surface as "no such column" in unrelated
tests rather than as a clear failure here.
"""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app.db import Base
import app.models  # noqa: F401  import side effect: registers every table

# Alembic's empty-string false positives: the stored default is literally ''
# and so is the model's; the comparison quotes them differently ("('')" from
# the DB, "" from the model). Only that exact pair is swallowed, and only on
# these columns — any other default on them is reported.
KNOWN_EMPTY_STRING_DEFAULTS = {
    ("kb_documents", "text_content"),
    ("kb_port_log", "ported_text"),
    ("kb_profile", "summary"),
    ("kb_profile", "notes"),
}


def _diff(engine, compare_server_default: bool) -> list:
    with engine.connect() as conn:
        ctx = MigrationContext.configure(
            conn,
            opts={"compare_type": True, "compare_server_default": compare_server_default},
        )
        raw = compare_metadata(ctx, Base.metadata)
    # Table-level entries are bare tuples; a column's modify_* entries
    # (modify_default, modify_nullable, modify_type) arrive grouped in a LIST
    # per column (alembic 1.18). Flatten so every entry starts with its verb.
    flat: list = []
    for entry in raw:
        flat.extend(entry if isinstance(entry, list) else [entry])
    return flat


def _owned(entry) -> bool:
    # Discriminates table-level entries only, (verb, Table, ...); a
    # column-level entry carries the schema, None, in slot 1 and is owned.
    table = getattr(entry[1] if len(entry) > 1 else None, "name", None) or ""
    return not str(table).startswith("alembic_")


def _rendered(default):
    # DefaultClause.arg is a TextClause on the reflected (DB) side and a plain
    # str or TextClause on the model side; either way, the SQL text. None when
    # that side has no default at all.
    if default is None:
        return None
    return getattr(default.arg, "text", default.arg)


def _is_empty_string_false_positive(entry) -> bool:
    # ("modify_default", schema, table_name, column_name, {existing_*},
    #  existing_default = the DB's, new_default = the model's)
    if entry[0] != "modify_default":
        return False
    if (str(entry[2]), str(entry[3])) not in KNOWN_EMPTY_STRING_DEFAULTS:
        return False
    db_side, model_side = _rendered(entry[5]), _rendered(entry[6])
    return str(db_side).strip("()") == "''" and model_side == ""


def test_models_match_migrations(_test_engine):
    unexpected = [d for d in _diff(_test_engine, compare_server_default=False) if _owned(d)]
    assert not unexpected, (
        "models and migrations disagree — generate a revision "
        f"(uuid.uuid4().hex[:12] per SYSTEM.md §12):\n{unexpected}"
    )


def test_server_defaults_match_migrations(_test_engine):
    # `alembic check` ignores server defaults; this pass does not. A default
    # that drifts between the baseline and the models (the Task 6 `is_default`
    # bug was exactly that shape) fails here.
    unexpected = [
        d
        for d in _diff(_test_engine, compare_server_default=True)
        if _owned(d) and not _is_empty_string_false_positive(d)
    ]
    assert not unexpected, f"server defaults disagree with the baseline:\n{unexpected}"
