"""Today (GET /api/today): the one thing that matters most now, the few counts behind it, and this
week. Read-only, and it never writes: every number comes from a reader that already exists (the job
stage ladder, the tracker score, the Agent inbox's summary, the status-event log through
`search_summary`, the health report), and a proposal past its expiry is left out rather than expired
(the Agent inbox's own read does that).

Like the Jobs list, it reads every job, the other copy's replicas included: an action on one becomes
a request for the next sync (docs/entities/job.md, "Ownership under sync").
"""

from __future__ import annotations

import re
import zoneinfo
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from typing import Any

from sqlalchemy import func, not_, select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.application_proposal import ApplicationProposal
from app.models.application_status_event import ApplicationStatusEvent
from app.models.base_resume import BaseResume
from app.models.job import Job
from app.models.resume_version import ResumeVersion
from app.models.tailoring_session import TailoringSession
from app.services import (
    ats_score,
    base_resume_data,
    inbox_readiness,
    proposals,
    resume_lint,
    search_summary,
    stage,
)
from app.services.search_summary import INTERVIEW_STATUSES, REPLY_STATUSES

# Next up is the first of these that exists, in this order: an offer waits on your answer to an
# employer, a ready PDF is one click from applying (the best match first), and a proposal's question
# waits on you but is the agent's work.
NEXT_UP_ORDER = ("offer", "pdf_ready", "needs_you")
# "Quiet, follow up": sent this many days ago with nothing since. Two weeks is the usual point to
# follow up; Analytics' "no reply" waits longer (search_summary.QUIET_AFTER_DAYS) because it asks
# whether a reply will come at all.
QUIET_FOLLOW_UP_DAYS = 14
WEEK_DAYS = 7

# An IANA zone name ("Europe/Berlin", "America/Argentina/Buenos_Aires", "Etc/GMT+5", "UTC"): letters,
# digits, "_", "+" and "-" in "/"-separated parts. Nothing else reaches the zone database.
_ZONE_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_+\-]*(/[A-Za-z0-9_+\-]+)*")


def local_zone(tz: str | None, utc_offset_minutes: int | None) -> tuple[tzinfo, str]:
    """The browser's time zone for "local days", and its name for the payload. The server does not
    know the browser's zone, so the page sends `tz` (IANA) and `utc_offset_minutes`; the name wins
    when this server's zone database has it (a Windows install without one does not), else the
    offset; neither is UTC. Raises ValueError for a malformed name, or an unknown one with no offset."""
    if tz is not None:
        if not _ZONE_NAME.fullmatch(tz) or len(tz) > 64:
            raise ValueError("tz is an IANA time zone name, such as Europe/Berlin.")
        try:
            return zoneinfo.ZoneInfo(tz), tz
        except (zoneinfo.ZoneInfoNotFoundError, ValueError):
            if utc_offset_minutes is None:
                raise ValueError(f"Unknown time zone {tz}: send utc_offset_minutes too.") from None
    if utc_offset_minutes is not None:
        zone = timezone(timedelta(minutes=utc_offset_minutes))
        return zone, zone.tzname(None)
    return UTC, "UTC"


# ---------------------------------------------------------------------------- next up


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _steps(*pairs: tuple[str, datetime | None]) -> list[dict[str, str]]:
    """"Where this job is": the ladder's steps the data dates, in ladder order; an undated step is left
    out, never guessed."""
    return [{"key": key, "at": at.isoformat()} for key, at in pairs if at is not None]


def _resume(db: Session, slug: str | None) -> dict[str, Any] | None:
    if not slug:
        return None
    row = db.get(BaseResume, slug)  # whatever its state: an application outlives its resume's archive
    return {
        "slug": slug,
        "name": (row.display_name or None) if row is not None else None,
        "color_hue": row.color_hue if row is not None else None,
    }


def _pay(job: Job) -> dict[str, Any] | None:
    """As posted; the page words and converts it (lib/money.ts). Missing pay is never estimated."""
    if job.salary_min is None and job.salary_max is None:
        return None
    return {
        "min": float(job.salary_min) if job.salary_min is not None else None,
        "max": float(job.salary_max) if job.salary_max is not None else None,
        "currency": job.salary_currency,
        "period": job.salary_period,
    }


def _item(db: Session, kind: str, job: Job, *, application: Application | None = None,
          proposal: ApplicationProposal | None = None, base: str | None, score: float | None,
          status: str | None, steps: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "kind": kind,
        "job_id": str(job.id),
        "application_id": str(application.id) if application is not None else None,
        "proposal_id": str(proposal.id) if proposal is not None else None,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "pay": _pay(job),
        "base_resume": _resume(db, base),
        "score": score,
        "status": status,
        "proposed_by": proposal.proposed_by if proposal is not None else None,
        "reason": proposal.reason if proposal is not None else None,
        "steps": steps,
    }


