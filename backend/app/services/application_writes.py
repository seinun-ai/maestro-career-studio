"""The single write-tail for replacing an application's tailored resume draft.

Five paths replace ``customized_json`` (from-base, form PATCH, typed edits,
materialize, tailor). Each must clear stale artifact references, record a
resume version, and remove the old files from disk — and disk removal must
wait until the caller's transaction commits, or a rollback leaves the DB
pointing at deleted files. This stages everything transactional and returns
the stale paths for the caller to pass to artifacts.remove_files() AFTER
commit.
"""
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application import NEWEST_FIRST, Application
from app.models.resume_version import ResumeVersion
from app.services import artifacts
from app.services.resume_versions import record_version

# The one sentence for an application with no tailored resume to read yet:
# scoring it, checking its health, or reviewing its changes all need one.
NO_TAILORED_RESUME = "This application has no tailored resume yet. Tailor it first."


def newest_for_job(db: Session, job_id: UUID) -> Application | None:
    """The application both write paths reuse: the job's newest, whatever its base resume
    (a job has one application; a tailor or from-base with another base replaces its draft).
    Ordered `NEWEST_FIRST`, the order the job detail and `stage` read, so a job holding
    several from before that rule updates the one its page shows."""
    return db.scalar(
        select(Application).where(Application.job_id == job_id).order_by(*NEWEST_FIRST).limit(1)
    )


def stage_resume_update(
    db: Session,
    application: Application,
    customized: dict[str, Any],
    *,
    source: str,
    summary: str | None = None,
    source_ref: str | None = None,
) -> tuple[list[Path], ResumeVersion]:
    stale = artifacts.stage_resume_artifact_removal(application)
    application.customized_json = customized
    db.flush()  # settles application.id for new rows without committing
    version = record_version(
        db,
        "application",
        str(application.id),
        customized,
        source=source,
        summary=summary,
        source_ref=source_ref,
    )
    return stale, version
