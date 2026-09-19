"""add_source_provenance

Revision ID: 56ade310b259
Revises: 6f07561c3b58
Create Date: 2026-07-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '56ade310b259'
down_revision: Union[str, None] = '6f07561c3b58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("source", sa.Text(), nullable=False, server_default="user"))
    op.add_column("applications", sa.Column("source", sa.Text(), nullable=False, server_default="user"))


def downgrade() -> None:
    op.drop_column("applications", "source")
    op.drop_column("jobs", "source")
