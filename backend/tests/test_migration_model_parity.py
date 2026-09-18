"""Catch a model shipped without its migration.

The suite migrates its file through alembic and only ever DELETEs, so a new
column on a model would otherwise surface as "no such column" in unrelated
tests rather than as a clear failure here.
"""

import os

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app.db import Base, make_engine
import app.models  # noqa: F401  import side effect: registers every table

# Alembic's empty-string false positives: the stored default is literally ''
# and so is the model's; the comparison quotes them differently. Nothing else
# may appear in a compare_server_default pass.
KNOWN_EMPTY_STRING_DEFAULTS = {
    ("kb_documents", "text_content"),
    ("kb_port_log", "ported_text"),
    ("kb_profile", "summary"),
    ("kb_profile", "notes"),
}


def _diff(compare_server_default: bool) -> list:
    engine = make_engine(os.environ["TEST_DATABASE_URL"])
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(
                conn,
                opts={"compare_type": True, "compare_server_default": compare_server_default},
            )
            raw = compare_metadata(ctx, Base.metadata)
    finally:
        engine.dispose()
    # Table-level entries are bare tuples; a column's modify_* entries
    # (modify_default, modify_nullable, modify_type) arrive grouped in a LIST
    # per column (alembic 1.18). Flatten so every entry starts with its verb.
    flat: list = []
    for entry in raw:
        flat.extend(entry if isinstance(entry, list) else [entry])
    return flat


def _owned(entry) -> bool:
    table = getattr(entry[1] if len(entry) > 1 else None, "name", None) or ""
    return not str(table).startswith("alembic_")


def test_models_match_migrations(db_session):
    unexpected = [d for d in _diff(compare_server_default=False) if _owned(d)]
    assert not unexpected, (
        "models and migrations disagree — generate a revision "
        f"(uuid.uuid4().hex[:12] per SYSTEM.md §12):\n{unexpected}"
    )


def test_server_defaults_match_migrations(db_session):
    # `alembic check` ignores server defaults; this pass does not. A default
    # that drifts between the baseline and the models (the Task 6 `is_default`
    # bug was exactly that shape) fails here.
    unexpected = []
    for entry in _diff(compare_server_default=True):
        if not _owned(entry):
            continue
        if entry[0] == "modify_default":
            # ("modify_default", schema, table_name, column_name, {existing_*},
            #  existing_default, new_default)
            key = (str(entry[2]), str(entry[3]))
            if key in KNOWN_EMPTY_STRING_DEFAULTS:
                continue
        unexpected.append(entry)
    assert not unexpected, f"server defaults disagree with the baseline:\n{unexpected}"
