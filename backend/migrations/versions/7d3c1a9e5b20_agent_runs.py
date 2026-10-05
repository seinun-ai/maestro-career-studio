"""The run log: one row per automation run an agent reported (MCP `record_run`).

Impl types only (sa.Uuid / sa.JSON / sa.DateTime), like the baseline: a revision never imports
app code that can change after it ships (SYSTEM.md §12).
"""
from alembic import op
import sqlalchemy as sa

revision = "7d3c1a9e5b20"
down_revision = "2ae2fc560139"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("automation", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("agent", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"),
                  nullable=False),
        sa.Column("counts", sa.JSON(), nullable=False),
        sa.Column("digest", sa.Text(), nullable=False),
        sa.Column("job_ids", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.create_index("ix_agent_runs_finished_at", ["finished_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.drop_index("ix_agent_runs_finished_at")
    op.drop_table("agent_runs")
