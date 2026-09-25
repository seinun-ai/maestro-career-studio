"""Versioned health evaluations and separate user disputes.

Impl types only (sa.JSON / sa.DateTime), like the baseline: a revision never imports
app code that can change after it ships (SYSTEM.md §12).
"""
from alembic import op
import sqlalchemy as sa

revision = "980498217fe6"
down_revision = "9a5744f9b9d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("bullet_classifications") as batch:
        batch.add_column(sa.Column("rubric_version", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("evidence_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("question", sa.Text(), nullable=True))
        batch.add_column(sa.Column("ask_kind", sa.Text(), nullable=True))
        batch.add_column(sa.Column("measure_target", sa.Text(), nullable=True))
        batch.add_column(sa.Column("alt_question", sa.Text(), nullable=True))
        batch.add_column(sa.Column("language_json", sa.JSON(), nullable=True))
    op.create_table(
        "bullet_disputes",
        sa.Column("content_hash", sa.Text(), primary_key=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("original_json", sa.JSON(), nullable=False),
        sa.Column("revised_json", sa.JSON(), nullable=False),
        sa.Column("reply", sa.Text(), nullable=False),
        sa.Column("suggestion", sa.Text(), nullable=True),
        sa.Column("metric_unavailable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rubric_version", sa.Integer(), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("bullet_disputes")
    with op.batch_alter_table("bullet_classifications") as batch:
        for column in ("language_json", "alt_question", "measure_target", "ask_kind",
                       "question", "evidence_json", "rubric_version"):
            batch.drop_column(column)
