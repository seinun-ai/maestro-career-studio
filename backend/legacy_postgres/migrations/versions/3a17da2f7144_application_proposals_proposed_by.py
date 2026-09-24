"""application_proposals.proposed_by (mirror of the SQLite chain's 9a5744f9b9d9)

The first-boot import copies every model column and refuses a source that
lacks one, so the boxed Postgres chain gains the column (and the same
backfill of the web app's own promotions) before the copy. Delete with this
chain (SYSTEM.md §13 postgres-to-sqlite).

Revision ID: 3a17da2f7144
Revises: 85a1bb628e28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3a17da2f7144"
down_revision: Union[str, Sequence[str], None] = "85a1bb628e28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("application_proposals", sa.Column("proposed_by", sa.Text(), nullable=True))
    op.execute(
        "UPDATE application_proposals SET proposed_by = 'you' "
        "WHERE plan_json->>'summary' = 'Promoted from the tracker by the user'"
    )


def downgrade() -> None:
    op.drop_column("application_proposals", "proposed_by")
