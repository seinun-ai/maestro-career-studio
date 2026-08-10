"""add tailoring_sessions table

Revision ID: c182db65461c
Revises: 7c023c003572
Create Date: 2026-07-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "c182db65461c"
down_revision: Union[str, Sequence[str], None] = "7c023c003572"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tailoring_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", UUID(as_uuid=True),
                  sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("base_resume", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'open'")),
        sa.Column("gaps_json", JSONB(), nullable=False),
        sa.Column("resolutions_json", JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("application_id", UUID(as_uuid=True),
                  sa.ForeignKey("applications.id", ondelete="SET NULL"), nullable=True),
        sa.Column("base_ats_score_id", UUID(as_uuid=True),
                  sa.ForeignKey("ats_scores.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tailoring_sessions_job_id", "tailoring_sessions", ["job_id"])


def downgrade() -> None:
    op.drop_table("tailoring_sessions")
