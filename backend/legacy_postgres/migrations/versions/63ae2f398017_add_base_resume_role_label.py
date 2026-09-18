"""add base resume role label

Revision ID: 63ae2f398017
Revises: c37b89e136ad
Create Date: 2026-08-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "63ae2f398017"
down_revision: Union[str, Sequence[str], None] = "c37b89e136ad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "base_resumes", sa.Column("role_label", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("base_resumes", "role_label")
