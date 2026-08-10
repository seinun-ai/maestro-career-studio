"""base_resume soft-delete and applied_at backfill

Revision ID: e6f7a8b9c0d1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "base_resumes",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill applied_at for legacy rows already marked applied but never stamped.
    op.execute(
        "UPDATE applications SET applied_at = COALESCE(applied_at, updated_at) "
        "WHERE status = 'applied' AND applied_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("base_resumes", "deleted_at")
