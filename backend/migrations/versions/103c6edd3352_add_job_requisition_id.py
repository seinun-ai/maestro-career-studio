"""add job requisition_id

Revision ID: 103c6edd3352
Revises: 0c677ba4cbcb
Create Date: 2026-08-01
"""
import sqlalchemy as sa
from alembic import op

revision = "103c6edd3352"
down_revision = "0c677ba4cbcb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("requisition_id", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "requisition_id")
