"""base_resumes.color_hue

The identity colour of a base resume: one hue (0-359), picked on create and
changed on PATCH /{slug}/identity. Existing live resumes are backfilled with
distinct presets so today's list is not all one grey.

Revision ID: abd275b457d8
Revises: cf0804d00ae2
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "abd275b457d8"
down_revision: Union[str, Sequence[str], None] = "cf0804d00ae2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Copied from services/resume_colors.PRESET_HUES: a migration never imports app code.
_PRESETS = (5, 40, 80, 125, 160, 195, 230, 265, 300, 335)


def upgrade() -> None:
    with op.batch_alter_table("base_resumes", schema=None) as batch_op:
        batch_op.add_column(sa.Column("color_hue", sa.Integer(), nullable=True))
    conn = op.get_bind()
    slugs = [
        row[0]
        for row in conn.execute(
            sa.text("SELECT slug FROM base_resumes WHERE deleted_at IS NULL ORDER BY created_at, slug")
        )
    ]
    for i, slug in enumerate(slugs):
        conn.execute(
            sa.text("UPDATE base_resumes SET color_hue = :h WHERE slug = :s"),
            {"h": _PRESETS[i % len(_PRESETS)], "s": slug},
        )


def downgrade() -> None:
    with op.batch_alter_table("base_resumes", schema=None) as batch_op:
        batch_op.drop_column("color_hue")
