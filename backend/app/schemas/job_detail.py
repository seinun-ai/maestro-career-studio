from pydantic import BaseModel

from app.schemas.application import ApplicationRead
from app.schemas.job import JobRead
from app.schemas.knockout import KnockoutScan


class JobDetail(BaseModel):
    # Ownership is carried by the nested job, using the same shape as the job list.
    job: JobRead
    application: ApplicationRead | None = None
    # Stated-JD-requirements vs profile pre-scan; recomputed on every read so a
    # re-extract or a Settings edit refreshes the verdict without a write path.
    knockout: KnockoutScan | None = None
    # Whether anything was recorded as filled into this job's form: the job page shows its
    # What was submitted tab only then (services/filled_answers.has_any).
    has_filled_answers: bool = False
