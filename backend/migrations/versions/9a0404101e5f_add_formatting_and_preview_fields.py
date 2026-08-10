"""add formatting and preview fields

Revision ID: 9a0404101e5f
Revises: 86d4d54bb4f1
Create Date: 2026-07-13 17:26:16.014758

Adds nullable formatting/preview columns to base_resumes and applications, and
refreshes the seeded Classic template source to the fmt-parameterized on-disk
resume.tex.j2. The template refresh is forward-only: downgrade drops the six
columns but leaves the template source in place.
"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '9a0404101e5f'
down_revision: Union[str, Sequence[str], None] = '86d4d54bb4f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    for table in ("base_resumes", "applications"):
        op.add_column(table, sa.Column("formatting_json", postgresql.JSONB(), nullable=True))
        op.add_column(table, sa.Column("pdf_pages", sa.Integer(), nullable=True))
        op.add_column(table, sa.Column("render_error", sa.Text(), nullable=True))

    # Refresh the seeded Classic template to the fmt-parameterized source.
    # Only touch a default that is still the pre-feature Classic (source has no
    # ``fmt.`` references). Editing the default in place (PUT ?allow_default_edit)
    # does not change origin, so guarding on origin alone would clobber a user's
    # customizations; the ``fmt.`` guard makes this a targeted, idempotent upgrade.
    template_path = Path(__file__).parents[2] / "app" / "templates" / "resume.tex.j2"
    source = template_path.read_text(encoding="utf-8")
    op.execute(
        sa.text(
            "UPDATE templates SET source = :src, last_error = NULL "
            "WHERE id = 'default' AND origin = 'seed' AND source NOT LIKE '%fmt.%'"
        ).bindparams(src=source)
    )


def downgrade() -> None:
    """Downgrade schema.

    Forward-only for the template source refresh; only the columns are dropped.
    """
    for table in ("applications", "base_resumes"):
        op.drop_column(table, "render_error")
        op.drop_column(table, "pdf_pages")
        op.drop_column(table, "formatting_json")
