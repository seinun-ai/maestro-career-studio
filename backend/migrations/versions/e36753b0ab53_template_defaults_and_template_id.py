"""template defaults and template_id

Revision ID: e36753b0ab53
Revises: a488a45fa472
Create Date: 2026-07-14 00:11:33.622152

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e36753b0ab53'
down_revision: Union[str, Sequence[str], None] = 'a488a45fa472'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("templates", sa.Column("default_formatting", postgresql.JSONB(), nullable=True))
    op.add_column("base_resumes", sa.Column("template_id", sa.Text(), nullable=True))
    op.add_column("applications", sa.Column("template_id", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("applications", "template_id")
    op.drop_column("base_resumes", "template_id")
    op.drop_column("templates", "default_formatting")
