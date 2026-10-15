"""jobs.referrer_board

The job board the user came from when a job was saved on the employer's own page, kept by name
("Built In") so "How did you hear about us?" can name it. Nullable: most jobs never have one.

Revision ID: e5a1c2d77b04
Revises: b7e41c90d3a2
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5a1c2d77b04"
down_revision: Union[str, Sequence[str], None] = "b7e41c90d3a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("referrer_board", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_column("referrer_board")
