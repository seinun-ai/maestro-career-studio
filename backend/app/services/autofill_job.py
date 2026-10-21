"""The job an autofill call is for, and the profile as that job may see it.

A saved answer that named a company or city (`custom[].only_for`) holds for jobs
there only (`autofill_catalog.custom_for_job`), and `work_auth` is the job's
country's work-permit answers (`autofill_country`: none for a job with no
country). Every route that hands the profile onward, to the deterministic fill
(/context) or to a model (/choose), passes it through `profile_for_job`, so the
scope is decided in one place. The fill loop's catalog (`routers/autofill._facts`)
resolves `work_auth` the same way, and per question."""

from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.job import Job
from app.services import autofill_catalog, autofill_country


def application_job(db: Session, application_id: UUID | None) -> Job | None:
    application = db.get(Application, application_id) if application_id is not None else None
    return db.get(Job, application.job_id) if application is not None else None


def job_market(job: Job | None) -> str | None:
    """The market of the job's country ("GB" is "UK"); None with no job or no market for it."""
    return autofill_country.market_for_job_country(job.country_code) if job is not None else None


def profile_for_job(db: Session, profile: Any, application_id: UUID | None) -> Any:
    """The profile with the saved answers that hold for the application's job, and the job's
    country's work-permit answers as `work_auth`. With no application (a form not tracked yet) a
    scoped answer holds nowhere, and there are no work-permit answers: a question that names its
    country is answered on the fill loop, where the question is known."""
    if not isinstance(profile, dict):
        return profile
    job = application_job(db, application_id)
    profile = autofill_country.with_work_auth(profile, job_market(job))
    if "custom" not in profile:
        return profile
    return {**profile, "custom": autofill_catalog.custom_for_job(
        profile["custom"], job.company if job else None, job.location if job else None)}


# The job boards a posting's URL host names as where the job was found ("how did you hear about us?").
# By registered domain: a subdomain ("uk.indeed.com") is the same board. A careers site or an ATS host
# is the employer's own page, no board.
_BOARDS = {
    "linkedin.com": "LinkedIn", "indeed.com": "Indeed", "glassdoor.com": "Glassdoor",
    "ziprecruiter.com": "ZipRecruiter", "monster.com": "Monster", "simplyhired.com": "SimplyHired",
    "dice.com": "Dice", "wellfound.com": "Wellfound", "angel.co": "Wellfound",
    "joinhandshake.com": "Handshake", "builtin.com": "Built In", "careerbuilder.com": "CareerBuilder",
    "snagajob.com": "Snagajob", "flexjobs.com": "FlexJobs", "levels.fyi": "Levels.fyi",
}


BOARD_NAMES = frozenset(_BOARDS.values())


def board_of_url(url: str | None) -> str | None:
    """The job board a posting URL's host names ("https://www.linkedin.com/jobs/view/1" is LinkedIn), else
    None: the host of a careers site or an applicant tracking system is the employer's."""
    host = (urlsplit(url or "").hostname or "").lower()
    return next((name for domain, name in _BOARDS.items() if host == domain or host.endswith(f".{domain}")), None)
