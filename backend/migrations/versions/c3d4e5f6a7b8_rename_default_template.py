"""rename default template display_name to Classic

Revision ID: c3d4e5f6a7b8
Revises: b1c2d3e4f5a6
Create Date: 2026-06-20

"""
from typing import Sequence, Union

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE templates SET display_name = 'Classic' "
        "WHERE id = 'default' AND display_name = 'Default'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE templates SET display_name = 'Default' "
        "WHERE id = 'default' AND display_name = 'Classic'"
    )
