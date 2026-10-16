from uuid import UUID

from pydantic import BaseModel

from app.schemas.application import ApplicationRead
from app.schemas.job import JobRead
from app.schemas.knockout import KnockoutScan
from app.services.stage import Rung


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
    # The application's base resume's own name (archived and soft-deleted rows included, since the
    # application outlives both); null with no application or when the resume has no name.
    base_resume_name: str | None = None
    # The rung the job page is on (services/stage.py): the newest application's, else the job's
    # own; the open session and its resolved/listed counts are set only on the `gaps` rung.
    stage: Rung
    open_session_id: UUID | None = None
    gaps_done: int = 0
    gaps_total: int = 0
