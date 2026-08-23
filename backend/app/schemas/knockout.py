from typing import Literal

from pydantic import BaseModel

KnockoutStatus = Literal["conflict", "clear", "incomplete_profile", "unstated"]
KnockoutResult = Literal["pass", "conflict", "warning", "job_unstated", "profile_missing"]


class KnockoutCheck(BaseModel):
    kind: Literal["work_authorization", "opt", "salary", "experience"]
    result: KnockoutResult
    job_value: str | None = None
    profile_value: str | None = None
    message: str | None = None


class KnockoutScan(BaseModel):
    """services/knockout.scan_job output. `unstated` is NOT a pass — the
    posting simply screens on nothing this scan can check."""

    status: KnockoutStatus
    checks: list[KnockoutCheck]
