from typing import Literal

from pydantic import BaseModel

KnockoutStatus = Literal["conflict", "clear", "incomplete_profile", "unstated"]
# `cant_compare`: the salary check had no exchange rate, or a side named no currency. Never a pass.
KnockoutResult = Literal["pass", "conflict", "warning", "job_unstated", "profile_missing", "cant_compare"]


class KnockoutCheck(BaseModel):
    kind: Literal["work_authorization", "opt", "salary", "experience", "on_site"]
    result: KnockoutResult
    job_value: str | None = None
    profile_value: str | None = None
    message: str | None = None


class KnockoutScan(BaseModel):
    """services/knockout.scan_job output. `unstated` is NOT a pass — the
    posting simply screens on nothing this scan can check."""

    status: KnockoutStatus
    checks: list[KnockoutCheck]
