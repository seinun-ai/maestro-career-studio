"""Provenance + proposal-ledger model tests."""
import uuid

from app.models.application import Application
from app.models.job import Job


def _mk_job(db_session, **kw):
    job = Job(raw_text="jd text", raw_text_hash=uuid.uuid4().hex + uuid.uuid4().hex[:32], **kw)
    db_session.add(job)
    db_session.commit()
    return job


def test_job_and_application_source_default_to_user(db_session):
    job = _mk_job(db_session)
    app_row = Application(job_id=job.id, base_resume="hybrid")
    db_session.add(app_row)
    db_session.commit()
    db_session.refresh(job)
    db_session.refresh(app_row)
    assert job.source == "user"
    assert app_row.source == "user"


def test_proposal_row_roundtrip_with_consent(db_session):
    from app.models.application_proposal import PROPOSAL_STATUSES, ApplicationProposal
    from app.models.consent_event import ConsentEvent

    job = _mk_job(db_session, source="agent", company="Acme")
    prop = ApplicationProposal(
        job_id=job.id,
        status="pending_review",
        fit_json={"chosen_base": "ml_eng", "decided_by": "auto"},
        plan_json={"summary": "k8s -> skills"},
    )
    db_session.add(prop)
    db_session.commit()
    db_session.add(ConsentEvent(
        proposal_id=prop.id, action="approved", channel="chat",
        evidence_manifest_json=[{"path": "step-01.png", "sha256": "x"}],
    ))
    db_session.commit()
    assert prop.status in PROPOSAL_STATUSES
    assert db_session.query(ConsentEvent).filter_by(proposal_id=prop.id).count() == 1

