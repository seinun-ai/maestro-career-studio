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
from app.services import ats_score, quick_tailor, tailoring_session

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
    try:
        compare = ats_score.compare(row.application_id, session=db)
    except ValueError as exc:
        logger.warning("post-tailor compare failed for session %s: %s", session_id, exc)
        return {
            "session": row,
            "compare": None,
            "compare_error": (
                f"tailoring succeeded; scores not comparable: {exc} — re-run scoring "
                f"and GET /api/applications/{row.application_id}/ats-compare"
            ),
        }
    return {"session": row, "compare": compare}
