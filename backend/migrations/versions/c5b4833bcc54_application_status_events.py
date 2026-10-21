"""application_status_events: a dated log of status changes

One row per change of `applications.status`: from, to, when (`at`), who said so (`source`), and
`backfilled`. Written by `services/application_status.set_status` from here on.

Backfill: one `backfilled` row per application that already has a status, `from_status` NULL,
`at` = its `updated_at` (copied as stored, so the on-disk format stays the app's), `source`
"backfill". That `at` is the row's last update, not when the status changed, so timing metrics
skip backfilled rows; they still count for status.

Impl types only (sa.Uuid / sa.DateTime / sa.Boolean), like the baseline: a revision never imports
app code that can change after it ships (SYSTEM.md §12). Downgrade drops the table.

Revision ID: c5b4833bcc54
Revises: ff9591f140f7
"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


revision: str = "c5b4833bcc54"
down_revision: Union[str, Sequence[str], None] = "ff9591f140f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "application_status_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("backfilled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("application_status_events", schema=None) as batch_op:
        batch_op.create_index("ix_status_events_app_at", ["application_id", "at"], unique=False)

    # Untyped id/at columns: the stored text is copied as it was read, whatever its shape.
    applications = sa.table(
        "applications", sa.column("id"), sa.column("status", sa.Text()), sa.column("updated_at"),
    )
    events = sa.table(
        "application_status_events",
        sa.column("id"),
        sa.column("application_id"),
        sa.column("from_status", sa.Text()),
        sa.column("to_status", sa.Text()),
        sa.column("at"),
        sa.column("source", sa.Text()),
        sa.column("backfilled", sa.Boolean()),
    )
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(applications.c.id, applications.c.status, applications.c.updated_at)
        .where(applications.c.status.is_not(None))
        .order_by(applications.c.id)
    ).all()
    if rows:
        bind.execute(events.insert(), [
            {"id": uuid.uuid4().hex, "application_id": row.id, "from_status": None,
             "to_status": row.status, "at": row.updated_at, "source": "backfill", "backfilled": True}
            for row in rows
        ])


def downgrade() -> None:
    with op.batch_alter_table("application_status_events", schema=None) as batch_op:
        batch_op.drop_index("ix_status_events_app_at")
    op.drop_table("application_status_events")
