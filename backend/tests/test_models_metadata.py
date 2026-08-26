from app.db import Base
from app import models  # noqa: F401


def test_all_planned_tables_are_registered():
    assert set(Base.metadata.tables) == {
        "application_proposals",
        "applications",
        "ats_scores",
        "autofill_field_observations",
        "base_resumes",
        "bullet_classifications",
        "bullet_rewrites",
        "chat_attachments",
        "chat_messages",
        "chat_sessions",
        "consent_events",
        "health_ask_answers",
        "health_gate_waivers",
        "jobs",
        "job_skills",
        "kb_documents",
        "kb_entities",
        "kb_points",
        "kb_port_log",
        "kb_profile",
        "qa_entries",
        "referrals",
        "resume_lint_reports",
        "resume_versions",
        "settings",
        "tailoring_sessions",
        "templates",
    }


def test_key_constraints_and_indexes_are_registered():
    jobs = Base.metadata.tables["jobs"]
    applications = Base.metadata.tables["applications"]
    job_skills = Base.metadata.tables["job_skills"]

    assert "uq_jobs_raw_text_hash" in {constraint.name or "" for constraint in jobs.constraints}
    assert "ix_applications_job_id_base_resume" in {index.name for index in applications.indexes}
    assert "ix_job_skills_skill_name" in {index.name for index in job_skills.indexes}
    assert "override_reason" in Base.metadata.tables["bullet_classifications"].columns


def test_formatting_and_preview_columns_registered():
    base_resumes = Base.metadata.tables["base_resumes"]
    applications = Base.metadata.tables["applications"]
    for table in (base_resumes, applications):
        assert "formatting_json" in table.columns
        assert "pdf_pages" in table.columns
        assert "render_error" in table.columns


def test_template_defaults_and_template_id_columns_registered():
    templates = Base.metadata.tables["templates"]
    base_resumes = Base.metadata.tables["base_resumes"]
    applications = Base.metadata.tables["applications"]
    assert "default_formatting" in templates.columns
    assert "template_id" in base_resumes.columns
    assert "template_id" in applications.columns


def test_autofill_field_observation_columns_registered():
    table = Base.metadata.tables["autofill_field_observations"]
    for column in (
        "signature_hash",
        "host",
        "label",
        "kind",
        "options",
        "rule_id",
        "outcomes",
        "seen_count",
        "session_marks",
        "first_seen_at",
        "last_seen_at",
    ):
        assert column in table.columns
    assert "uq_autofill_field_observations_signature_hash" in {
        constraint.name or "" for constraint in table.constraints
    }
    assert table.columns["signature_hash"].type.length == 64
