"""add_application_artifact_dir

Revision ID: 1fc63637cffb
Revises: 11b61fe1ace9
Create Date: 2026-07-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1fc63637cffb"
down_revision: Union[str, None] = "11b61fe1ace9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("artifact_dir", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("applications", "artifact_dir")
