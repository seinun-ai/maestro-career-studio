"""add applications.referral_id

Revision ID: d08cfaa90f0d
Revises: 46d391258b6d
Create Date: 2026-05-12 06:03:00.838205

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd08cfaa90f0d'
down_revision: Union[str, Sequence[str], None] = '46d391258b6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("referral_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_applications_referral_id",
        "applications",
        "referrals",
        ["referral_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_applications_referral_id", "applications", type_="foreignkey")
    op.drop_column("applications", "referral_id")
