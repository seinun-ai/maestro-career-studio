"""health v2: classification cache, gate waivers, report + template columns"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "92afc6239dee"
down_revision = "e36753b0ab53"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bullet_classifications",
        sa.Column("content_hash", sa.Text(), primary_key=True),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("override_level", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "health_gate_waivers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("resume_kind", sa.Text(), nullable=False),
        sa.Column("resume_key", sa.Text(), nullable=False),
        sa.Column("gate_id", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("resume_kind", "resume_key", "gate_id", name="uq_health_waiver"),
    )
    op.add_column("resume_lint_reports", sa.Column("model_version", sa.Text(), nullable=True))
    op.add_column("resume_lint_reports", sa.Column("features_json", JSONB(), nullable=True))
    op.add_column("templates", sa.Column("parse_report_json", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("templates", "parse_report_json")
    op.drop_column("resume_lint_reports", "features_json")
    op.drop_column("resume_lint_reports", "model_version")
    op.drop_table("health_gate_waivers")
    op.drop_table("bullet_classifications")
