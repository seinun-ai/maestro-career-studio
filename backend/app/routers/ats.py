from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.job import Job
from app.schemas.ats_score import AtsCandidatesRead, AtsRunRequest, AtsScoreRead
from app.services import ats_score, base_eligibility

router = APIRouter(prefix="/api/ats-scores", tags=["ats-scores"])


@router.post("", response_model=list[AtsScoreRead])
def run_ats_scores(payload: AtsRunRequest, db: Annotated[Session, Depends(get_db)]):
    if bool(payload.target_type) != bool(payload.target_id):
        raise HTTPException(
            status_code=422,
            detail="target_type and target_id must be provided together (or both omitted)",
        )
    try:
        if payload.target_type and payload.target_id:
            default_phase = "tailored" if payload.target_type == "application" else "base"
            rows = [
                ats_score.score_target(
                    payload.job_id,
                    payload.target_type,
                    payload.target_id,
                    phase=payload.phase or default_phase,
                    session=db,
                )
            ]
        else:
            rows = ats_score.score_all_bases(
                payload.job_id,
                session=db,
                include_other_countries=payload.include_other_countries,
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # Caller-owned commit (score_target/score_all_bases stage on our session).
    db.commit()
    return rows


@router.get("", response_model=list[AtsScoreRead])
def list_ats_scores(
    db: Annotated[Session, Depends(get_db)],
    job_id: Annotated[UUID, Query()],
    include_other_countries: Annotated[bool, Query()] = False,
):
    return ats_score.latest_scores(
        job_id, db, include_other_countries=include_other_countries
    )


@router.get("/candidates", response_model=AtsCandidatesRead)
def ats_candidates(
    db: Annotated[Session, Depends(get_db)],
    job_id: Annotated[UUID, Query()],
    include_other_countries: Annotated[bool, Query()] = False,
):
    """How the country rule treats this job: its country, which bases it skips,
    and whether the filter fell back to every base. With `include_other_countries`
    nothing is skipped, matching the scores asked for the same way."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    found = base_eligibility.candidates(db, job, include_other_countries=include_other_countries)
    return AtsCandidatesRead(
        job_country=found.job_country, fallback=found.fallback, skipped=found.skipped
    )
