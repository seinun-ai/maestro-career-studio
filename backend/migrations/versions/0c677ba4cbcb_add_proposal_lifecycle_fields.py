"""add_proposal_lifecycle_fields

Revision ID: 0c677ba4cbcb
Revises: 1fc63637cffb
Create Date: 2026-07-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0c677ba4cbcb"
down_revision: Union[str, None] = "1fc63637cffb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "application_proposals",
        sa.Column("intervention_json", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "application_proposals",
        sa.Column("cap_reserved_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("application_proposals", "cap_reserved_at")
    op.drop_column("application_proposals", "intervention_json")
