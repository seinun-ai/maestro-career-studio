"""The ONE place a column type is chosen. SYSTEM.md §6 {#inv-single-dialect}.

SQLite is the only runtime database. These names exist so the port to it
happened in one file, and so nothing under app/ ever imports a dialect again.
"""
from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.types import TypeDecorator

# A JSON document: stored as text by SQLite, loaded as dict/list. Every query in
# the app treats these columns as opaque (load and store), which is what made
# the port from JSONB a rename.
JSONDoc = sa.JSON

# uuid.UUID in Python, CHAR(32) hex on disk. Call it exactly as the old dialect
# type was called: UUIDType(as_uuid=True).
UUIDType = sa.Uuid


class UTCDateTime(TypeDecorator):
    """Timezone-aware in Python, naive UTC on disk.

    SQLite has no timezone-aware column type. Every writer in the app uses
    datetime.now(UTC), so a NAIVE bind is a bug, not a convention, and it
    raises here rather than storing an ambiguous instant. Values read back
    (including CURRENT_TIMESTAMP server defaults, which SQLite emits in UTC)
    are stamped UTC so comparisons against datetime.now(UTC) stay legal.
    """

    impl = sa.DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError(f"UTCDateTime expects datetime, got {type(value).__name__}")
        if value.tzinfo is None:
            raise ValueError(
                "naive datetime bound to a UTCDateTime column; use datetime.now(UTC)"
            )
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
