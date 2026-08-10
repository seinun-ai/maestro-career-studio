"""add templates archived_at

Mirrors a7c3f19d24be (base_resume archived_at) exactly: same column type, same
nullable-means-active semantics. Seeding four more bundled templates makes the
gallery and the Studio picker long enough that hiding the ones you do not use
stops being cosmetic.

Revision ID: 8ba1429dca29
Revises: c37b89e136ad
Create Date: 2026-08-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "8ba1429dca29"
down_revision: Union[str, Sequence[str], None] = "c37b89e136ad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "templates",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("templates", "archived_at")
