"""add templates.engine column

Revision ID: 9c4e1b7f2a6d
Revises: da726bb8e929
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9c4e1b7f2a6d"
down_revision: Union[str, Sequence[str], None] = "da726bb8e929"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default='latex' -> every existing row is untouched and reads 'latex'.
    op.add_column(
        "templates",
        sa.Column("engine", sa.Text(), nullable=False, server_default="latex"),
    )


def downgrade() -> None:
    op.drop_column("templates", "engine")
