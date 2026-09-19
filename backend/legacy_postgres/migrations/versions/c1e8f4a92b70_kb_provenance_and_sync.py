"""kb provenance, port-log direction, and base sync timestamp

Revision ID: c1e8f4a92b70
Revises: 0bc45a1bf6d6
Create Date: 2026-08-21

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1e8f4a92b70"
down_revision: Union[str, Sequence[str], None] = "0bc45a1bf6d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # All nullable: NULL means "written before this existed". No backfill —
    # inventing provenance/direction for historic rows would be a fabricated
    # audit trail. last_kb_synced_at NULL means never synced.
    op.add_column("kb_points", sa.Column("provenance", sa.Text(), nullable=True))
    op.add_column("kb_port_log", sa.Column("direction", sa.Text(), nullable=True))
    op.add_column(
        "base_resumes",
        sa.Column("last_kb_synced_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("base_resumes", "last_kb_synced_at")
    op.drop_column("kb_port_log", "direction")
    op.drop_column("kb_points", "provenance")
