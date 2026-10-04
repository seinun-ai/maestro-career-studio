"""The answer receipt over HTTP (`services/filled_answers.py`). Same `/api/jobs` prefix as
`routers/jobs.py`; the two-segment paths cannot collide with its `/{job_id}` routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.job import Job
from app.schemas.filled_answers import FilledAnswersCreate, FilledAnswersPosted, FilledAnswersRead
from app.services import filled_answers

router = APIRouter(prefix="/api/jobs", tags=["filled-answers"])


def _job(db: Session, job_id: UUID) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/filled-answers", response_model=FilledAnswersPosted, status_code=201)
def post_filled_answers(
    job_id: UUID, payload: FilledAnswersCreate, db: Annotated[Session, Depends(get_db)]
):
    job = _job(db, job_id)
    try:
        return filled_answers.record(db, job, payload)
    except filled_answers.ApplicationMismatch as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{job_id}/filled-answers", response_model=FilledAnswersRead)
def get_filled_answers(job_id: UUID, db: Annotated[Session, Depends(get_db)]):
    return filled_answers.receipt(db, _job(db, job_id))
