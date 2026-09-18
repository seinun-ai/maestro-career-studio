"""career KB: entities, points, documents, port log, profile"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "3002d44d2876"
down_revision = "92afc6239dee"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kb_entities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("org", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Text(), nullable=True),
        sa.Column("end_date", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="completed"),
        sa.Column("detail_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "kb_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("mime", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("text_content", sa.Text(), nullable=False, server_default=""),
        sa.Column("ingest_status", sa.Text(), nullable=False, server_default="extracted"),
        sa.Column("ingest_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["kb_entities.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_kb_documents_entity_id", "kb_documents", ["entity_id"])
    op.create_table(
        "kb_points",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("source_document_id", UUID(as_uuid=True), nullable=True),
        sa.Column("tags_json", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("merge_sources_json", JSONB(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["kb_entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_document_id"], ["kb_documents.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_kb_points_entity_id", "kb_points", ["entity_id"])
    op.create_table(
        "kb_port_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("point_id", UUID(as_uuid=True), nullable=True),
        sa.Column("resume_kind", sa.Text(), nullable=False, server_default="base"),
        sa.Column("resume_key", sa.Text(), nullable=False),
        sa.Column("section", sa.Text(), nullable=False),
        sa.Column("ported_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("ported_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["kb_entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["point_id"], ["kb_points.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_kb_port_log_entity_id", "kb_port_log", ["entity_id"])
    op.create_index("ix_kb_port_log_point_id", "kb_port_log", ["point_id"])
    op.create_table(
        "kb_profile",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("contact_json", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("skills_json", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("kb_profile")
    op.drop_index("ix_kb_port_log_point_id", table_name="kb_port_log")
    op.drop_index("ix_kb_port_log_entity_id", table_name="kb_port_log")
    op.drop_table("kb_port_log")
    op.drop_index("ix_kb_points_entity_id", table_name="kb_points")
    op.drop_table("kb_points")
    op.drop_index("ix_kb_documents_entity_id", table_name="kb_documents")
    op.drop_table("kb_documents")
    op.drop_table("kb_entities")
