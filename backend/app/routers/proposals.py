from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.application import Application
from app.models.application_proposal import ApplicationProposal
from app.models.job import Job
from app.models.qa_entry import QAEntry
from app.schemas.job import JobSummary
from app.schemas.proposal import (
    ApplicationSummaryForProposal,
    ProposalBulkResponse,
    ProposalBulkResult,
    ProposalBulkTransition,
    ProposalCreate,
    ProposalDetail,
    ProposalFunnelResponse,
    ProposalListResponse,
    ProposalReasonBody,
    ProposalRead,
    ProposalTransition,
)
from app.services import artifacts, auto_apply_settings, proposal_evidence
from app.services import proposals as svc

router = APIRouter(prefix="/api/proposals", tags=["proposals"])


def _job_summary(job: Job) -> JobSummary:
    return JobSummary.model_validate(job)


def _detail(db: Session, prop: ApplicationProposal) -> ProposalDetail:
    job = db.get(Job, prop.job_id)
    if job is None:
        raise HTTPException(404, detail="Job not found")

    app_summary = None
    qa_entries_data = []
    if prop.application_id is not None:
        app_row = db.get(Application, prop.application_id)
        if app_row is not None:
            app_summary = ApplicationSummaryForProposal(
                id=app_row.id,
                status=app_row.status,
                pdf_ready=bool(app_row.pdf_path),
            )
            qa_rows = db.scalars(
                select(QAEntry).where(QAEntry.application_id == app_row.id)
            ).all()
            qa_entries_data = [
                {
                    "id": str(q.id),
                    "kind": q.kind,
                    "prompt": q.prompt,
                    "answer": q.answer,
                    "created_at": q.created_at.isoformat() if q.created_at else None,
                }
                for q in qa_rows
            ]

    return ProposalDetail(
        id=prop.id,
        job_id=prop.job_id,
        application_id=prop.application_id,
        referral_id=prop.referral_id,
        status=prop.status,
        fit_json=prop.fit_json,
        plan_json=prop.plan_json,
        evidence_json=prop.evidence_json,
        intervention_json=prop.intervention_json,
        reason=prop.reason,
        expires_at=prop.expires_at,
        cap_reserved_at=prop.cap_reserved_at,
        created_at=prop.created_at,
        updated_at=prop.updated_at,
        job=_job_summary(job),
        application=app_summary,
        qa_entries=qa_entries_data,
    )


@router.post("", response_model=ProposalDetail)
def create_proposal(
    payload: ProposalCreate,
    db: Annotated[Session, Depends(get_db)],
    response: Response,
):
    job = db.get(Job, payload.job_id)
    if job is None:
        raise HTTPException(404, detail="Job not found")

    cfg = auto_apply_settings.get_settings(db)
    company = (job.company or "").strip().lower()

    if company and company in {c.strip().lower() for c in cfg.company_blocklist}:
        raise HTTPException(409, detail="company is blocklisted")

    open_prop = db.scalar(
        select(ApplicationProposal)
        .where(
            ApplicationProposal.job_id == payload.job_id,
            # svc.OPEN_STATUSES, never an inline literal: a duplicated tuple
            # here silently forked from the service when `accepted` landed, and
            # the first apply run minted duplicate proposals for triaged jobs.
            ApplicationProposal.status.in_(tuple(svc.OPEN_STATUSES)),
        )
        .order_by(ApplicationProposal.created_at.desc())
        .limit(1)
    )
    if open_prop is not None:
        # Idempotent resume: return the open proposal instead of 409. When the
        # caller supplies application_id and the proposal is still unlinked,
        # late-link (never relink if already set to a different application).
        if payload.application_id is not None:
            if (
                open_prop.application_id is not None
                and open_prop.application_id != payload.application_id
            ):
                raise HTTPException(
                    409, detail="proposal already linked to an application",
                )
            if open_prop.application_id is None:
                _validate_and_stamp_application(db, payload.application_id)
                open_prop.application_id = payload.application_id
                db.commit()
                db.refresh(open_prop)
        response.status_code = 200
        return _detail(db, open_prop)

    # Owner decision 2026-08-01 (design G3): a decline is scoped to that unique
    # posting and never implicates the company — the explicit blocklist above is
    # the only company-level gate. Deleting the rejected proposal is the reset.
    declined = db.scalar(
        select(ApplicationProposal.id)
        .where(
            ApplicationProposal.job_id == payload.job_id,
            ApplicationProposal.status == "rejected",
        )
        .limit(1)
    )
    if declined:
        raise HTTPException(
            409, detail="job was declined — delete the rejected proposal to re-propose",
        )

    if payload.application_id is not None:
        _validate_and_stamp_application(db, payload.application_id)

    prop = svc.create_proposal(
        db,
        job_id=payload.job_id,
        application_id=payload.application_id,
        referral_id=payload.referral_id,
        fit=payload.fit,
        plan=payload.plan,
    )
    response.status_code = 201
    return _detail(db, prop)