def _dated_event(db: Session, app_id, to_status: str, *, newest: bool) -> datetime | None:
    """The first (or newest) real event to `to_status`; a backfilled one has no real date."""
    at = func.max(ApplicationStatusEvent.at) if newest else func.min(ApplicationStatusEvent.at)
    return db.scalar(
        select(at).where(
            ApplicationStatusEvent.application_id == app_id,
            ApplicationStatusEvent.to_status == to_status,
            not_(ApplicationStatusEvent.backfilled),
        )
    )


def _draft_steps(db: Session, application: Application) -> list[tuple[str, datetime | None]]:
    """When the gap analysis closed (its session turned `tailored`) and when tailoring last wrote the
    draft (its newest `tailor` version). A draft made with "Use resume as is" has neither."""
    closed = db.scalar(
        select(TailoringSession.updated_at)
        .where(TailoringSession.application_id == application.id,
               TailoringSession.status == "tailored")
        .order_by(TailoringSession.updated_at.desc())
        .limit(1)
    )
    tailored = db.scalar(
        select(func.max(ResumeVersion.created_at)).where(
            ResumeVersion.resume_kind == "application",
            ResumeVersion.resume_key == str(application.id),
            ResumeVersion.source == "tailor",
        )
    )
    return [("gaps_closed", closed), ("tailored", tailored)]


def _offer(db: Session) -> dict[str, Any] | None:
    """An offer awaiting your response: status offered. The one that has waited longest first."""
    offers = db.scalars(select(Application).where(Application.status == "offered")).all()
    if not offers:
        return None
    since = dict(
        db.execute(
            select(ApplicationStatusEvent.application_id, func.max(ApplicationStatusEvent.at))
            .where(ApplicationStatusEvent.application_id.in_([a.id for a in offers]),
                   ApplicationStatusEvent.to_status == "offered")
            .group_by(ApplicationStatusEvent.application_id)
        ).all()
    )
    far_future = datetime.max.replace(tzinfo=UTC)  # an offer with no event sorts last
    application = min(offers, key=lambda a: (since.get(a.id) or far_future, str(a.id)))
    job = db.get(Job, application.job_id)
    score = ats_score.tracker_scores(db, [application]).get(application.id)
    steps = _steps(
        ("saved", job.created_at),
        *_draft_steps(db, application),
        ("applied", application.applied_at),
        ("interviewing", _dated_event(db, application.id, "interviewing", newest=False)),
        ("offered", _dated_event(db, application.id, "offered", newest=True)),
    )
    return _item(db, "offer", job, application=application, base=application.base_resume,
                 score=score, status=application.status, steps=steps)


def _unsent(db: Session) -> list[Application]:
    """Applications not sent and not closed: the ones a stage rung below `applied` can describe."""
    return list(db.scalars(
        select(Application).where(
            Application.applied_at.is_(None),
            func.coalesce(Application.status, "draft") == "draft",
        )
    ))


def _pdf_ready(db: Session, unsent: list[Application], rungs: dict) -> dict[str, Any] | None:
    """A draft with its PDF ready (the `pdf_ready` rung) and the best match score (the tracker's)."""
    ready = [a for a in unsent if rungs[a.id].rung == "pdf_ready"]
    if not ready:
        return None
    scores = ats_score.tracker_scores(db, ready)
    application = max(ready, key=lambda a: (scores.get(a.id, -1.0), a.created_at, str(a.id)))
    job = db.get(Job, application.job_id)
    steps = _steps(("saved", job.created_at), *_draft_steps(db, application))
    return _item(db, "pdf_ready", job, application=application, base=application.base_resume,
                 score=scores.get(application.id), status=application.status, steps=steps)


def _needs_you(db: Session, now: datetime) -> dict[str, Any] | None:
    """A proposal waiting on your answer (the Agent inbox's Needs you lane), newest first as the lane
    lists it; one past its expiry is not waiting any more."""
    proposal = db.scalars(
        select(ApplicationProposal)
        .where(ApplicationProposal.status.in_(inbox_readiness.NEEDS_YOU),
               not_(proposals.past_expiry(now)))
        .order_by(ApplicationProposal.created_at.desc(), ApplicationProposal.id.desc())
        .limit(1)
    ).first()
    if proposal is None:
        return None
    job = db.get(Job, proposal.job_id)
    application = db.get(Application, proposal.application_id) if proposal.application_id else None
    fit = proposal.fit_json if isinstance(proposal.fit_json, dict) else {}
    chosen = fit.get("chosen_base") if isinstance(fit.get("chosen_base"), str) else None
    scores = fit.get("scores") if isinstance(fit.get("scores"), dict) else {}
    score = scores.get(chosen) if chosen else None
    score = float(score) if isinstance(score, int | float) and not isinstance(score, bool) else None
    if score is None and application is not None:
        score = ats_score.tracker_scores(db, [application]).get(application.id)
    base = chosen or (application.base_resume if application is not None else None)
    steps = _steps(("saved", job.created_at), ("proposed", proposal.created_at))
    return _item(db, "needs_you", job, application=application, proposal=proposal, base=base,
                 score=score, status=proposal.status, steps=steps)


