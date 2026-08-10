"""kb write provenance: origin_detail on points, origin+origin_detail on entities

Revision ID: 0d9eb8e7abd8
Revises: a7c3f19d24be
Create Date: 2026-08-04

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0d9eb8e7abd8"
down_revision: Union[str, Sequence[str], None] = "a7c3f19d24be"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # All nullable: NULL means "written before provenance existed, or via the
    # web UI". No backfill — inventing an origin for historic rows would be a
    # fabricated audit trail.
    op.add_column("kb_points", sa.Column("origin_detail", sa.Text(), nullable=True))
    op.add_column("kb_entities", sa.Column("origin", sa.Text(), nullable=True))
    op.add_column("kb_entities", sa.Column("origin_detail", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("kb_entities", "origin_detail")
    op.drop_column("kb_entities", "origin")
    op.drop_column("kb_points", "origin_detail")
