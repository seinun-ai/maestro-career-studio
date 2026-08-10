"""add ats_scores table

Revision ID: 99c21dd616a7
Revises: f7a8b9c0d1e2
Create Date: 2026-07-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "99c21dd616a7"
down_revision: Union[str, Sequence[str], None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ats_scores",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", UUID(as_uuid=True),
                  sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=False),
        sa.Column("application_id", UUID(as_uuid=True),
                  sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=True),
        sa.Column("phase", sa.Text(), nullable=False),
        sa.Column("composite", sa.Numeric(5, 1), nullable=False),
        sa.Column("subscores_json", JSONB(), nullable=False),
        sa.Column("skill_table_json", JSONB(), nullable=False),
        sa.Column("config_version", sa.Text(), nullable=False),
        sa.Column("engine_version", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ats_scores_job_id_phase", "ats_scores", ["job_id", "phase"])
    op.create_index("ix_ats_scores_application_id", "ats_scores", ["application_id"])


def downgrade() -> None:
    op.drop_table("ats_scores")
