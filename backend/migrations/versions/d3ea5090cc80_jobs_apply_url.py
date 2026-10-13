"""jobs.apply_url

The employer's own apply link, recorded beside source_url (the board page the job was saved
from) when the posting exposes one. Nullable: most jobs never have one.

Revision ID: d3ea5090cc80
Revises: abd275b457d8
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d3ea5090cc80"
down_revision: Union[str, Sequence[str], None] = "abd275b457d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("apply_url", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_column("apply_url")
