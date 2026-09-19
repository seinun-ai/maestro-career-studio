"""add qa_entry pdf_path

Revision ID: 646035b8946b
Revises: 81cdb01239b6
Create Date: 2026-05-01 09:29:17.809751

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '646035b8946b'
down_revision: Union[str, Sequence[str], None] = '81cdb01239b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("qa_entries", sa.Column("pdf_path", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("qa_entries", "pdf_path")
