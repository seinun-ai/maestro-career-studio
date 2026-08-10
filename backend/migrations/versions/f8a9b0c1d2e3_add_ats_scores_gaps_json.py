"""add ats_scores gaps_json

Revision ID: f8a9b0c1d2e3
Revises: d5e6f7a8b9c0
Create Date: 2026-07-08 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, Sequence[str], None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ats_scores", sa.Column("gaps_json", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("ats_scores", "gaps_json")
