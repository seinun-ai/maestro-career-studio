"""add application user_prompt

Revision ID: a1b2c3d4e5f6
Revises: 646035b8946b
Create Date: 2026-05-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "3a7f1b2c9e4d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("user_prompt", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("applications", "user_prompt")
