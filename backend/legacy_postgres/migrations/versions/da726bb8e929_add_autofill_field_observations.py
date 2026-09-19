"""add autofill_field_observations table

Revision ID: da726bb8e929
Revises: 14133e25da5f
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "da726bb8e929"
down_revision: Union[str, Sequence[str], None] = "14133e25da5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "autofill_field_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("signature_hash", sa.String(length=64), nullable=False),
        sa.Column("host", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column(
            "options",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("rule_id", sa.Text(), nullable=True),
        sa.Column(
            "outcomes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("seen_count", sa.Integer(), nullable=False),
        sa.Column(
            "session_marks",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "signature_hash",
            name="uq_autofill_field_observations_signature_hash",
        ),
    )


def downgrade() -> None:
    op.drop_table("autofill_field_observations")
