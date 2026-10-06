"""Every table's sync class (design Part A + amendments). A new table MUST be added here:
test_every_table_is_classified fails otherwise.
"""

from uuid import UUID

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import get_history

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

LOCAL_SETTING_PREFIXES = ("sync.", "llm.capabilities.", "kb.seeded")


def _application_id(resume_key: str | None) -> UUID | None:
    if not isinstance(resume_key, str):
        return None
    try:
        return UUID(resume_key)
    except ValueError:
        return None


def pending_parents(session: Session) -> dict:
    """Index pending identities once; callers may reuse it for a whole flush."""
    return {(type(obj), obj.id): obj for obj in session.new
            if getattr(obj, "id", None) is not None}


def _parent_job_id(session: Session, model: type, identity: UUID | None, parents: dict) -> UUID | None:
    if identity is None:
        return None
    parent = parents.get((model, identity))
    if parent is None:
        parent = session.get(model, identity)
    return parent.job_id if parent is not None else None


def _link_of(obj: Base) -> tuple[str, type | None] | None:
    table = obj.__table__.name
    if table == "consent_events":
        return "proposal_id", ApplicationProposal
    if table == "qa_entries":
        return "application_id", Application
    if TABLES.get(table) == "by_kind":
        return "resume_key", Application
    if TABLES.get(table) == JOB and table != "jobs":
        return "job_id", None
    return None


def _resolve_link(session: Session, link: tuple, value, parents: dict) -> UUID | None:
    _, model = link
    if model is None:
        return value
    identity = value if isinstance(value, UUID) else _application_id(value)
    return _parent_job_id(session, model, identity, parents)


def job_id_of(session: Session, obj: Base, parents: dict | None = None) -> UUID | None:
    """Resolve a job row's owner subtree, including pending parents, without flushing."""
    with session.no_autoflush:
        if obj.__table__.name == "jobs":
            return obj.id
        if TABLES.get(obj.__table__.name) == "by_kind" and obj.resume_kind != "application":
            return None
        link = _link_of(obj)
        if link is None:
            return None
        index = pending_parents(session) if parents is None else parents
        return _resolve_link(session, link, getattr(obj, link[0]), index)


def _previous_values(session: Session, obj: Base, column: str) -> list:
    history = get_history(obj, column)
    if history.deleted or not history.has_changes():
        return list(history.deleted)
    state = inspect(obj)
    if state.identity is None:
        return []
    # Expire-on-commit can leave an overwritten FK unloaded: history has no old value.
    statement = select(getattr(type(obj), column)).where(
        *(key == value for key, value in zip(state.mapper.primary_key, state.identity))
    )
    return [session.scalar(statement)]


def job_ids_of(session: Session, obj: Base, parents: dict | None = None) -> set[UUID]:
    """Both job subtrees of a moved row, including an unloaded previous link."""
    with session.no_autoflush:
        index = pending_parents(session) if parents is None else parents
        current = job_id_of(session, obj, index)
        result = {current} if current is not None else set()
        link = _link_of(obj)
        if obj not in session.dirty or link is None:
            return result
        by_kind = TABLES.get(obj.__table__.name) == "by_kind"
        old_kinds = _previous_values(session, obj, "resume_kind") if by_kind else []
        if by_kind and obj.resume_kind != "application" and "application" not in old_kinds:
            return result
        previous = _previous_values(session, obj, link[0])
        if "application" in old_kinds and not previous:
            previous = [getattr(obj, link[0])]
        for value in previous:
            identity = _resolve_link(session, link, value, index)
            if identity is not None:
                result.add(identity)
        return result


def is_profile_row(obj: Base) -> bool:
    """Profile data includes base-resume rows and excludes machine-local settings."""
    table = obj.__table__.name
    if table == "settings":
        return isinstance(obj.key, str) and not obj.key.startswith(LOCAL_SETTING_PREFIXES)
    classification = TABLES.get(table)
    kind = "base" if table == "kb_port_log" and obj.resume_kind is None else getattr(obj, "resume_kind", None)
    return classification == PROFILE or (classification == "by_kind" and kind == "base")
