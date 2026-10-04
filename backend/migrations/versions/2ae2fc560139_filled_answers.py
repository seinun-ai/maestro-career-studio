"""The answer receipt: what each page run filled into a job's application form.

Impl types only (sa.Uuid / sa.JSON / sa.DateTime), like the baseline: a revision never imports
app code that can change after it ships (SYSTEM.md §12). The values live in this table and
nowhere else (SYSTEM.md {#inv-filled-answers-local}).
"""
from alembic import op
import sqlalchemy as sa

revision = "2ae2fc560139"
down_revision = "4c9c98bbc8ef"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "filled_answers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("host", sa.Text(), nullable=True),
        sa.Column("step", sa.Text(), nullable=True),
        sa.Column("captured_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"),
                  nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("filled_answers", schema=None) as batch_op:
        batch_op.create_index("ix_filled_answers_job_id", ["job_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("filled_answers", schema=None) as batch_op:
        batch_op.drop_index("ix_filled_answers_job_id")
    op.drop_table("filled_answers")
