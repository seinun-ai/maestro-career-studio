"""Catch a model shipped without its migration.

Nothing enforced this before: the suite creates no schema (conftest connects to
an existing DB and only DELETEs), so a new column on a model surfaces as a
confusing UndefinedColumn in unrelated tests rather than as a clear failure
here.
"""

import os

from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from sqlalchemy import create_engine

from app.db import Base
import app.models  # noqa: F401 — import side effect: registers every table


def test_models_match_migrations(db_session):
    url = os.environ["TEST_DATABASE_URL"]
    engine = create_engine(url, future=True)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)

    # Ignore anything the app deliberately does not own or manage here.
    def owned(entry) -> bool:
        table = getattr(entry[1] if len(entry) > 1 else None, "name", None) or ""
        return not str(table).startswith("alembic_")

    unexpected = [d for d in diff if owned(d)]
    assert not unexpected, (
        "models and migrations disagree — generate a revision "
        f"(uuid.uuid4().hex[:12] per SYSTEM.md §9):\n{unexpected}"
    )
