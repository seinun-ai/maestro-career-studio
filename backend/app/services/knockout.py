"""Knock-out pre-scan: stated JD hard requirements vs the user's own profile.

Compares what the posting states (work authorization, OPT policy, salary)
against what the autofill profile answers, BEFORE tailoring/filling effort is
spent. Read-and-compare only — every input already exists on `Job` and in the
autofill profile; this module persists nothing.

Verdict semantics (inv-honesty applied to screening):
- ``conflict``            — a stated requirement contradicts a known answer.
- ``clear``               — at least one stated requirement was evaluated and
                            every evaluable one passed.
- ``incomplete_profile``  — a stated requirement exists that the profile
                            cannot answer. Not a pass.
- ``unstated``            — the posting states no screenable requirement.
                            Not a pass either: "no blockers stated" is a
                            weaker claim than "you clear the stated blockers".

Salary never conflicts — pay is negotiable — it only warns.
"""

import re
from decimal import Decimal
from typing import Any

from app.models.job import Job
from app.schemas.autofill_profile import WorkAuth

# Statuses that clear a citizen/green-card gate.
_CITIZEN_OR_GC = {"citizen", "permanent_resident"}
# Status → (needs sponsorship now, needs sponsorship in the future) when the
# profile carries no explicit sponsorship answers. TN is deliberately absent:
# TN renewal mechanics vary enough that inferring either answer would guess a
# knockout answer, which the WorkAuth schema forbids.
_STATUS_SPONSORSHIP = {
    "citizen": (False, False),
    "permanent_resident": (False, False),
    "opt": (False, True),
    "stem_opt": (False, True),
    "h1b": (True, True),
    "other_visa": (True, True),
    "not_authorized": (True, True),
}

_OPT_STATUSES = {"opt", "stem_opt"}


def _sponsorship_needs(work_auth: WorkAuth) -> tuple[bool | None, bool | None]:
    """Explicit answers win; status only fills the blanks."""
    now, future = work_auth.sponsorship_now, work_auth.sponsorship_future
    inferred = _STATUS_SPONSORSHIP.get(work_auth.status or "")
    if inferred is not None:
        if now is None:
            now = inferred[0]
        if future is None:
            future = inferred[1]
    return now, future


def _gc_required_verdict(work_auth: WorkAuth) -> tuple[str, str | None]:
    if work_auth.status is None:
        return (
            "profile_missing",
            "Posting requires citizen/green-card status; set your work authorization in Settings.",
        )
    if work_auth.status in _CITIZEN_OR_GC:
        return "pass", None
    return "conflict", "Posting requires US citizen or green-card status."


def _no_sponsorship_verdict(work_auth: WorkAuth) -> tuple[str, str | None]:
    now, future = _sponsorship_needs(work_auth)
    if now or future:
        timing = "now" if now else "in the future"
        return (
            "conflict",
            f"Posting offers no sponsorship; your profile needs sponsorship {timing}.",
        )
    if now is None or future is None:
        return (
            "profile_missing",
            "Posting offers no sponsorship; answer the sponsorship questions in Settings.",
        )
    return "pass", None


def _work_auth_check(job: Job, work_auth: WorkAuth) -> dict[str, Any]:
    stated = job.work_authorization
    check: dict[str, Any] = {
        "kind": "work_authorization",
        "job_value": stated,
        "profile_value": work_auth.status,
    }
    if not stated or stated == "unstated":
        return {**check, "result": "job_unstated", "message": None}
    if stated == "sponsorship_available":
        return {**check, "result": "pass", "message": "Posting offers sponsorship."}
    if stated == "citizen_or_gc_required":
        result, message = _gc_required_verdict(work_auth)
    else:  # no_sponsorship
        result, message = _no_sponsorship_verdict(work_auth)
    return {**check, "result": result, "message": message}


def _opt_check(job: Job, work_auth: WorkAuth) -> dict[str, Any] | None:
    stated = job.opt_accepted
    jd_states = bool(stated) and stated != "unstated"
    holder = work_auth.status in _OPT_STATUSES
    if not jd_states and not holder:
        return None
    check: dict[str, Any] = {
        "kind": "opt",
        "job_value": stated if jd_states else None,
        "profile_value": work_auth.status,
    }
    if not jd_states:
        return {**check, "result": "job_unstated", "message": None}
    result, message = _opt_verdict(stated, work_auth.status, holder)
    return {**check, "result": result, "message": message}


