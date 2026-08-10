from typing import Literal

from pydantic import BaseModel

from app.schemas.application import ApplicationSummary
from app.schemas.job import JobSummary


class JobMatchResult(BaseModel):
    """What the tracked library knows about the page the user is currently on.

    Two states, not three. An earlier version carried a `likely` tier for
    partial path overlap, on the theory that the UI could present it as a
    correctable suggestion. The tier could not survive its own evidence: the
    underlying score was a raw count of shared leading path segments, never
    normalized by path depth, so a lever posting's apply page and a greenhouse
    sibling posting both scored 12. `likely` was therefore not a weaker kind of
    match, it was a bag holding "the job you saved" and "a different job at the
    same employer" with no way to tell them apart. Directional containment
    decides the question outright (services/job_url_match.py), so the tier has
    nothing left to express.

    There is no `score` either. Nothing read it — not extension/, not
    frontend/ — and an integer with no consumer is one a client will eventually
    branch on, re-deriving the collision this design removed. The endpoint
    answers a yes/no question, so it returns a yes/no answer.

    Lives in its own module rather than in schemas/job.py for the same reason
    JobDetail does: schemas/application.py imports from schemas/job.py, so any
    job+application composite declared there is a circular import.
    """

    match: Literal["exact", "none"]
    job: JobSummary | None = None
    application: ApplicationSummary | None = None
