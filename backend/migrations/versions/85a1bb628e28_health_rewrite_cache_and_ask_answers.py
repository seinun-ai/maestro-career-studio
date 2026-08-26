"""health round 2: unattended rewrite cache + persisted ask answers

Revision ID: 85a1bb628e28
Revises: 3ea31824ea85
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "85a1bb628e28"
down_revision: Union[str, Sequence[str], None] = "3ea31824ea85"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bullet_rewrites",
        sa.Column("content_hash", sa.Text(), primary_key=True),
        sa.Column("rewrite_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_table(
        "health_ask_answers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("resume_kind", sa.Text(), nullable=False),
        sa.Column("resume_key", sa.Text(), nullable=False),
        sa.Column("finding_id", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("suggestion", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "resume_kind",
            "resume_key",
            "finding_id",
            name="uq_health_ask_answer",
        ),
    )


def downgrade() -> None:
    op.drop_table("health_ask_answers")
    op.drop_table("bullet_rewrites")
