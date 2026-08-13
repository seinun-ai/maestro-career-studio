import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.tailoring_session import TailoringSession
from app.schemas.tailoring_session import (
    ResolutionsPatch,
    TailoringSessionCreate,
    TailoringSessionRead,
    TailorRequest,
    TailorResponse,
)
from app.services import application_render, ats_score, quick_tailor, tailoring_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tailoring-sessions", tags=["tailoring-sessions"])


def _get_or_404(db: Session, session_id: UUID) -> TailoringSession:
    row = db.get(TailoringSession, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Tailoring session not found: {session_id}")
    return row


@router.post("", response_model=TailoringSessionRead)
def create_tailoring_session(
    payload: TailoringSessionCreate, db: Annotated[Session, Depends(get_db)]
):
    try:
        return tailoring_session.create_session(
            payload.job_id, payload.base_resume, enrich=payload.enrich, session=db
        )
    except tailoring_session.HealthGateBlockedError as exc:
        # A failing fatal health gate on the base resume blocks tailoring (409).
        # Subclass of ValueError, so this must precede the generic 422 mapping.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("", response_model=list[TailoringSessionRead])
def list_tailoring_sessions(
    db: Annotated[Session, Depends(get_db)], job_id: Annotated[UUID, Query()]
):
    return list(
        db.scalars(
            select(TailoringSession)
            .where(TailoringSession.job_id == job_id)
            # id desc is a deterministic tiebreak for same-transaction timestamps
            .order_by(TailoringSession.created_at.desc(), TailoringSession.id.desc())
        )
    )


@router.get("/{session_id}", response_model=TailoringSessionRead)
def get_tailoring_session(session_id: UUID, db: Annotated[Session, Depends(get_db)]):
    row = _get_or_404(db, session_id)
    # Transient annotation: lets the gap page show a stale banner up front
    # instead of the user discovering it via a 409 on save/tailor.
    if row.status == "open":
        row.stale_reason = tailoring_session.staleness_reason(row, db)
    return row


@router.patch("/{session_id}", response_model=TailoringSessionRead)
def patch_resolutions(
    session_id: UUID, payload: ResolutionsPatch, db: Annotated[Session, Depends(get_db)]
):
    _get_or_404(db, session_id)
    try:
        return tailoring_session.save_resolutions(
            session_id,
            [item.model_dump() for item in payload.resolutions],
            session=db,
            replace=payload.replace,
            user_prompt=payload.user_prompt,
        )
    except tailoring_session.StaleSessionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except tailoring_session.SessionNotOpenError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{session_id}/close", response_model=TailoringSessionRead)
def close_tailoring_session(session_id: UUID, db: Annotated[Session, Depends(get_db)]):
    """Abandon an open session — the explicit exit for "changed my mind" flows
    (e.g. "use base as-is"), so open sessions stop accumulating forever."""
    _get_or_404(db, session_id)
    try:
        return tailoring_session.close_session(session_id, session=db)
    except tailoring_session.SessionNotOpenError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{session_id}/apply-profile", response_model=TailoringSessionRead)
def apply_profile(session_id: UUID, db: Annotated[Session, Depends(get_db)]):
    """Fill every UNRESOLVED gap from the saved quick-tailor profile, then stop.

    Deterministic and LLM-free: quick_tailor.plan_resolutions over the frozen
    gaps, routed through save_resolutions so the honesty gate holds. This is
    the agent-facing half of quick tailor — the MCP path calls this, reads
    what was planned, and authors its own typed ops, so the saved resolutions
    and the applied ops cannot disagree (SYSTEM.md §11 item 13, the weakness
    that made a combined fill+tailor call unsafe for an agent caller). The
    /tailor route's apply_profile flag is unchanged and still serves the web
    app's one-call path.

    The discarded return value is DELIBERATE, and incurs a debt the MCP
    workflow layer must pay: fill_checkpoint_session returns the profile's
    standing-instruction fallback, which both other quick-tailor paths pass
    into tailor() as user_prompt. Persisting it here is wrong — the web path
    keeps it transient on purpose — so the MCP caller must read the profile
    and pass the instruction into its own tailor_session call. Left unpaid,
    quick tailor over MCP would ignore a setting the web app obeys, which is
    the "one saved setting must not mean two things" trap §4 warns about.
    """
    row = _get_or_404(db, session_id)
    try:
        quick_tailor.fill_checkpoint_session(row, session=db)
    except (
        tailoring_session.StaleSessionError,
        tailoring_session.SessionNotOpenError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        # Same mapping patch_resolutions uses for this service's plain
        # ValueErrors (unknown gap_id, bad placement target, an unloadable
        # base on a legacy row with no base_content_hash, which staleness
        # treats as fresh). Without it those surface as a 500 to an agent
        # caller, which reads as "the server is broken" rather than "your
        # session is unusable".
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return row


@router.post("/{session_id}/tailor", response_model=TailorResponse)
def tailor_session(
    session_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    payload: TailorRequest | None = None,
):
    """Run the tailor pipeline: resolutions -> LLM edit ops -> application -> score."""
    row = _get_or_404(db, session_id)
    effective_prompt = payload.user_prompt if payload else None

    # "Quick tailor" on the gap page: quick_tailor.fill_checkpoint_session owns
    # the fill-from-profile composition and the instruction-fallback rule (the
    # same rule the one-shot endpoint applies — one saved setting must not mean
    # two things); this branch only maps its typed exceptions to 409.
    if payload and payload.apply_profile:
        try:
            effective_prompt = quick_tailor.fill_checkpoint_session(
                row, session=db, request_prompt=effective_prompt
            )
        except tailoring_session.StaleSessionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except tailoring_session.SessionNotOpenError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        row = tailoring_session.tailor(
            session_id,
            session=db,
            user_prompt=effective_prompt,
            ops=payload.ops if payload else None,
        )
    except tailoring_session.StaleSessionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except tailoring_session.SessionNotOpenError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        # LLM/validation failures surface as 400 (mirrors retry_application_ai);
        # nothing was persisted, the session stays open with resolutions intact.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Embed before/after so the UI can show the win immediately. The base row
    # exists from session creation; the tailored row was just written. A compare
    # failure here (e.g. engine/config version mismatch with a stale base row)
    # must not mask the already-committed tailor — report success with the error.
    compare = None
    compare_error = None
    try:
        compare = ats_score.compare(row.application_id, session=db)
    except ValueError as exc:
        logger.warning("post-tailor compare failed for session %s: %s", session_id, exc)
        compare_error = (
            f"tailoring succeeded; scores not comparable: {exc} — re-run scoring "
            f"and GET /api/applications/{row.application_id}/ats-compare"
        )

    # Render, exactly as the one-shot path does (quick_tailor.run_for_job).
    # These are the same pipeline reached two ways, and only that one rendered:
    # in the app a tailored draft arrived with no PDF, so seeing it meant
    # pressing Save on an unedited draft purely to trigger a compile.
    #
    # Deliberately AFTER the compare and outside its failure branch — a compare
    # failure must not also cost the PDF, which is why compare no longer returns
    # early. Same degrade-not-fail policy as the one-shot: the tailor is already
    # committed, and render_resume persists `application.render_error` itself,
    # which is where the studio reads the reason.
    pdf_ready = True
    try:
        application_render.render_resume(db, row.application_id)
    except Exception as exc:
        logger.warning("post-tailor render failed for session %s: %s", session_id, exc)
        pdf_ready = False

    return {
        "session": row,
        "compare": compare,
        "compare_error": compare_error,
        "pdf_ready": pdf_ready,
    }
