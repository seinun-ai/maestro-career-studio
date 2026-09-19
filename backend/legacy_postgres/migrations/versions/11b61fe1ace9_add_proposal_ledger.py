"""add_proposal_ledger

Revision ID: 11b61fe1ace9
Revises: 56ade310b259
Create Date: 2026-07-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '11b61fe1ace9'
down_revision: Union[str, None] = '56ade310b259'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "application_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("applications.id", ondelete="SET NULL"), nullable=True),
        sa.Column("referral_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("referrals.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending_review"),
        sa.Column("fit_json", postgresql.JSONB(), nullable=True),
        sa.Column("plan_json", postgresql.JSONB(), nullable=True),
        sa.Column("evidence_json", postgresql.JSONB(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_application_proposals_status", "application_proposals", ["status"])
    op.create_index("ix_application_proposals_job_id", "application_proposals", ["job_id"])

    op.create_table(
        "consent_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("application_proposals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("evidence_manifest_json", postgresql.JSONB(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_consent_events_proposal_id", "consent_events", ["proposal_id"])


def downgrade() -> None:
    op.drop_index("ix_consent_events_proposal_id", table_name="consent_events")
    op.drop_table("consent_events")
    op.drop_index("ix_application_proposals_job_id", table_name="application_proposals")
    op.drop_index("ix_application_proposals_status", table_name="application_proposals")
    op.drop_table("application_proposals")
