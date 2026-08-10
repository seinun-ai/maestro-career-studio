from pydantic import BaseModel

from app.schemas.application import ApplicationRead
from app.schemas.job import JobRead


class JobDetail(BaseModel):
    job: JobRead
    application: ApplicationRead | None = None
