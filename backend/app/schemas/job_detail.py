from pydantic import BaseModel

from app.schemas.application import ApplicationRead
from app.schemas.job import JobRead
from app.schemas.knockout import KnockoutScan


class JobDetail(BaseModel):
    job: JobRead
    application: ApplicationRead | None = None
    # Stated-JD-requirements vs profile pre-scan; recomputed on every read so a
    # re-extract or a Settings edit refreshes the verdict without a write path.
    knockout: KnockoutScan | None = None
