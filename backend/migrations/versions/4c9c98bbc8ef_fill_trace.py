"""The fill trace: one stored trace per Companion run and the counters folded from them.

Impl types only (sa.Uuid / sa.JSON / sa.DateTime), like the baseline: a revision never imports
app code that can change after it ships (SYSTEM.md §12). Both tables are value-free.
"""
from alembic import op
import sqlalchemy as sa

revision = "4c9c98bbc8ef"
down_revision = "643ba5470e73"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "autofill_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("host", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("trace", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_autofill_runs_run_id"),
    )
    op.create_table(
        "autofill_mechanism_stats",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("counts", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("autofill_mechanism_stats")
    op.drop_table("autofill_runs")
