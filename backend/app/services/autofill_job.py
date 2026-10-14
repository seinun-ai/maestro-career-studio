"""The job an autofill call is for, and the profile as that job may see it.

A saved answer that named a company or city (`custom[].only_for`) holds for jobs
there only (`autofill_catalog.custom_for_job`). Every route that hands the
profile onward, to the deterministic fill (/context) or to a model (/choose),
passes it through `profile_for_job`, so the scope is decided in one place."""

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.job import Job
from app.services import autofill_catalog


def application_job(db: Session, application_id: UUID | None) -> Job | None:
    application = db.get(Application, application_id) if application_id is not None else None
    return db.get(Job, application.job_id) if application is not None else None


def profile_for_job(db: Session, profile: Any, application_id: UUID | None) -> Any:
    """The profile with the saved answers that hold for the application's job.
    With no application (a form not tracked yet) a scoped answer holds nowhere."""
    if not isinstance(profile, dict) or "custom" not in profile:
        return profile
    job = application_job(db, application_id)
    return {**profile, "custom": autofill_catalog.custom_for_job(
        profile["custom"], job.company if job else None, job.location if job else None)}
