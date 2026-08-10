"""add base_resumes.role_category

Revision ID: 6f07561c3b58
Revises: 9c4e1b7f2a6d
Create Date: 2026-07-25

Base resumes had no declared role. "Which resume targets which role" was
inferred by string-matching the SLUG against the job-side label map, which is a
coincidence rather than a relationship — so a resume named data_scientist_new
resolved to nothing, and analytics could not relate a resume to the roles it was
used for.

The backfill declares ONLY what is already unambiguously true: a slug that is
itself a category key. Everything else stays 'unknown' and is proposed in the UI
with its evidence. Deliberately NOT inferred from the modal role of each base's
applications — that reads the job axis at its most corrupt and would be a silent
guess inside a migration.

The slug list below is a POINT-IN-TIME SNAPSHOT, not role_categories.keys().
That function reads YAML at call time, which would make this historical revision
time-varying (see the same trap documented for 9a0404101e5f).

Note this backfill matches zero rows on a fresh install — migrations run before
seeding, so base_resumes is empty here. The equivalent rule lives in
services/seeding.seed_base_resumes, which is the normative path.
"""
from alembic import op
import sqlalchemy as sa

revision = "6f07561c3b58"
down_revision = "9c4e1b7f2a6d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "base_resumes",
        sa.Column("role_category", sa.Text(), nullable=False, server_default="unknown"),
    )
    op.execute(
        """
        UPDATE base_resumes SET role_category = slug WHERE slug IN (
            'data_scientist', 'data_analyst', 'data_engineer', 'ai_ml_engineer',
            'analytics_engineer', 'business_analyst', 'bi_developer',
            'research_scientist', 'software_engineer', 'mlops_engineer'
        )
        """
    )


def downgrade() -> None:
    op.drop_column("base_resumes", "role_category")
