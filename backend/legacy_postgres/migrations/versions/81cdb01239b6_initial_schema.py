"""initial schema

Revision ID: 81cdb01239b6
Revises: 
Create Date: 2026-04-22 16:18:40.710433

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '81cdb01239b6'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "base_resumes",
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("data_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("pdf_path", sa.Text(), nullable=True),
        sa.Column("tex_path", sa.Text(), nullable=True),
        sa.Column("pdf_rendered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("slug"),
    )
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("raw_text_hash", sa.String(length=64), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("extracted_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("company", sa.Text(), nullable=True),
        sa.Column("role_category", sa.Text(), nullable=True),
        sa.Column("level", sa.Text(), nullable=True),
        sa.Column("employment_type", sa.Text(), nullable=True),
        sa.Column("work_mode", sa.Text(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("salary_min", sa.Numeric(), nullable=True),
        sa.Column("salary_max", sa.Numeric(), nullable=True),
        sa.Column("salary_period", sa.Text(), nullable=True),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("raw_text_hash", name="uq_jobs_raw_text_hash"),
    )
    op.create_index("ix_jobs_role_category_level", "jobs", ["role_category", "level"], unique=False)
    op.create_table(
        "settings",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("base_resume", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("suggestions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("decisions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("customized_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("pdf_path", sa.Text(), nullable=True),
        sa.Column("tex_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_applications_job_id_base_resume",
        "applications",
        ["job_id", "base_resume"],
        unique=False,
    )
    op.create_index("ix_applications_status", "applications", ["status"], unique=False)
    op.create_table(
        "fit_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("base_resume", sa.Text(), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=True),
        sa.Column("verdict", sa.Text(), nullable=True),
        sa.Column("categories_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("gap_summary", sa.Text(), nullable=True),
        sa.Column("model_used", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "base_resume", name="uq_fit_scores_job_id_base_resume"),
    )
    op.create_index("ix_fit_scores_job_id", "fit_scores", ["job_id"], unique=False)
    op.create_table(
        "job_skills",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_name", sa.Text(), nullable=False),
        sa.Column("skill_category", sa.Text(), nullable=False),
        sa.Column("requirement_level", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("job_id", "skill_name", "skill_category", "requirement_level"),
    )
    op.create_index("ix_job_skills_skill_name", "job_skills", ["skill_name"], unique=False)
    op.create_table(
        "qa_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("model_used", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("qa_entries")
    op.drop_index("ix_job_skills_skill_name", table_name="job_skills")
    op.drop_table("job_skills")
    op.drop_index("ix_fit_scores_job_id", table_name="fit_scores")
    op.drop_table("fit_scores")
    op.drop_index("ix_applications_status", table_name="applications")
    op.drop_index("ix_applications_job_id_base_resume", table_name="applications")
    op.drop_table("applications")
    op.drop_table("settings")
    op.drop_index("ix_jobs_role_category_level", table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("base_resumes")
