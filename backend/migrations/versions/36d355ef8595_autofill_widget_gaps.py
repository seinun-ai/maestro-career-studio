"""The known-gaps list: widgets the Companion could not operate, or the user fixed by hand.

Impl types only (sa.Uuid / sa.DateTime), like the baseline: a revision never imports app code that
can change after it ships (SYSTEM.md §12). The table is value-free: no label, value or option text.
"""
from alembic import op
import sqlalchemy as sa

revision = "36d355ef8595"
down_revision = "d3ea5090cc80"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "autofill_widget_gaps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("family", sa.String(length=24), nullable=False),
        sa.Column("host", sa.Text(), nullable=False),
        sa.Column("shape", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.String(length=24), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"),
                  nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"),
                  nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("family", "host", "shape", "outcome", name="uq_autofill_widget_gaps_key"),
    )


def downgrade() -> None:
    op.drop_table("autofill_widget_gaps")
