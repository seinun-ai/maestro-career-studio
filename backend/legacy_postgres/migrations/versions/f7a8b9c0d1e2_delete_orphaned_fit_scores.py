"""delete orphaned fit_scores rows (base_resume with no base_resumes row)

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-06-30

One-time data cleanup. `hybrid` was hard-deleted before soft-delete existed,
so it has no `base_resumes` row but still had orphaned `fit_scores` rows that
surfaced as a ghost `hybrid` bucket in the fit distribution. This removes any
`fit_scores` whose `base_resume` no longer maps to a `base_resumes` slug.

Note: this intentionally does NOT touch `applications` rows referencing
`base_resume = 'hybrid'` -- that is preserved history.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, Sequence[str], None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM fit_scores "
        "WHERE base_resume NOT IN (SELECT slug FROM base_resumes)"
    )


def downgrade() -> None:
    # One-way data cleanup: the orphaned rows are unrecoverable, so there is
    # nothing to restore on downgrade.
    pass
