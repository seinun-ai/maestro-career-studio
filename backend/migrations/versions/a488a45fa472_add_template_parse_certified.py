"""add template parse_certified

Revision ID: a488a45fa472
Revises: 9a0404101e5f
Create Date: 2026-07-13 23:18:52.968589

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a488a45fa472'
down_revision: Union[str, Sequence[str], None] = '9a0404101e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "templates",
        sa.Column("parse_certified", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("templates", "parse_certified")
