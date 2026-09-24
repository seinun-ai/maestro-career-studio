"""application_proposals.proposed_by

Who filed a proposal: "you" for the web app's queue, the MCP client's
clientInfo.name for a connected agent, NULL when unknown. Backfills the web
app's own past promotions, which carry a fixed plan summary
(frontend/lib/api.ts promoteJobToAgentQueue).

Revision ID: 9a5744f9b9d9
Revises: 871d0425b64c
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9a5744f9b9d9"
down_revision: Union[str, Sequence[str], None] = "871d0425b64c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PROMOTED = "Promoted from the tracker by the user"


def upgrade() -> None:
    with op.batch_alter_table("application_proposals", schema=None) as batch_op:
        batch_op.add_column(sa.Column("proposed_by", sa.Text(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE application_proposals SET proposed_by = 'you' "
            "WHERE json_extract(plan_json, '$.summary') = :summary"
        ).bindparams(summary=PROMOTED)
    )


def downgrade() -> None:
    with op.batch_alter_table("application_proposals", schema=None) as batch_op:
        batch_op.drop_column("proposed_by")
