"""Every table's sync class (design Part A + amendments). A new table MUST be added here:
test_every_table_is_classified fails otherwise.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from app.db import Base
from app.models.application import Application
from app.models.application_proposal import ApplicationProposal

PROFILE = "profile"
JOB = "job"
RUN_LOG = "run_log"
LOCAL = "local"
SYNC = "sync"

TABLES = {
    "jobs": JOB,
    "job_skills": JOB,
    "applications": JOB,
    "application_proposals": JOB,
    "consent_events": JOB,
    "ats_scores": JOB,
    "tailoring_sessions": JOB,
    "qa_entries": JOB,
    "filled_answers": JOB,
    "base_resumes": PROFILE,
    "templates": PROFILE,
    "referrals": PROFILE,
    "kb_entities": PROFILE,
    "kb_points": PROFILE,
    "kb_documents": PROFILE,
    "kb_profile": PROFILE,
    "settings": PROFILE,
    # Split by resume_kind: base rows are profile; application rows follow their application.
    "resume_versions": "by_kind",
    "resume_lint_reports": "by_kind",
    "health_ask_answers": "by_kind",
    "health_gate_waivers": "by_kind",
    "kb_port_log": "by_kind",
    "agent_runs": RUN_LOG,
    # Content-addressed bullet caches stay local: each copy recomputes its own.
    "bullet_classifications": LOCAL,
    "bullet_rewrites": LOCAL,
    "bullet_disputes": LOCAL,
    "chat_sessions": LOCAL,
    "chat_messages": LOCAL,
    "chat_attachments": LOCAL,
    "autofill_runs": LOCAL,
    "autofill_field_observations": LOCAL,
    "autofill_mechanism_stats": LOCAL,
    "sync_state": SYNC,
    "sync_tombstones": SYNC,
    "sync_requests": SYNC,
    "alembic_version": SYNC,
}

LOCAL_SETTING_PREFIXES = ("sync.", "llm.capabilities.", "kb.seeded", "llm_library_proposals")


def _application_id(resume_key: str | None) -> UUID | None:
    if not isinstance(resume_key, str):
        return None
    try:
        return UUID(resume_key)
    except ValueError:
        return None


def _parent_job_id(
    session: Session,
    model: type[Application] | type[ApplicationProposal],
    identity: UUID | None,
) -> UUID | None:
    if identity is None:
        return None
    # The flush hook also sees children of parents not yet in the database.
    for parent in session.new:
        if isinstance(parent, model) and parent.id == identity:
            return parent.job_id
    parent = session.get(model, identity)
    return parent.job_id if parent is not None else None


def job_id_of(session: Session, obj: Base) -> UUID | None:
    """Resolve a job row's owner subtree, including pending parents, without flushing."""
    with session.no_autoflush:
        table = obj.__table__.name
        classification = TABLES[table]
        if classification == JOB:
            if table == "jobs":
                return obj.id
            if table == "consent_events":
                return _parent_job_id(session, ApplicationProposal, obj.proposal_id)
            if table == "qa_entries":
                return _parent_job_id(session, Application, obj.application_id)
            return obj.job_id
        if classification == "by_kind" and obj.resume_kind == "application":
            return _parent_job_id(session, Application, _application_id(obj.resume_key))
        return None


def is_profile_row(obj: Base) -> bool:
    """Profile data includes base-resume rows and excludes machine-local settings."""
    table = obj.__table__.name
    if table == "settings":
        return isinstance(obj.key, str) and not obj.key.startswith(LOCAL_SETTING_PREFIXES)
    classification = TABLES[table]
    return classification == PROFILE or (
        classification == "by_kind" and obj.resume_kind == "base"
    )
