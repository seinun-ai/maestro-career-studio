"""Drop the legacy fit_scores table and applications.suggestions_json/decisions_json.

The LLM fit-scoring pipeline was replaced by the deterministic ATS engine
(ats_scores); nothing has written fit_scores or suggestions/decisions since.
This is destructive for any remaining legacy rows — they were read-only
history surfaced on job/application detail and the legacy Suggestions tab,
both of which are removed alongside this migration.

Revision ID: 09265240aade
Revises: f8a9b0c1d2e3
Create Date: 2026-07-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "09265240aade"
down_revision: Union[str, Sequence[str], None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("fit_scores")
    op.drop_column("applications", "suggestions_json")
    op.drop_column("applications", "decisions_json")


def downgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("decisions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "applications",
        sa.Column("suggestions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_table(
        "fit_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("base_resume", sa.Text(), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=True),
        sa.Column("verdict", sa.Text(), nullable=True),
        sa.Column("categories_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("gap_summary", sa.Text(), nullable=True),
        sa.Column("model_used", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("job_id", "base_resume", name="uq_fit_scores_job_id_base_resume"),
    )
    op.create_index("ix_fit_scores_job_id", "fit_scores", ["job_id"])
