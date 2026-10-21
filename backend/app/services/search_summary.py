"""The search summary: what happened to the applications you sent, for Analytics' lead card and
tiles (GET /api/explore/search-summary). Read-only.

Read from the dated status-event log (docs/entities/application.md, "Status-event log"). An event the
migration backfilled carries the application's last update time, not when its status changed, so it
counts for status (heard back, interview, offer, quiet) and never for timing (days to hear back, the
week a reply landed). Every share goes through `rates.rate` (owner decision D7). `Sent` and
`sent_applications` are also Today's reader of the same log (services/today.py).
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.application_status_event import ApplicationStatusEvent
from app.models.base_resume import BaseResume
from app.services import explore_gaps, rates
from app.services.explore_activity import bucket_for, week_start

# A reply is any word back from the employer: a no, an interview, an offer.
REPLY_STATUSES = frozenset({"rejected", "interviewing", "offered", "accepted"})
# Interviewing or later, so the funnel nests: an offer recorded without an interview event still
# reached the interview stage, as a current status of offered already does.
INTERVIEW_STATUSES = frozenset({"interviewing", "offered", "accepted"})
OFFER_STATUSES = frozenset({"offered", "accepted"})
# Statuses an application sits on while nothing has happened since it was sent (None: an old row
# with an applied date and no status).
WAITING_STATUSES = frozenset({"applied", None})

# "No reply after N days" counts an application only once N days have passed since it was sent.
# Sources disagree on when silence means no (14 to 45 days), so 30 sits between them; an
# application sent more recently is neither quiet nor not, and stays out of both counts.
QUIET_AFTER_DAYS = 30
# A median and a 25th-75th percentile range from fewer than five replies move with every new one,
# so below five the summary sends the count so far and no days.
MIN_REPLIES_FOR_TIMING = 5
# The longest window asked for as a number of weeks (ten years); anything longer is "all".
MAX_WEEKS = 520

_DAY_SECONDS = 86400


@dataclass(frozen=True)
class _Event:
    from_status: str | None
    to_status: str
    at: datetime
    backfilled: bool


@dataclass
class Sent:
    """One application that was sent (it has `applied_at`), with its status events, oldest first."""

    id: UUID
    base_resume: str
    status: str | None
    applied_at: datetime
    events: list[_Event] = field(default_factory=list)

    def _since_sent(self) -> list[_Event]:
        # A backfilled event's time is not when it happened, so it is never "before sending".
        return [e for e in self.events if e.backfilled or e.at >= self.applied_at]

    def reached(self, statuses: Collection[str]) -> bool:
        """Its current status is one of `statuses`, or an event after sending moved it to one (a
        backfilled event counts: its status is real, only its time is not)."""
        return self.status in statuses or any(e.to_status in statuses for e in self._since_sent())

    def first_reached_at(self, statuses: Collection[str]) -> datetime | None:
        """When it first reached one of `statuses`; None when it never did or that time is unknown
        (the first such event is a backfilled one)."""
        for e in self._since_sent():
            if e.to_status in statuses:
                return None if e.backfilled else e.at
        return None

    def days_to_reply(self) -> float | None:
        """Days from sending to the first reply, only when both dates are real: the reply is a dated
        event that moved the application on from Applied. A jump from Draft straight to a reply
        stamps `applied_at` at that moment, which says nothing about waiting."""
        for e in self._since_sent():
            if e.to_status in REPLY_STATUSES:
                if e.backfilled or e.from_status != "applied":
                    return None
                return (e.at - self.applied_at).total_seconds() / _DAY_SECONDS
        return None

    def is_quiet(self) -> bool:
        """Nothing happened after sending: still waiting, and never a reply."""
        return self.status in WAITING_STATUSES and not self.reached(REPLY_STATUSES)


def sent_applications(db: Session, *, source: str | None = None) -> list[Sent]:
    """Every sent application (`applied_at` set), with its events: two queries, whatever the count.
    `source` ("user" | "agent") keeps only applications of that origin."""
    stmt = select(
        Application.id, Application.base_resume, Application.status, Application.applied_at
    ).where(Application.applied_at.is_not(None))
    events = (
        select(
            ApplicationStatusEvent.application_id,
            ApplicationStatusEvent.from_status,
            ApplicationStatusEvent.to_status,
            ApplicationStatusEvent.at,
            ApplicationStatusEvent.backfilled,
        )
        .join(Application, Application.id == ApplicationStatusEvent.application_id)
        .where(Application.applied_at.is_not(None))
        # id: a stable tie-break only.
        .order_by(ApplicationStatusEvent.at, ApplicationStatusEvent.id)
    )
    if source:
        stmt = stmt.where(Application.source == source)
        events = events.where(Application.source == source)
    sent = {
        row.id: Sent(row.id, row.base_resume, row.status, row.applied_at)
        for row in db.execute(stmt)
    }
    for app_id, from_status, to_status, at, backfilled in db.execute(events):
        sent[app_id].events.append(_Event(from_status, to_status, at, bool(backfilled)))
    return list(sent.values())


def quiet(sent: list[Sent], *, after_days: int, now: datetime) -> tuple[int, int]:
    """(quiet, eligible): of the applications sent at least `after_days` ago, how many have heard
    nothing since."""
    cutoff = now - timedelta(days=after_days)
    eligible = [s for s in sent if s.applied_at <= cutoff]
    return sum(s.is_quiet() for s in eligible), len(eligible)


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 1) if values else None


def _timing(cohort: list[Sent]) -> dict[str, Any]:
    days = sorted(d for s in cohort if (d := s.days_to_reply()) is not None)
    if len(days) < MIN_REPLIES_FOR_TIMING:
        return {"replies": len(days), "median_days": None, "p25_days": None, "p75_days": None}
    p25, _, p75 = statistics.quantiles(days, n=4, method="inclusive")
    return {"replies": len(days), "median_days": _median(days), "p25_days": round(p25, 1),
            "p75_days": round(p75, 1)}


def _score_gain(db: Session, source: str | None, since: datetime | None) -> dict[str, Any]:
    """The tailoring lift (`explore_gaps.lift_pairs`, the Score gain chart's rows) as medians:
    tailored minus base, and each side on its own."""
    pairs = explore_gaps.lift_pairs(db, source=source, since=since)
    return {
        "n": len(pairs),
        "median": _median([tailored - base for _, base, tailored in pairs]),
        "median_base": _median([base for _, base, _ in pairs]),
        "median_tailored": _median([tailored for _, _, tailored in pairs]),
    }


def _by_resume(db: Session, cohort: list[Sent]) -> list[dict[str, Any]]:
    groups: dict[str, list[Sent]] = defaultdict(list)
    for s in cohort:
        groups[s.base_resume].append(s)
    # The resume's row whatever its state: an application outlives archiving and a soft delete.
    rows = {
        slug: (name, hue)
        for slug, name, hue in db.execute(
            select(BaseResume.slug, BaseResume.display_name, BaseResume.color_hue).where(
                BaseResume.slug.in_(list(groups))
            )
        )
    } if groups else {}
    out = []
    for slug, apps in groups.items():
        name, hue = rows.get(slug, (None, None))
        applied = len(apps)
        out.append({
            "slug": slug,
            "name": name or None,
            "color_hue": hue,
            "applied": applied,
            "heard_back": rates.rate(sum(s.reached(REPLY_STATUSES) for s in apps), applied),
            "interview": rates.rate(sum(s.reached(INTERVIEW_STATUSES) for s in apps), applied),
        })
    return sorted(out, key=lambda row: (-row["applied"], row["slug"]))


def _window_start(sent: list[Sent], weeks: int | None, this_monday: date) -> date:
    if weeks is not None:
        return this_monday - timedelta(weeks=weeks - 1)
    first = min((s.applied_at for s in sent), default=None)
    return bucket_for(first, "week") if first is not None else this_monday


def build(
    db: Session, *, weeks: int | None, source: str | None, now: datetime | None = None
) -> dict[str, Any]:
    """The summary over the last `weeks` calendar weeks (Monday-based, UTC, this one included), or
    everything since the first application sent when `weeks` is None. `source` ("user" | "agent")
    keeps only applications of that origin; None is all."""
    now = now or datetime.now(UTC)
    sent = sent_applications(db, source=source)
    this_monday = week_start(now.astimezone(UTC).date())
    start = _window_start(sent, weeks, this_monday)
    start_at = datetime.combine(start, time.min, tzinfo=UTC)
    cohort = [s for s in sent if s.applied_at >= start_at]

    applied = len(cohort)
    heard_back = sum(s.reached(REPLY_STATUSES) for s in cohort)
    interview = sum(s.reached(INTERVIEW_STATUSES) for s in cohort)
    offer = sum(s.reached(OFFER_STATUSES) for s in cohort)
    quiet_count, quiet_of = quiet(cohort, after_days=QUIET_AFTER_DAYS, now=now)

    week_starts = [start + timedelta(weeks=i) for i in range((this_monday - start).days // 7 + 1)]
    applied_by_week = Counter(bucket_for(s.applied_at, "week") for s in cohort)
    # A reply lands in the week it came, whenever its application was sent.
    reply_dates = [at for s in sent if (at := s.first_reached_at(REPLY_STATUSES)) is not None]
    replies_by_week = Counter(bucket_for(at, "week") for at in reply_dates if at >= start_at)
    undated = sum(
        s.reached(REPLY_STATUSES) and s.first_reached_at(REPLY_STATUSES) is None for s in cohort
    )

    return {
        "weeks": weeks,
        "window_start": start.isoformat(),
        "source": source or "all",
        "applied": applied,
        "applied_per_week": round(applied / len(week_starts), 1),
        "heard_back": rates.rate(heard_back, applied),
        "interview": rates.rate(interview, heard_back),
        "offer": rates.rate(offer, interview),
        "time_to_hear_back": _timing(cohort),
        "quiet": {"after_days": QUIET_AFTER_DAYS, **rates.rate(quiet_count, quiet_of)},
        "score_gain": _score_gain(db, source, start_at if weeks is not None else None),
        "by_resume": _by_resume(db, cohort),
        "series": [
            {
                "week_start": ws.isoformat(),
                "applied": applied_by_week.get(ws, 0),
                "replies": replies_by_week.get(ws, 0),
            }
            for ws in week_starts
        ],
        "undated_replies": undated,
        "min_rate_n": rates.MIN_RATE_N,
        "min_replies_for_timing": MIN_REPLIES_FOR_TIMING,
    }
