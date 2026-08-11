"""Server-side composition of the agentic job-search brief.

One structured payload giving a browsing agent everything it needs before
opening a single job board: profile constraints (with validation warnings —
the brief NEVER guesses or corrects), persona text, base-resume targets, market
aggregations (role mix, top required skills, build areas), referral crawl
targets, and a 30-day capture ledger so the agent knows what is already
well-covered. Playbook: docs/agentic-job-search.md.
"""
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.job import Job
from app.models.referral import Referral
from app.services import auto_apply_settings, autofill_profile, job_preferences, persona
from app.services import proposals as proposals_svc
from app.services.explore_base_summaries import base_summaries
from app.services.explore_build_areas import build_areas
from app.services.explore_overview import build_overview

LEDGER_DAYS = 30
# Cap on the per-job years list in the brief; the ledger's cutoff bounds it in
# time, this bounds it in count. 25 recent scoped jobs is comparison material;
# 500 is a context bill.
MAX_BRIEF_JOBS = 25


def _str_or_none(value: Any) -> str | None:
    # The autofill profile is intentionally loose JSON; coerce scalars so a
    # bool/number in a hand-edited profile can't 500 the response model.
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _yes_no(value: bool | None) -> str | None:
    if value is None:
        return None
    return "yes" if value else "no"


def _work_auth_warnings(work_auth: dict[str, Any]) -> list[str]:
    authorized = (_str_or_none(work_auth.get("authorized_to_work")) or "").lower()
    sponsorship = (_str_or_none(work_auth.get("requires_sponsorship")) or "").lower()
    if not authorized or not sponsorship:
        return [
            "Work authorization is incomplete in the autofill profile "
            "(authorized_to_work / requires_sponsorship missing). Fix it in "
            "Settings before filtering jobs on it; the brief never guesses."
        ]
    if authorized == "no" and sponsorship == "no":
        return [
            "Work-auth values are contradictory: authorized_to_work='no' with "
            "requires_sponsorship='no'. The brief carries them verbatim — "
            "correct the autofill profile in Settings before relying on them."
        ]
    return []


def _auto_apply_block(db: Session) -> dict[str, Any]:
    cfg = auto_apply_settings.get_settings(db)
    return {
        "company_blocklist": cfg.company_blocklist,
        "max_proposals_per_run": cfg.max_proposals_per_run,
        "cap": proposals_svc.cap_status(db),
    }


def build_brief(db: Session) -> dict[str, Any]:
    profile = autofill_profile.get_profile(db)
    personal = profile.get("personal") or {}
    preferences = profile.get("preferences") or {}
    typed_work_auth = autofill_profile.get_work_auth(db)
    # Keep the established public response keys while sourcing them from the
    # typed reader. Current sponsorship and status are deliberately irrelevant:
    # neither can answer the future sponsorship question without guessing.
    work_auth = {
        "authorized_to_work": _yes_no(typed_work_auth.authorized_now),
        "requires_sponsorship": _yes_no(typed_work_auth.sponsorship_future),
    }

    overview = build_overview(db)

    # Single coalesce expression reused in GROUP BY (separate builds render as
    # distinct bind params and Postgres rejects the grouping — the
    # explore_base_summaries gotcha).
    rc = func.coalesce(Job.role_category, "unknown")
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=LEDGER_DAYS)
    ledger = [
        {"role_category": str(key), "count": int(count)}
        for key, count in db.execute(
            select(rc, func.count())
            .where(Job.created_at >= cutoff)
            .group_by(rc)
            .order_by(func.count().desc(), rc)
        ).all()
    ]

    referrals = [
        {
            "company": referral.company,
            "careers_url": referral.careers_url,
            "has_contact": bool((referral.contact_name or "").strip()),
        }
        for referral in db.scalars(select(Referral).order_by(Referral.company))
    ]

    # Bounded like the ledger above, and for the same reason: the brief is a
    # PROMPT BLOCK, not an export. An unbounded select(Job) grows with every
    # captured job forever. Only jobs that state a years bound can support the
    # years_experience comparison this list exists for, and only recent ones
    # are worth prompting on — agents wanting more use list_jobs.
    jobs = [
        {
            "id": str(job.id),
            "title": job.title,
            "company": job.company,
            "years_experience_min": job.years_experience_min,
            "years_experience_max": job.years_experience_max,
        }
        for job in db.scalars(
            select(Job)
            .where(Job.created_at >= cutoff)
            .where(
                Job.years_experience_min.is_not(None)
                | Job.years_experience_max.is_not(None)
            )
            .order_by(Job.created_at.desc(), Job.id)
            .limit(MAX_BRIEF_JOBS)
        )
    ]

    return {
        # Timezone-aware UTC ISO timestamp for the whole brief.
        "generated_at": now.isoformat(),
        "profile": {
            "city": _str_or_none(personal.get("city")),
            "state": _str_or_none(personal.get("state")),
            "country": _str_or_none(personal.get("country")),
            "willing_to_relocate": _str_or_none(preferences.get("willing_to_relocate")),
            "work_auth": work_auth,
        },
        "persona": persona.get_persona(db),
        # G1 (2026-08-01): the typed search preferences, verbatim — same
        # no-guessing doctrine as work_auth. G2: hunt guardrails up front so a
        # run never burns extraction on a blocklisted company or discovers the
        # per-run/daily caps by 409.
        "job_preferences": job_preferences.get_preferences(db).model_dump(),
        "jobs": jobs,
        "auto_apply": _auto_apply_block(db),
        "base_resumes": base_summaries(db),
        "role_mix": overview["role_mix"],
        "top_skills": overview["top_required_skills"],
        "build_areas": build_areas(db),
        "referrals": referrals,
        "captured_last_30_days": ledger,
        # Provenance labels matching the windows the code above truly computes:
        # build_overview (role_mix, top_skills) and build_areas run unfiltered
        # over ALL jobs; only the capture ledger is bounded to LEDGER_DAYS.
        "windows": {
            "role_mix": "all_time",
            "top_skills": "all_time",
            "build_areas": "all_time",
            "captured_last_30_days": f"last_{LEDGER_DAYS}_days",
        },
        "warnings": _work_auth_warnings(work_auth),
    }
