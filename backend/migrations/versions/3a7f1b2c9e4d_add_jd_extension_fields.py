"""add jd extension fields

Revision ID: 3a7f1b2c9e4d
Revises: d08cfaa90f0d
Create Date: 2026-05-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3a7f1b2c9e4d"
down_revision: Union[str, Sequence[str], None] = "d08cfaa90f0d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("city", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("state", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("country", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("location_raw", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("work_authorization", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("opt_accepted", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("years_experience_min", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("years_experience_max", sa.Integer(), nullable=True))

    # Preserve the existing free-text location on every row so the backfill
    # script (which fills city/state/country/etc. via LLM) starts with
    # location_raw already populated.
    op.execute("UPDATE jobs SET location_raw = location WHERE location IS NOT NULL")

    op.create_index("ix_jobs_state", "jobs", ["state"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_jobs_state", table_name="jobs")
    op.drop_column("jobs", "years_experience_max")
    op.drop_column("jobs", "years_experience_min")
    op.drop_column("jobs", "opt_accepted")
    op.drop_column("jobs", "work_authorization")
    op.drop_column("jobs", "location_raw")
    op.drop_column("jobs", "country")
    op.drop_column("jobs", "state")
    op.drop_column("jobs", "city")
