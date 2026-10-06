"""Clear cached evaluations the quote check demoted by mistake.

The model sometimes wrapped each evidence quote in quote marks, so no quote matched the bullet
and `bullet_classify._validate` demoted every analogue/direct level to adjacent with no evidence
kept. Those rows are indistinguishable from the model's own verdict, so every current-rubric
adjacent row without evidence is dropped and re-evaluated on the next check. A hand-set rating
lives on the same row and is kept.
"""
from alembic import op
import sqlalchemy as sa

revision = "643ba5470e73"
down_revision = "4022b54933e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "DELETE FROM bullet_classifications WHERE rubric_version = 2 AND level = 'adjacent'"
        " AND override_level IS NULL AND (evidence_json IS NULL OR evidence_json IN ('[]', 'null'))"))


def downgrade() -> None:
    """No-op: a deleted cache row is re-evaluated on the next check; there is nothing to restore."""
