"""add resume_lint_reports

Revision ID: 86d4d54bb4f1
Revises: b14020ffe969
Create Date: 2026-07-12
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "86d4d54bb4f1"
down_revision = "b14020ffe969"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resume_lint_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("resume_kind", sa.Text(), nullable=False),
        sa.Column("resume_key", sa.Text(), nullable=False),
        sa.Column("resume_version_number", sa.Integer(), nullable=True),
        sa.Column("report_json", JSONB(), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_resume_lint_reports_resume", "resume_lint_reports", ["resume_kind", "resume_key"]
    )


def downgrade() -> None:
    op.drop_index("ix_resume_lint_reports_resume", table_name="resume_lint_reports")
    op.drop_table("resume_lint_reports")
