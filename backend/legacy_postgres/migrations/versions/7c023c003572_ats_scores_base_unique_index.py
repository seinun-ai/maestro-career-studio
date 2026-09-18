"""unique base row per (job, target) on ats_scores

Backstop against concurrent duplicate base rows: the service upserts via
select-then-update (single-user app), the partial unique index enforces it.

Revision ID: 7c023c003572
Revises: 99c21dd616a7
Create Date: 2026-07-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7c023c003572"
down_revision: Union[str, Sequence[str], None] = "99c21dd616a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_ats_scores_base_target",
        "ats_scores",
        ["job_id", "target_type", "target_id"],
        unique=True,
        postgresql_where=sa.text("phase = 'base'"),
    )


def downgrade() -> None:
    op.drop_index("uq_ats_scores_base_target", table_name="ats_scores")
