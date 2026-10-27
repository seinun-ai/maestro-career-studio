"""Server-side composition of the agentic job-search brief.

One structured payload giving a browsing agent everything it needs before
opening a single job board: profile constraints (with validation warnings —
the brief NEVER guesses or corrects), persona text, base-resume targets, market
aggregations (role mix, top required skills, build areas), referral crawl
targets, and a 30-day capture ledger so the agent knows what is already
well-covered. Playbook: docs/agentic-job-search.md.

Work permits are per country (SYSTEM.md §6 inv-work-permit-per-country): the
brief carries each apply-in market's answers (`work_auth_by_country`), and the
one set from before (`work_auth`, the home market's, named by
`work_auth_market` as the autofill profile names it) stays for one release.
"""
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.job import Job
from app.models.referral import Referral
from app.schemas.autofill_profile import WorkAuth
from app.services import (
    agent_runs,
    auto_apply_settings,
    autofill_profile,
    job_preferences,
    market_settings,
    markets,
    model_settings,
    persona,
    role_categories,
)
from app.services import proposals as proposals_svc
from app.services.explore_base_summaries import base_summaries
from app.services.explore_build_areas import build_areas
from app.services.explore_overview import build_overview
from app.services.sync import status as sync_status

LEDGER_DAYS = 30
# Cap on the per-job years list in the brief; the ledger's cutoff bounds it in
# time, this bounds it in count. 25 recent scoped jobs is comparison material;
# 500 is a context bill.
MAX_BRIEF_JOBS = 25


def _yes_no_or_text(value: Any) -> str | None:
    """A yes/no profile answer as the word, whichever type it is stored as.

    The Settings form writes these as BOOLEANS, the extension's pause row writes
    the user's answer as a string, and the profile JSON is hand-editable — so
    one key legitimately arrives as `True`, `"yes"` or `"Yes"`. `_str_or_none`
    alone renders the first of those as `"True"`, which is not wrong so much as
    it is a different vocabulary from the other two: this value goes into a
    brief the model reads beside `work_auth`'s own yes/no answers, and one field
    answering in Python's booleans is the kind of inconsistency that costs a
    little accuracy and can never be traced back.

    Non-boolean values pass through untouched. "Open to relocating for the right
    role" is a real answer somebody has typed into that box, and narrowing it to
    a yes/no would be this function deciding what they meant.
    """
    if isinstance(value, bool):
        return "yes" if value else "no"
    return _str_or_none(value)


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


def _brief_work_auth(typed: WorkAuth) -> dict[str, str | None]:
    """One country's answers in the brief's established public yes/no keys.

    Current sponsorship and status are deliberately irrelevant: neither can
    answer the future sponsorship question without guessing."""
    return {
        "authorized_to_work": _yes_no(typed.authorized_now),
        "requires_sponsorship": _yes_no(typed.sponsorship_future),
    }


def _work_auth_warnings(work_auth: dict[str, Any], country: str | None = None) -> list[str]:
    """What is wrong with one country's answers; `country` (a label) names it unless the user
    lives and applies in that one country."""
    answers = "Your work authorization answers" + (f" for {country}" if country else "")
    authorized = (_str_or_none(work_auth.get("authorized_to_work")) or "").lower()
    sponsorship = (_str_or_none(work_auth.get("requires_sponsorship")) or "").lower()
    if not authorized or not sponsorship:
        return [
            f"{answers} are incomplete. Fix them in "
            "Profile › Work permits before filtering jobs on them. The brief never guesses."
        ]
    if authorized == "no" and sponsorship == "no":
        return [
            f"{answers} are contradictory: not authorized to "
            "work, and no sponsorship needed. The brief passes them on unchanged. "
            "Correct them in Profile › Work permits before relying on them."
        ]
    return []


def _work_permits(db: Session, profile: dict[str, Any]) -> dict[str, Any]:
    """The home market's answers (`work_auth`, kept for one release, named by `work_auth_market`),
    each apply-in market's (`work_auth_by_country`, keyed by market: "UK", not "GB"), and the
    warnings for the markets applied in. Living and applying in one country words them as before;
    otherwise each warning names its country. The home is judged only when applied in."""
    place = market_settings.peek_market(db)
    stored = profile.get(autofill_profile.BY_COUNTRY) or {}
    by_country = {
        market: _brief_work_auth(autofill_profile.typed_work_auth(stored.get(market)))
        for market in place.apply_in
    }
    one_country = place.apply_in == [place.home]
    warnings = [
        warning
        for market, answers in by_country.items()
        for warning in _work_auth_warnings(
            answers, None if one_country else markets.get(market)["label"]
        )
    ]
    return {
        "work_auth": _brief_work_auth(autofill_profile.work_auth_from_profile(profile)),
        "work_auth_market": place.home,
        "work_auth_by_country": by_country,
        "warnings": warnings,
    }


def _last_runs(db: Session) -> dict[str, str]:
    """When each automation's newest reported run finished (the Automations page's Last ran)."""
    return {run["automation"]: run["finished_at"].isoformat() for run in agent_runs.latest(db)}


def _auto_apply_block(db: Session) -> dict[str, Any]:
    cfg = auto_apply_settings.get_settings(db)
    return {
        "full_automation": cfg.full_automation,
        "company_blocklist": cfg.company_blocklist,
        "max_proposals_per_run": cfg.max_proposals_per_run,
        "cap": proposals_svc.cap_status(db),
    }


def _applying_block(db: Session) -> dict[str, Any]:
    # The Screening answers level decides how far a fill answers without asking;
    # an agent that applies reads it here instead of assuming the default.
    return {"answer_level": model_settings.get_answer_level(db)}


def _sync_block() -> dict[str, Any]:
    enabled = sync_status.enabled()
    role = "remote" if sync_status.is_remote() else "home"
    return {"enabled": enabled, "role": role if enabled else None}


def build_brief(db: Session) -> dict[str, Any]:
    profile = autofill_profile.get_profile(db)
    personal = profile.get("personal") or {}
    preferences = profile.get("preferences") or {}
    permits = _work_permits(db, profile)

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
            "willing_to_relocate": _yes_no_or_text(
                preferences.get("willing_to_relocate")
            ),
            "work_auth": permits["work_auth"],
            "work_auth_market": permits["work_auth_market"],
            "work_auth_by_country": permits["work_auth_by_country"],
        },
        "persona": persona.get_persona(db),
        # G1 (2026-08-01): the typed search preferences, verbatim — same
        # no-guessing doctrine as work_auth. G2: hunt guardrails up front so a
        # run never burns extraction on a blocklisted company or discovers the
        # per-run/daily caps by 409.
        "job_preferences": job_preferences.get_preferences(db).model_dump(),
        "jobs": jobs,
        "auto_apply": _auto_apply_block(db),
        "applying": _applying_block(db),
        "sync": _sync_block(),
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
        "last_runs": _last_runs(db),
        "roles": [{"key": key, "label": label} for key, label in role_categories.labels().items()],
        "warnings": permits["warnings"],
    }
