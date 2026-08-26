import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.application import Application
from app.models.application_proposal import ApplicationProposal
from app.models.ats_score import AtsScore
from app.models.job import Job
from app.models.tailoring_session import TailoringSession
from app.schemas.application import (
    ApplicationDetail,
    ApplicationFromBase,
    ApplicationPatch,
    ApplicationRead,
    ApplicationSummary,
    RenderResult,
)
from app.schemas.ats_score import AtsCompareRead
from app.schemas.formatting import validate_formatting
from app.schemas.job import JobRead
from app.schemas.resume import ResumeData
from app.schemas.resume_edit import ResumeEditRequest
from app.services import (
    application_render,
    artifacts,
    ats_score,
    base_resume_data,
    coherence_check,
    pdf_preview,
    resume_diff,
    resume_ops,
)
from app.services import proposals as proposal_svc
from app.services.application_writes import stage_resume_update
from app.services.resume_edit import ContentChangedError, apply_edits
from app.schemas.proposal import AssertOpenProposalBody


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/applications", tags=["applications"])


def _detail(
    application: Application,
    db: Session,
    *,
    applied: list[dict] | None = None,
) -> ApplicationDetail:
    base = ApplicationRead.model_validate(application).model_dump()
    job = db.get(Job, application.job_id)
    return ApplicationDetail(
        **base,
        job=JobRead.model_validate(job) if job else None,
        applied=applied,
    )


