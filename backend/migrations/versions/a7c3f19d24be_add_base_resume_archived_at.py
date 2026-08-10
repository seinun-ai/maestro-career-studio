"""add base_resume archived_at

Revision ID: a7c3f19d24be
Revises: aa323ad849bf
Create Date: 2026-08-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7c3f19d24be"
down_revision: Union[str, Sequence[str], None] = "aa323ad849bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "base_resumes",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("base_resumes", "archived_at")
