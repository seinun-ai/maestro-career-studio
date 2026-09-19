"""store the user's classification override reason"""

import sqlalchemy as sa
from alembic import op

revision = "7bf4d2e18ac3"
down_revision = "3002d44d2876"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bullet_classifications",
        sa.Column("override_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bullet_classifications", "override_reason")