# ---------------------------------------------------------------------------- counts


def _gaps_to_close(db: Session) -> tuple[int, int]:
    """(jobs, gaps): jobs on the `gaps` rung (an open gap analysis is their next step) and the gaps
    still unanswered across them."""
    jobs = list(db.scalars(
        select(Job).where(Job.id.in_(
            select(TailoringSession.job_id).where(TailoringSession.status == "open")
        ))
    ))
    on_gaps = [st for st in stage.for_job_rows(db, jobs).values() if st.rung == "gaps"]
    return len(on_gaps), sum(st.gaps_total - st.gaps_done for st in on_gaps)


def _to_health_check(db: Session) -> list[str]:
    """Selectable base resumes with no health report yet, or one the resume has changed since."""
    out = []
    for slug in db.scalars(
        select(BaseResume.slug).where(base_resume_data.selectable_filter()).order_by(BaseResume.slug)
    ):
        report = resume_lint.latest_report(db, "base", slug)
        if report is None or resume_lint.is_stale(db, report):
            out.append(slug)
    return out


def _counts(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A count of zero is nothing to do: left out, so the page shows only what is there."""
    return [entry for entry in entries if entry["count"]]


# ---------------------------------------------------------------------------- this week


def _week(sent: list[search_summary.Sent], zone: tzinfo, today_local: date) -> dict[str, Any]:
    days = [today_local - timedelta(days=WEEK_DAYS - 1 - i) for i in range(WEEK_DAYS)]
    first = days[0]

    def local(value: datetime) -> date:
        return value.astimezone(zone).date()

    applied = {day: 0 for day in days}
    for s in sent:
        if (day := local(s.applied_at)) in applied:
            applied[day] += 1

    def reached_this_week(statuses) -> int:
        # Dated events only: a backfilled status has no day.
        return sum(
            1 for s in sent
            if (at := s.first_reached_at(statuses)) is not None and first <= local(at) <= today_local
        )

    return {
        "days": [{"date": day.isoformat(), "applied": applied[day]} for day in days],
        "applied": sum(applied.values()),
        "replies": reached_this_week(REPLY_STATUSES),
        "interviews": reached_this_week(INTERVIEW_STATUSES),
        "applied_all_time": len(sent),
    }


# ---------------------------------------------------------------------------- the payload


def build(db: Session, *, zone: tzinfo = UTC, zone_label: str = "UTC",
          now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    unsent = _unsent(db)
    rungs = stage.for_applications(db, unsent)
    pickers: dict[str, Callable[[], dict[str, Any] | None]] = {
        "offer": lambda: _offer(db),
        "pdf_ready": lambda: _pdf_ready(db, unsent, rungs),
        "needs_you": lambda: _needs_you(db, now),
    }
    next_up = next((item for kind in NEXT_UP_ORDER if (item := pickers[kind]()) is not None), None)

    sent = search_summary.sent_applications(db)
    quiet, _ = search_summary.quiet(sent, after_days=QUIET_FOLLOW_UP_DAYS, now=now)
    gap_jobs, gaps_left = _gaps_to_close(db)
    to_check = _to_health_check(db)
    return {
        "today": now.astimezone(zone).date().isoformat(),
        "time_zone": zone_label,
        "next_up": next_up,
        "also": _counts([
            {"key": "to_approve", "count": inbox_readiness.summary(db)["to_review"],
             "href": "/proposals"},
            {"key": "to_check", "count": sum(st.rung == "tailored" for st in rungs.values()),
             "href": "/applications?stage=tailored"},
            {"key": "quiet", "count": quiet, "days": QUIET_FOLLOW_UP_DAYS,
             "href": "/applications?status=applied"},
        ]),
        "more": _counts([
            {"key": "gaps_to_close", "count": gap_jobs, "gaps": gaps_left,
             "href": "/applications?stage=gaps"},
            {"key": "health_check", "count": len(to_check),
             "href": f"/base-resumes/{to_check[0]}/health" if len(to_check) == 1 else "/base-resumes"},
        ]),
        "week": _week(sent, zone, now.astimezone(zone).date()),
    }
