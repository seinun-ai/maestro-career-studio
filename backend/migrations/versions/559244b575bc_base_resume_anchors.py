"""base_resumes.countries / company / focus

The anchors a base resume is written for: the countries it may be sent to
(ISO codes; [] means no country filter), the company it targets and a free-text
focus. Metadata only, set on PATCH /{slug}/identity like the role pair.

Revision ID: 559244b575bc
Revises: 7d3c1a9e5b20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "559244b575bc"
down_revision: Union[str, Sequence[str], None] = "7d3c1a9e5b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("base_resumes", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("countries", sa.JSON(), server_default=sa.text("'[]'"), nullable=False)
        )
        batch_op.add_column(sa.Column("company", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("focus", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("base_resumes", schema=None) as batch_op:
        batch_op.drop_column("focus")
        batch_op.drop_column("company")
        batch_op.drop_column("countries")
