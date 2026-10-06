"""Ownership metadata and local sync bookkeeping; sync remains opt-in.

Impl types only: shipped revisions never import mutable app model code.
"""

import sqlalchemy as sa
from alembic import op

revision = "46b60e6ca922"
down_revision = "7d3c1a9e5b20"
branch_labels = None
depends_on = None


def _create_sync_state() -> None:
    table = op.create_table(
        "sync_state",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )
    op.bulk_insert(table, [{"name": "clock", "value": 0}, {"name": "profile_rev", "value": 0}])


def _create_sync_tombstones() -> None:
    op.create_table(
        "sync_tombstones",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("rev", sa.Integer(), nullable=False),
        sa.Column(
            "deleted_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.PrimaryKeyConstraint("job_id"),
    )


def _create_sync_requests() -> None:
    op.create_table(
        "sync_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("origin", sa.String(8), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.add_column(sa.Column("owner_machine", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("sync_rev", sa.Integer(), server_default="0", nullable=False))
        batch_op.add_column(sa.Column("handover", sa.String(16), nullable=True))
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.add_column(sa.Column("machine", sa.String(32), nullable=True))
    _create_sync_state()
    _create_sync_tombstones()
    _create_sync_requests()


def downgrade() -> None:
    op.drop_table("sync_requests")
    op.drop_table("sync_tombstones")
    op.drop_table("sync_state")
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.drop_column("machine")
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_column("handover")
        batch_op.drop_column("sync_rev")
        batch_op.drop_column("owner_machine")
