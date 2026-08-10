"""add tailoring_session staleness hashes

A session freezes gaps + the before-score at creation, but tailor() loads the
CURRENT base resume and the JD can be re-extracted meanwhile. Store content
hashes at creation so mutations on a stale session can be rejected instead of
silently operating on a different document (SYSTEM.md §11 item 1).

Revision ID: 8e5e32ca5c63
Revises: 7bf4d2e18ac3
Create Date: 2026-07-16
"""
import sqlalchemy as sa
from alembic import op

revision = "8e5e32ca5c63"
down_revision = "7bf4d2e18ac3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tailoring_sessions",
        sa.Column("base_content_hash", sa.Text(), nullable=True),
    )
    op.add_column(
        "tailoring_sessions",
        sa.Column("jd_extraction_hash", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tailoring_sessions", "jd_extraction_hash")
    op.drop_column("tailoring_sessions", "base_content_hash")
