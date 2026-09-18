"""add kb_port_log.source_text for adapted ports

Adapted ports rewrite the point text before it lands in the resume, so
``ported_text`` (what the resume says) can legitimately differ from the KB
point. ``source_text`` snapshots the point text at port time; drift is
computed against it when present. NULL (verbatim ports) falls back to
``ported_text``, preserving the original semantics.

Revision ID: 53855dff79bc
Revises: 8e5e32ca5c63
Create Date: 2026-07-17

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "53855dff79bc"
down_revision = "8e5e32ca5c63"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("kb_port_log", sa.Column("source_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("kb_port_log", "source_text")