def _opt_verdict(stated: str, status: str | None, holder: bool) -> tuple[str, str | None]:
    if status is None:
        return (
            "profile_missing",
            "Posting states an OPT policy; set your work authorization in Settings.",
        )
    if not holder:
        return "pass", None
    if stated == "no" or (stated == "stem_opt_ok" and status != "stem_opt"):
        policy = "does not accept OPT" if stated == "no" else "accepts STEM OPT only"
        return "conflict", f"Posting {policy}."
    return "pass", None


_NUMBER = re.compile(r"(\d[\d,.]*)\s*([kK])?")


def parse_desired_salary(raw: Any) -> Decimal | None:
    """First number in a free-text desired salary; '150k' style honored.

    Returns None when nothing parses — the scan then stays silent rather than
    comparing against a guess.
    """
    if isinstance(raw, (int, float, Decimal)):
        return Decimal(str(raw))
    if not isinstance(raw, str):
        return None
    match = _NUMBER.search(raw)
    if not match:
        return None
    try:
        value = Decimal(match.group(1).replace(",", "").rstrip("."))
    except ArithmeticError:
        return None
    if match.group(2):
        value *= 1000
    return value


def _salary_check(job: Job, preferences: dict[str, Any] | None) -> dict[str, Any] | None:
    ceiling = job.salary_max if job.salary_max is not None else job.salary_min
    if ceiling is None:
        return None
    # Yearly figures only: desired_salary is a yearly expectation, and
    # comparing it to an hourly/monthly rate would need a conversion guess.
    yearly = job.salary_period == "year" or (
        job.salary_period is None and Decimal(ceiling) >= 10000
    )
    if not yearly:
        return None
    desired = parse_desired_salary((preferences or {}).get("desired_salary"))
    if desired is None:
        return None
    check: dict[str, Any] = {
        "kind": "salary",
        "job_value": str(ceiling),
        "profile_value": str(desired),
    }
    if Decimal(ceiling) < desired:
        return {
            **check,
            "result": "warning",
            "message": "Posted range tops out below your desired salary.",
        }
    return {**check, "result": "pass", "message": None}


def _experience_check(job: Job, years_experience: int | None) -> dict[str, Any] | None:
    """Stated minimum years vs the profile's stated years (job_preferences).

    Warning severity like salary, never a conflict: "N+ years" is the classic
    soft-hard requirement — real ATS knockouts exist, but the bar is routinely
    cleared with less, and both numbers are self-reported. Omitted when either
    side is unstated; the years come from the user's own Job preferences field,
    never derived from KB date spans (a false conflict from an incomplete KB
    would be worse than an honest omission).
    """
    if job.years_experience_min is None or years_experience is None:
        return None
    check: dict[str, Any] = {
        "kind": "experience",
        "job_value": f"{job.years_experience_min}+",
        "profile_value": str(years_experience),
    }
    if years_experience < job.years_experience_min:
        return {
            **check,
            "result": "warning",
            "message": (
                f"Posting asks {job.years_experience_min}+ years; "
                f"your profile states {years_experience}."
            ),
        }
    return {**check, "result": "pass", "message": None}


def scan_job(
    job: Job,
    work_auth: WorkAuth,
    preferences: dict[str, Any] | None,
    years_experience: int | None = None,
) -> dict[str, Any]:
    # settings/autofill.json is hand-editable loose JSON; `preferences` may
    # arrive as any shape.
    if not isinstance(preferences, dict):
        preferences = None
    checks = [_work_auth_check(job, work_auth)]
    opt = _opt_check(job, work_auth)
    if opt is not None:
        checks.append(opt)
    salary = _salary_check(job, preferences)
    if salary is not None:
        checks.append(salary)
    experience = _experience_check(job, years_experience)
    if experience is not None:
        checks.append(experience)

    results = {c["result"] for c in checks}
    if "conflict" in results:
        status = "conflict"
    elif "profile_missing" in results:
        status = "incomplete_profile"
    elif results & {"pass", "warning"}:
        status = "clear"
    else:
        status = "unstated"
    return {"status": status, "checks": checks}