def _validate_and_stamp_application(db: Session, application_id: UUID) -> Application:
    app_row = db.get(Application, application_id)
    if app_row is None:
        raise HTTPException(404, detail="Application not found")
    # Being linked to a proposal is what defines the agent lane for an
    # application; the creation flows (from-base, quick-tailor) default to
    # source="user" and know nothing about proposals.
    app_row.source = "agent"
    return app_row


@router.get("", response_model=ProposalListResponse)
def list_proposals(
    db: Annotated[Session, Depends(get_db)],
    status: str | None = Query(default=None, description="one status or a comma-separated set"),
    limit: Annotated[int, Query(ge=1, le=500)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    svc.expire_stale(db)
    stmt = select(ApplicationProposal, Job).join(Job, Job.id == ApplicationProposal.job_id)
    if status is not None:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        stmt = stmt.where(ApplicationProposal.status.in_(statuses))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(ApplicationProposal.created_at.desc()).offset(offset).limit(limit)

    results = db.execute(stmt).all()
    items = [
        ProposalRead(
            id=prop.id,
            job_id=prop.job_id,
            application_id=prop.application_id,
            referral_id=prop.referral_id,
            status=prop.status,
            fit_json=prop.fit_json,
            plan_json=prop.plan_json,
            evidence_json=prop.evidence_json,
            intervention_json=prop.intervention_json,
            reason=prop.reason,
            expires_at=prop.expires_at,
            cap_reserved_at=prop.cap_reserved_at,
            created_at=prop.created_at,
            updated_at=prop.updated_at,
            job=_job_summary(job),
        )
        for prop, job in results
    ]
    return ProposalListResponse(items=items, total=total)


@router.post("/bulk-transition", response_model=ProposalBulkResponse)
def bulk_transition(payload: ProposalBulkTransition, db: Annotated[Session, Depends(get_db)]):
    """Mass triage: per-row guard checks, per-row ConsentEvent, honest per-id
    report — a mixed selection partially succeeds instead of all-or-nothing."""
    results = []
    for pid in payload.ids:
        prop = db.get(ApplicationProposal, pid)
        if prop is None:
            results.append(ProposalBulkResult(id=pid, ok=False, detail="not found"))
            continue
        try:
            svc.transition(db, prop, payload.status,
                           consent=payload.consent.model_dump(),
                           reason=payload.reason)
            results.append(ProposalBulkResult(id=pid, ok=True, status=prop.status))
        except svc.TransitionError as e:
            db.rollback()
            results.append(ProposalBulkResult(id=pid, ok=False, detail=str(e)))
    return ProposalBulkResponse(results=results)


@router.get("/funnel", response_model=ProposalFunnelResponse)
def get_proposals_funnel(db: Annotated[Session, Depends(get_db)]):
    svc.expire_stale(db)

    captured = db.scalar(
        select(func.count(Job.id)).where(Job.source == "agent")
    ) or 0

    prop_counts = dict(
        db.execute(
            select(ApplicationProposal.status, func.count(ApplicationProposal.id))
            .group_by(ApplicationProposal.status)
        ).all()
    )

    interviewing = db.scalar(
        select(func.count(Application.id)).where(
            Application.source == "agent",
            Application.status.in_(("interviewing", "offered", "accepted")),
        )
    ) or 0

    return ProposalFunnelResponse(
        captured=captured,
        proposed=prop_counts.get("pending_review", 0) + prop_counts.get("needs_decision", 0),
        accepted=prop_counts.get("accepted", 0),
        approved=prop_counts.get("approved", 0),
        cap=svc.cap_status(db),
        submitted=prop_counts.get("submitted", 0),
        interviewing=interviewing,
        rejected_proposals=prop_counts.get("rejected", 0),
        needs_human=prop_counts.get("needs_human", 0),
        expired=prop_counts.get("expired", 0),
    )


@router.get("/{proposal_id}", response_model=ProposalDetail)
def get_proposal(proposal_id: UUID, db: Annotated[Session, Depends(get_db)]):
    svc.expire_stale(db)
    prop = db.get(ApplicationProposal, proposal_id)
    if prop is None:
        raise HTTPException(404, detail="Proposal not found")
    return _detail(db, prop)


@router.delete("/{proposal_id}", status_code=204)
def delete_proposal(proposal_id: UUID, db: Annotated[Session, Depends(get_db)]):
    """Web-only housekeeping delete (design §3c). Deliberately NOT exposed as
    an MCP tool — the no-"delete"-tools invariant (SYSTEM §6) stands."""
    from pathlib import Path

    prop = db.get(ApplicationProposal, proposal_id)
    if prop is None:
        raise HTTPException(404, detail="Proposal not found")
    if prop.status in ("submitted", "submission_uncertain"):
        # These rows ARE the audit trail that an application was machine-
        # submitted (consent events + receipt evidence). Delete the linked
        # application first if the whole record must go.
        raise HTTPException(
            409,
            detail="cannot delete a submitted proposal — it is the submission audit trail",
        )
    # Staged artifact removal (SYSTEM §6): resolve files first, delete the row,
    # COMMIT, only then unlink. ConsentEvents go via the DB-level FK cascade.
    stale: list[Path] = []
    for item in prop.evidence_json or []:
        name = Path(str(item.get("path", ""))).name
        if not name:
            continue
        path = proposal_evidence.evidence_file_path(db, prop, name)
        if path is not None:
            stale.append(path)
    db.delete(prop)
    db.commit()
    artifacts.remove_files(stale)


@router.patch("/{proposal_id}", response_model=ProposalDetail)
def transition_proposal(
    proposal_id: UUID,
    payload: ProposalTransition,
    db: Annotated[Session, Depends(get_db)],
):
    prop = db.get(ApplicationProposal, proposal_id)
    if prop is None:
        raise HTTPException(404, detail="Proposal not found")
    try:
        if payload.status == "pending_review" and prop.status == "needs_decision":
            svc.record_decision(
                db,
                prop,
                fit=payload.fit or {},
                application_id=payload.application_id,
            )
            return _detail(db, prop)

        if payload.application_id is not None:
            if prop.application_id is not None and prop.application_id != payload.application_id:
                raise HTTPException(409, detail="proposal already linked to an application")
            _validate_and_stamp_application(db, payload.application_id)
            prop.application_id = payload.application_id
        if payload.fit is not None:
            fit = dict(prop.fit_json or {})
            fit.update(payload.fit)
            fit["decided_by"] = "user"
            prop.fit_json = fit
        svc.transition(
            db,
            prop,
            payload.status,
            consent=payload.consent.model_dump() if payload.consent else None,
            reason=payload.reason,
            intervention=payload.intervention,
            attested=payload.attested,
        )
    except svc.TransitionError as e:
        detail = str(e)
        if "already linked" in detail:
            raise HTTPException(409, detail="proposal already linked to an application") from e
        raise HTTPException(409, detail=detail) from e
    return _detail(db, prop)


@router.post("/{proposal_id}/request-decision", response_model=ProposalDetail)
def request_decision(
    proposal_id: UUID,
    payload: ProposalReasonBody,
    db: Annotated[Session, Depends(get_db)],
):
    prop = db.get(ApplicationProposal, proposal_id)
    if prop is None:
        raise HTTPException(404, detail="Proposal not found")
    try:
        svc.request_decision(db, prop, reason=payload.reason)
    except svc.TransitionError as e:
        raise HTTPException(409, detail=str(e)) from e
    return _detail(db, prop)


@router.post("/{proposal_id}/resume", response_model=ProposalDetail)
def resume_proposal(proposal_id: UUID, db: Annotated[Session, Depends(get_db)]):
    prop = db.get(ApplicationProposal, proposal_id)
    if prop is None:
        raise HTTPException(404, detail="Proposal not found")
    try:
        svc.resume_proposal(db, prop)
    except svc.TransitionError as e:
        raise HTTPException(409, detail=str(e)) from e
    return _detail(db, prop)


@router.post("/{proposal_id}/report-failure", response_model=ProposalDetail)
def report_failure(
    proposal_id: UUID,
    payload: ProposalReasonBody,
    db: Annotated[Session, Depends(get_db)],
):
    prop = db.get(ApplicationProposal, proposal_id)
    if prop is None:
        raise HTTPException(404, detail="Proposal not found")
    if not payload.reason:
        raise HTTPException(422, detail="reason is required")
    try:
        svc.report_failure(
            db, prop, reason=payload.reason, intervention=payload.intervention,
        )
    except svc.TransitionError as e:
        raise HTTPException(409, detail=str(e)) from e
    return _detail(db, prop)


@router.get("/{proposal_id}/final-review")
def get_final_review(proposal_id: UUID, db: Annotated[Session, Depends(get_db)]):
    prop = db.get(ApplicationProposal, proposal_id)
    if prop is None:
        raise HTTPException(404, detail="Proposal not found")
    return svc.get_final_review(db, prop)


@router.post("/{proposal_id}/evidence", status_code=201)
async def upload_evidence(
    proposal_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    step: int = Form(...),
    label: str = Form(...),
    kind: str = Form(...),
    file: UploadFile = File(...),
):
    prop = db.get(ApplicationProposal, proposal_id)
    if prop is None:
        raise HTTPException(404, detail="Proposal not found")
    if kind not in svc.EVIDENCE_KINDS:
        raise HTTPException(
            422,
            detail=f"kind must be one of {sorted(svc.EVIDENCE_KINDS)}",
        )

    content_type = (file.content_type or "").lower()
    if content_type not in ("image/png", "image/jpeg", "image/jpg"):
        raise HTTPException(415, detail="Unsupported media type; only image/png and image/jpeg are accepted")

    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, detail="File size exceeds maximum limit of 5 MB")

    ext = ".jpg" if content_type in ("image/jpeg", "image/jpg") else ".png"
    try:
        return proposal_evidence.save_evidence(
            db, prop, step=step, label=label, data=data, extension=ext, kind=kind,
        )
    except proposal_evidence.EvidenceError as e:
        raise HTTPException(409, detail=str(e)) from e
    except svc.TransitionError as e:
        raise HTTPException(409, detail=str(e)) from e


@router.get("/{proposal_id}/evidence/{name}")
def serve_evidence(proposal_id: UUID, name: str, db: Annotated[Session, Depends(get_db)]):
    prop = db.get(ApplicationProposal, proposal_id)
    if prop is None:
        raise HTTPException(404, detail="Proposal not found")

    path = proposal_evidence.evidence_file_path(db, prop, name)
    if path is None or not path.is_file():
        raise HTTPException(404, detail="Evidence file not found")

    return FileResponse(path)
