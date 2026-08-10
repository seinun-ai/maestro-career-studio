from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.application import Application
from app.models.base_resume import BaseResume
from app.schemas.resume_version import (
    ResumeVersionDetail,
    ResumeVersionLabelPatch,
    ResumeVersionSummary,
)
from app.services import base_resume_render
from app.services import resume_versions as service
from app.services.artifacts import remove_files, stage_resume_artifact_removal

router = APIRouter(prefix="/api/resume-versions", tags=["resume-versions"])

Kind = Literal["base", "application"]


def _detail(row, diff: list[dict]) -> ResumeVersionDetail:
    return ResumeVersionDetail(
        **ResumeVersionSummary.model_validate(row).model_dump(),
        snapshot=row.snapshot,
        diff=diff,
    )


def _get_version_or_404(db: Session, kind: Kind, key: str, number: int):
    row = service.get_version(db, kind, key, number)
    if row is None:
        raise HTTPException(status_code=404, detail="Version not found")
    return row


@router.get("/{kind}/{key}", response_model=list[ResumeVersionSummary])
def list_versions(kind: Kind, key: str, db: Annotated[Session, Depends(get_db)]):
    return [
        ResumeVersionSummary.model_validate(row) for row in service.get_versions(db, kind, key)
    ]


@router.get("/{kind}/{key}/{number}", response_model=ResumeVersionDetail)
def get_version(kind: Kind, key: str, number: int, db: Annotated[Session, Depends(get_db)]):
    row = _get_version_or_404(db, kind, key, number)
    parent = None
    if row.parent_version_id is not None:
        parent = db.get(service.ResumeVersion, row.parent_version_id)
    diff = service.diff_versions(parent.snapshot if parent else None, row.snapshot)
    return _detail(row, diff)


@router.get("/{kind}/{key}/{number}/diff", response_model=list[dict])
def diff_version(
    kind: Kind,
    key: str,
    number: int,
    db: Annotated[Session, Depends(get_db)],
    against: int | None = None,
):
    """Diff version `number` against `against` (defaults to its parent)."""
    row = _get_version_or_404(db, kind, key, number)
    if against is not None:
        other = _get_version_or_404(db, kind, key, against)
        return service.diff_versions(other.snapshot, row.snapshot)
    parent = (
        db.get(service.ResumeVersion, row.parent_version_id)
        if row.parent_version_id is not None
        else None
    )
    return service.diff_versions(parent.snapshot if parent else None, row.snapshot)


@router.post("/{kind}/{key}/{number}/restore", response_model=ResumeVersionSummary)
def restore_version(
    kind: Kind, key: str, number: int, db: Annotated[Session, Depends(get_db)]
):
    """Copy a past version's snapshot into the live resume; history is append-only."""
    try:
        snapshot, version = service.restore(db, kind, key, number)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    if kind == "base":
        row = db.get(BaseResume, key)
        if row is None:
            raise HTTPException(status_code=404, detail="Base resume not found")
        row.data_json = snapshot
        db.commit()
        from app.routers.base_resumes import _write_json_file

        _write_json_file(key, snapshot)
        base_resume_render.render_base_resume(key, db)
    else:
        try:
            application_id = UUID(key)
        except ValueError as e:
            raise HTTPException(status_code=400, detail="Invalid application id") from e
        application = db.get(Application, application_id)
        if application is None:
            raise HTTPException(status_code=404, detail="Application not found")
        application.customized_json = snapshot
        stale = stage_resume_artifact_removal(application)
        db.commit()
        remove_files(stale)

    db.refresh(version)
    return ResumeVersionSummary.model_validate(version)


@router.patch("/{kind}/{key}/{number}", response_model=ResumeVersionSummary)
def set_version_label(
    kind: Kind,
    key: str,
    number: int,
    payload: ResumeVersionLabelPatch,
    db: Annotated[Session, Depends(get_db)],
):
    row = _get_version_or_404(db, kind, key, number)
    row.label = (payload.label or "").strip() or None
    db.commit()
    db.refresh(row)
    return ResumeVersionSummary.model_validate(row)
