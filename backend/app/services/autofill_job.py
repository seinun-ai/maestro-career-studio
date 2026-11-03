"""The job an autofill call is for, and the profile as that job may see it.

A saved answer that named a company or city (`custom[].only_for`) holds for jobs
there only (`autofill_catalog.custom_for_job`), and `work_auth` is the job's
country's work-permit answers (`autofill_country`: none for a job with no
country). Every route that hands the profile onward, to the deterministic fill
(/context) or to a model (/choose), passes it through `profile_for_job`, so the
scope is decided in one place. The job's country's own answers (`answers_by_country`)
are folded over the slots they fill, its pay is its own or none, and no other country's
reach it (`autofill_country.for_market`, by the chosen home each caller reads once:
`autofill_profile.chosen_home`). The fill loop's catalog (`routers/autofill._facts`)
resolves both the same way, and per question."""

from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.job import Job
from app.services import autofill_catalog, autofill_country, autofill_profile, countries


def application_job(db: Session, application_id: UUID | None) -> Job | None:
    application = db.get(Application, application_id) if application_id is not None else None
    return db.get(Job, application.job_id) if application is not None else None


def job_market(job: Job | None) -> str | None:
    """The market of the job's country ("GB" is "UK"); None with no job or no market for it."""
    return autofill_country.market_for_job_country(job.country_code) if job is not None else None


def view_for(profile: Any, job: Job | None, market: str | None, *, chosen_home: str | None) -> Any:
    """The profile a form on `job` reads for one market's questions: that market's answers
    (`autofill_country.for_market`: its permits, own answers and pay by `chosen_home`, no other
    country's) and the saved answers that hold for the job (`custom_for_job`; with no job, no
    scoped one)."""
    if not isinstance(profile, dict):
        return profile
    view = autofill_country.for_market(profile, market, chosen_home=chosen_home)
    if "custom" not in view:
        return view
    return {**view, "custom": autofill_catalog.custom_for_job(
        view["custom"], job.company if job else None, job.location if job else None)}


def profile_for_job(db: Session, profile: Any, application_id: UUID | None,
                    question: str | None = None) -> Any:
    """The profile with the saved answers that hold for the application's job, the job's country's
    work-permit answers as `work_auth` (`work_auth_market` names it) and its own answers and pay over
    the slots they fill (`view_for`, by the chosen home read here: `autofill_profile.chosen_home`).
    With no application (a form not tracked yet) a scoped answer holds
    nowhere, and there are no country's answers: a question that names its country is answered on
    the fill loop, where the question is known.
    `question` is that case for one question (the Companion's pause row learning an answer): the
    market it gets by `autofill_country.market_for_question`, the country it names, else the job's,
    and `work_auth_country` naming that country in words, one no market covers too (None: no one
    country), so the pause row can say why an answer was not kept."""
    if not isinstance(profile, dict):
        return profile
    job = application_job(db, application_id)
    market = job_market(job)
    if question is not None:
        market = autofill_country.market_for_question(question, market)
    view = view_for(profile, job, market, chosen_home=autofill_profile.chosen_home(db))
    if question is not None:
        code = autofill_country.country_for_question(question, job.country_code if job else None)
        view = {**view, autofill_country.WORK_AUTH_COUNTRY: countries.label(code)}
    return view


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