@router.post("/from-base", response_model=ApplicationRead)
def create_application_from_base(
    payload: ApplicationFromBase, db: Annotated[Session, Depends(get_db)]
):
    """Create or update an application by applying typed edit ops to a base resume.

    The server loads the stored base, applies only the supplied ops, validates,
    and stores the result as customized_json. Reuse policy matches tailor():
    with no application_id, the job's newest application for this base resume
    is updated in place (the job page only ever surfaces the newest application,
    so a second insert would strand the first — audit C2/C9). Pass
    application_id to target a specific application explicitly.
    """
    if db.get(Job, payload.job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if payload.application_id is not None:
        application = db.get(Application, payload.application_id)
        if application is None:
            raise HTTPException(status_code=404, detail="Application not found")
    else:
        application = db.scalar(
            select(Application)
            .where(
                Application.job_id == payload.job_id,
                Application.base_resume == payload.base_resume,
            )
            .order_by(Application.created_at.desc())
            .limit(1)
        )

    try:
        base = base_resume_data.load_base_resume(payload.base_resume, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        customized = apply_edits(base, payload.ops)
    except ContentChangedError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if application is not None:
        application.job_id = payload.job_id
        application.base_resume = payload.base_resume
        if payload.user_prompt is not None:
            application.user_prompt = payload.user_prompt.strip() or None
        summary = f"Rebuilt from base resume {payload.base_resume}"
    else:
        application = Application(
            job_id=payload.job_id,
            base_resume=payload.base_resume,
            status="draft",
            user_prompt=(payload.user_prompt or "").strip() or None,
        )
        db.add(application)
        summary = f"Created from base resume {payload.base_resume}"
    stale, _ = stage_resume_update(
        db, application, customized, source="import", summary=summary
    )
    db.commit()
    db.refresh(application)
    artifacts.remove_files(stale)

    # Best-effort auto-score (base upserts, tailored appends). The application
    # is already committed, so NO scoring failure — expected (job without
    # extracted skills -> ValueError) or unexpected (DB error mid-commit,
    # engine bug) — may turn a successful creation into a 500: MCP callers
    # would retry and duplicate the application.
    try:
        # The base row is an upsert singleton the ATS panel already creates on
        # first visit; re-running the whole engine for it here was pure
        # redundancy (audit C20). Score it only when genuinely missing.
        has_base_row = db.scalar(
            select(AtsScore.id).where(
                AtsScore.job_id == payload.job_id,
                AtsScore.target_type == "base_resume",
                AtsScore.target_id == payload.base_resume,
                AtsScore.phase == "base",
            )
        )
        if has_base_row is None:
            ats_score.score_target(
                payload.job_id, "base_resume", payload.base_resume, phase="base", session=db
            )
        ats_score.score_target(
            payload.job_id, "application", str(application.id), phase="tailored", session=db
        )
        db.commit()  # caller-owned commit: score_target stages on our session
    except Exception as exc:
        db.rollback()  # a failed flush/commit leaves the session in
        # PendingRollback state; serializing `application` would raise
        logger.warning("ATS auto-score skipped for application %s: %s", application.id, exc)

    return application


@router.get("", response_model=list[ApplicationSummary])
def list_applications(
    db: Annotated[Session, Depends(get_db)],
    status: str | None = None,
    role_category: str | None = None,
    created_after: Annotated[datetime | None, Query()] = None,
    created_before: Annotated[datetime | None, Query()] = None,
    source: Literal["user", "agent"] | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    # Always join the job: the tracker shows company/title on every row, and
    # joining here removes the frontend's third query (full jobs list fetched
    # only to hydrate names client-side — audit C7).
    stmt = select(Application, Job).join(Job, Job.id == Application.job_id)
    if role_category:
        stmt = stmt.where(Job.role_category == role_category)
    if status:
        stmt = stmt.where(Application.status == status)
    if source:
        stmt = stmt.where(Application.source == source)
    if created_after:
        stmt = stmt.where(Application.created_at >= created_after)
    if created_before:
        stmt = stmt.where(Application.created_at <= created_before)
    stmt = stmt.order_by(Application.created_at.desc()).offset(offset).limit(limit)
    summaries: list[ApplicationSummary] = []
    for application, job in db.execute(stmt):
        summary = ApplicationSummary.model_validate(application)
        summary.job_title = job.title
        summary.job_company = job.company
        summary.job_location = job.location
        summaries.append(summary)
    return summaries


@router.get("/{application_id}/ats-compare", response_model=AtsCompareRead)
def compare_application_ats(application_id: UUID, db: Annotated[Session, Depends(get_db)]):
    try:
        return ats_score.compare(application_id, session=db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{application_id}/resume-diff")
def get_application_resume_diff(
    application_id: UUID, db: Annotated[Session, Depends(get_db)]
):
    """Structural base→tailored diff with provenance labels (design §4.5).

    404 unknown app; 409 when ``customized_json`` is empty (nothing tailored yet).
    Attributes hunks via the newest ``TailoringSession`` for this application
    (none → all-``llm``).
    """
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    if not application.customized_json:
        raise HTTPException(
            status_code=409,
            detail="Application has no tailored resume yet",
        )
    try:
        base = base_resume_data.load_base_resume(application.base_resume, session=db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    session_row = db.scalars(
        select(TailoringSession)
        .where(TailoringSession.application_id == application_id)
        .order_by(TailoringSession.created_at.desc(), TailoringSession.id.desc())
        .limit(1)
    ).first()

    hunks = resume_diff.diff_resume(base, application.customized_json)
    resolutions = session_row.resolutions_json if session_row is not None else []
    labeled = resume_diff.attribute(hunks, resolutions)
    return {
        "hunks": labeled,
        "session_id": str(session_row.id) if session_row is not None else None,
    }


@router.post("/{application_id}/coherence-check")
def coherence_check_application(
    application_id: UUID, db: Annotated[Session, Depends(get_db)]
):
    """Read-only coherence lint over the tailored resume (design §4.4,
    2026-08-12). Three groups: ``flags`` (LLM, changed loci only),
    ``hygiene`` (deterministic resume_lint rules, base-inherited defects
    suppressed), ``gates`` (structural gates against the tailored artifact).
    Returns proposals only; applying one is a normal studio edit. Best-effort
    per group: a failure degrades that group to empty, never an error."""
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    if not application.customized_json:
        raise HTTPException(
            status_code=409,
            detail="Application has no tailored resume yet",
        )
    try:
        base = base_resume_data.load_base_resume(application.base_resume, session=db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return coherence_check.run(base, application.customized_json, db, application.template_id)


@router.get("/{application_id}", response_model=ApplicationDetail)
def get_application(application_id: UUID, db: Annotated[Session, Depends(get_db)]):
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return _detail(application, db)


@router.patch("/{application_id}", response_model=ApplicationRead)
def patch_application(
    application_id: UUID,
    payload: ApplicationPatch,
    db: Annotated[Session, Depends(get_db)],
):
    """Patch application fields; a supplied ``customized_json`` is stored
    canonically.

    ``customized_json`` is validated AND normalized through
    ``ResumeData.model_validate(...).model_dump()`` before persistence, rather
    than storing the caller's raw dict. This converges with the base-resume PUT
    and typed-edit paths so unknown junk keys can no longer half-survive here
    (they are dropped) while every declared field — including ``extra_sections``
    and its defaults — is filled in consistently across write paths.
    """
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")

    fields = payload.model_fields_set
    stale: list[Path] = []
    for field in fields:
        if field == "customized_json":
            continue  # handled below via the shared write-tail
        # `formatting` maps to the `formatting_json` column, not a same-named attr.
        if field == "formatting":
            try:
                application.formatting_json = validate_formatting(payload.formatting)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            continue
        setattr(application, field, getattr(payload, field))

    if "customized_json" in fields:
        if payload.customized_json is None:
            # Explicit null clears the draft (and its now-stale artifacts).
            stale = artifacts.stage_resume_artifact_removal(application)
            application.customized_json = None
        else:
            # Same structural validation every other write path gets via
            # apply_edits (audit C4) — a malformed draft must not reach storage.
            # Store the NORMALIZED dump (not the raw dict) so unknown keys are
            # dropped and declared defaults (incl. extra_sections) are filled,
            # matching base-resume PUT / typed edits.
            try:
                normalized = ResumeData.model_validate(
                    payload.customized_json
                ).model_dump(mode="json")
            except ValidationError as e:
                # include_context=False: custom validators (e.g. extra_sections
                # reserved/duplicate-key checks) raise ValueError, whose object
                # lands in ctx and is not JSON-serializable as an HTTPException
                # detail. The human `msg` is retained.
                raise HTTPException(
                    status_code=422, detail=e.errors(include_context=False)
                ) from e
            stale, _ = stage_resume_update(
                db, application, normalized, source="form_edit"
            )

    # Keep applied_at in sync with the status transition, unless the caller
    # explicitly set applied_at in this same PATCH (respect their value).
    # Any stage that implies a submitted application (applied and everything
    # after it on the pipeline) stamps the date once if unset — jumping
    # straight from draft to interviewing implies you applied (review
    # finding). Dropping back to "draft" clears it; rejected/withdrawn
    # preserve whatever is there (they don't imply an application happened).
    if "status" in fields and "applied_at" not in fields:
        if application.status in ("applied", "interviewing", "offered", "accepted"):
            if application.applied_at is None:
                application.applied_at = datetime.now(UTC)
        elif application.status == "draft":
            application.applied_at = None

    # User override (2026-08-01): marking the application applied+ means they
    # completed it themselves — resolve any open proposal on the JOB (linked or
    # not; one open proposal per job) instead of leaving it squatting in the
    # triage/queued lanes. Close as posting-scoped decline with an honest
    # consent event; this also releases an approved proposal's cap slot and,
    # via the declined-job guard, stops the hunt re-proposing a posting the
    # user already applied to. Application rejected/withdrawn deliberately do
    # NOT close proposals — they don't imply an application happened.
    if "status" in fields and application.status in (
        "applied", "interviewing", "offered", "accepted",
    ):
        open_props = db.scalars(
            select(ApplicationProposal).where(
                ApplicationProposal.job_id == application.job_id,
                ApplicationProposal.status.in_(tuple(proposal_svc.OPEN_STATUSES)),
            )
        ).all()
        for prop in open_props:
            try:
                proposal_svc.transition(
                    db, prop, "rejected",
                    consent={
                        "channel": "frontend",
                        "note": "user marked the application applied",
                    },
                    reason="applied manually",
                )
            except proposal_svc.TransitionError:
                # A concurrent transition beat us to a terminal state; the
                # user's status change must not fail over ledger housekeeping.
                continue

    db.commit()
    db.refresh(application)
    artifacts.remove_files(stale)
    return application


@router.patch("/{application_id}/edits", response_model=ApplicationDetail)
def edit_application_resume(
    application_id: UUID,
    payload: ResumeEditRequest,
    db: Annotated[Session, Depends(get_db)],
):
    """Apply typed edit ops to an existing application's customized_json (or base resume if customized_json is None)."""
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")

    baseline = application.customized_json
    if baseline is None:
        try:
            baseline = base_resume_data.load_base_resume(application.base_resume, db)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        application, _, applied = resume_ops.edit_application(
            db, application, payload.ops, baseline=baseline, source="edit_ops"
        )
    except ContentChangedError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _detail(application, db, applied=applied)


def _truncate_detail(text: str, limit: int = 12000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...(truncated)"


@router.delete("/{application_id}", status_code=204)
def delete_application(application_id: UUID, db: Annotated[Session, Depends(get_db)]):
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    files = artifacts.collect_application_files(application)
    db.delete(application)
    db.commit()
    artifacts.remove_files(files)


@router.post("/{application_id}/materialize-resume", response_model=ApplicationDetail)
def materialize_application_resume(
    application_id: UUID, db: Annotated[Session, Depends(get_db)]
):
    """Snapshot the application's base resume into ``customized_json``.

    The legacy suggestions/decisions merge is gone; this now simply (re)builds
    the tailored-resume draft from the stored base so the editor has a starting
    point. Existing customized_json is replaced.
    """
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")

    try:
        snapshot = base_resume_data.load_base_resume(application.base_resume, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    stale, _ = stage_resume_update(
        db,
        application,
        snapshot,
        source="import",
        summary=f"Materialized from base resume {application.base_resume}",
    )
    db.commit()
    db.refresh(application)
    artifacts.remove_files(stale)
    return _detail(application, db)


@router.post("/{application_id}/render", response_model=RenderResult)
def render_application(
    application_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    template_id: str | None = None,
):
    """Thin HTTP adapter over ``application_render.render_resume``, which owns
    the pipeline and persists ``application.render_error`` on failure — this
    function only maps exception types to statuses."""
    try:
        source_path, pdf_path, doc = application_render.render_resume(
            db, application_id, template_id=template_id
        )
    # ValidationError MUST stay above the ValueError clause: pydantic v2's
    # ValidationError subclasses ValueError, so reordering would silently turn
    # 422s into 400s (no test covers that path).
    except ValidationError as e:
        raise HTTPException(
            status_code=422, detail=e.errors(include_context=False)
        ) from e
    # Template resolution is tolerant now (a stale/deleted/draft template_id
    # falls back to the default in render_tex), so it no longer raises here.
    # ValueError sources that DO reach here: a missing/broken base resume from
    # load_base_resume, and TemplateMissingExtraSectionsError (an extras-bearing
    # resume routed through a template that cannot render custom sections) —
    # both are user-actionable, so map to a clean 400 with the message (not the
    # generic-Exception 500 below). LookupError stays mapped to 404.
    except (LookupError, ValueError) as e:
        status = 404 if isinstance(e, LookupError) else 400
        raise HTTPException(status_code=status, detail=str(e)) from e
    except Exception as e:
        # render_error is already persisted; the render still returns 500 (the
        # caller asked to render, and failed).
        raise HTTPException(
            status_code=500,
            detail=_truncate_detail(str(e)),
        ) from e
    return RenderResult(
        tex_path=str(source_path),
        pdf_path=str(pdf_path),
        resolved_template_id=doc.resolved_template_id,
        resolved_engine=doc.engine,
        template_fallback=(
            template_id is not None and doc.resolved_template_id != template_id
        ),
    )


@router.get("/{application_id}/preview/pages")
def get_preview_manifest(application_id: UUID, db: Annotated[Session, Depends(get_db)]):
    application = db.get(Application, application_id)
    if (
        application is None
        or not application.pdf_path
        or not Path(application.pdf_path).exists()
    ):
        raise HTTPException(status_code=404, detail="PDF not found")
    pages = pdf_preview.ensure_page_images(Path(application.pdf_path))
    return {
        "page_count": len(pages),
        "rendered_at": application.updated_at,
        "render_error": application.render_error,
    }


@router.get("/{application_id}/preview/page/{page}")
def get_preview_page(
    application_id: UUID, page: int, db: Annotated[Session, Depends(get_db)]
):
    application = db.get(Application, application_id)
    if (
        application is None
        or not application.pdf_path
        or not Path(application.pdf_path).exists()
    ):
        raise HTTPException(status_code=404, detail="PDF not found")
    path = pdf_preview.pages_dir(Path(application.pdf_path)) / f"page-{page}.png"
    if not path.exists():
        pages = pdf_preview.ensure_page_images(Path(application.pdf_path))
        if page < 1 or page > len(pages):
            raise HTTPException(status_code=404, detail="Page not found")
        path = pages[page - 1]
    return FileResponse(path, media_type="image/png")


@router.get("/{application_id}/pdf")
def get_application_pdf(application_id: UUID, db: Annotated[Session, Depends(get_db)]):
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    if not application.pdf_path or not Path(application.pdf_path).exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(
        application.pdf_path,
        media_type="application/pdf",
        filename=Path(application.pdf_path).name,
        content_disposition_type="inline",
    )


@router.post("/{application_id}/assert-open-proposal")
def assert_open_proposal(
    application_id: UUID,
    payload: AssertOpenProposalBody,
    db: Annotated[Session, Depends(get_db)],
):
    """P1 gate for agent-sourced jobs: refuse execute helpers without an open proposal."""
    try:
        prop = proposal_svc.require_open_proposal_for_application(
            db, application_id, op=payload.op,
        )
    except proposal_svc.TransitionError as e:
        detail = str(e)
        if detail == "application not found":
            raise HTTPException(404, detail="Application not found") from e
        raise HTTPException(409, detail=detail) from e
    return {
        "ok": True,
        "proposal_id": str(prop.id) if prop is not None else None,
        "op": payload.op,
    }
