"""add jobs.disqualifying_for_opt

Revision ID: e5f6a7b8c9d0
Revises: c3d4e5f6a7b8
Create Date: 2026-06-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "disqualifying_for_opt",
            sa.Boolean(),
            nullable=True,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("jobs", "disqualifying_for_opt")
