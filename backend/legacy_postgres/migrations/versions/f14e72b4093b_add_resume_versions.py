"""add resume_versions

Revision ID: f14e72b4093b
Revises: 09265240aade
Create Date: 2026-07-11
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "f14e72b4093b"
down_revision = "09265240aade"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resume_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("resume_kind", sa.Text(), nullable=False),
        sa.Column("resume_key", sa.Text(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "parent_version_id",
            UUID(as_uuid=True),
            sa.ForeignKey("resume_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "resume_kind", "resume_key", "version_number", name="uq_resume_versions_identity"
        ),
    )
    op.create_index(
        "ix_resume_versions_resume", "resume_versions", ["resume_kind", "resume_key"]
    )


def downgrade() -> None:
    op.drop_index("ix_resume_versions_resume", table_name="resume_versions")
    op.drop_table("resume_versions")
