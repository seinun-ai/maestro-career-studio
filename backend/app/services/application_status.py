"""Changing an application's status: the one writer, and what a change does besides storing it.

`set_status` is the only code that writes `Application.status` (SYSTEM.md
{#inv-status-through-set-status}, pinned by tests/test_status_events.py): it writes the column and,
when the value changes, one dated `ApplicationStatusEvent`, so Analytics and Today read real
dates. `apply_status_effects` is shared by the PATCH route and the sync request applier, so a status
set from either side stamps the date, links earlier answers and closes the job's open proposals the
same way.
"""

import unicodedata
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.application_proposal import ApplicationProposal
from app.models.application_status_event import ApplicationStatusEvent
from app.services import filled_answers
from app.services import proposals as proposal_svc

# Stages that imply the application was submitted.
SUBMITTED_STAGES = ("applied", "interviewing", "offered", "accepted")

# Who said the status changed: `ApplicationStatusEvent.source`. An MCP client's own name
# (`clientInfo.name`, e.g. "claude-ai") is the source of an agent's change; these words are the rest.
YOU = "you"  # the web app (REST PATCH, Mark applied, the Agent inbox's attest)
MCP = "mcp"  # an MCP client that sent no name, or a name that is one of these words
MAIL = "mail"  # MCP update_application with from_email: read from the user's job email
COMPANION = "companion"  # the Companion's extension origin: its PATCH, Apply and the Submit it saw
TAILOR = "tailor"  # the tailor pipeline made the job's first draft (Tailor, Quick tailor)
FROM_BASE = "from_base"  # POST /applications/from-base made the first draft (Use resume as is)
SYNC = "sync"  # the owner applied the other copy's request, which did not say who asked
BACKFILL = "backfill"  # the migration that made the log (rows marked `backfilled`)
SOURCE_WORDS = frozenset({YOU, MCP, MAIL, COMPANION, TAILOR, FROM_BASE, SYNC, BACKFILL})
_SOURCE_MAX = 120  # the MCP client label's own cap (write_origin)


def clean_source(value: object, fallback: str = SYNC) -> str:
    """A stored source: text without control characters, at most 120 characters, else `fallback`
    (a sync request's payload is the other copy's data)."""
    if not isinstance(value, str):
        return fallback
    visible = "".join(c for c in value if unicodedata.category(c) != "Cc").strip()
    return visible[:_SOURCE_MAX] or fallback


def source_of(origin, *, companion: bool, from_email: bool = False) -> str:
    """Who a REST status write speaks for. `origin` is the request's `write_origin.WriteOrigin`; an
    MCP write names its client, unless that name is one of the source words (a client cannot pass
    itself off as you or as mail). `from_email`: the body said the change was read from mail."""
    if from_email:
        return MAIL
    if origin.origin == "mcp":
        name = clean_source(origin.detail, MCP)
        return MCP if name.lower() in SOURCE_WORDS else name
    return COMPANION if companion else YOU


def set_status(session: Session, application: Application, to_status: str | None,
               source: str) -> ApplicationStatusEvent | None:
    """Write `application.status` and, when it changes, one event saying so; the caller commits.

    A new application's first status counts as a change from None. Clearing the status (None)
    writes the column only: an event always names what the status became. The event carries
    `application_id` before the flush because the sync flush guard ties a row to its job by that
    column (SYSTEM.md {#inv-flush-guard}); a pending application gets its id here for that.
    Source words: YOU, MCP (or the client's own name), MAIL, COMPANION, TAILOR, FROM_BASE, SYNC,
    BACKFILL above.
    """
    before = application.status
    if to_status == before:
        return None
    application.status = to_status
    if to_status is None:
        return None
    if application.id is None:
        application.id = uuid.uuid4()
    event = ApplicationStatusEvent(application_id=application.id, from_status=before,
                                   to_status=to_status, source=clean_source(source, YOU))
    session.add(event)
    return event


def _stamp_applied_at(application: Application, fields: set[str]) -> None:
    """Keep applied_at in sync with the status transition, unless the caller set it in this
    same change (their value wins). Any submitted stage stamps the date once if unset; dropping
    back to "draft" clears it; rejected/withdrawn keep whatever is there (they don't imply an
    application happened)."""
    if "status" not in fields or "applied_at" in fields:
        return
    if application.status in SUBMITTED_STAGES:
        if application.applied_at is None:
            application.applied_at = datetime.now(UTC)
    elif application.status == "draft":
        application.applied_at = None


def _close_open_proposals(db: Session, application: Application) -> None:
    """User override (2026-08-01): marking the application applied+ means they completed it
    themselves, so resolve any open proposal on the JOB (linked or not; one open proposal per
    job) instead of leaving it squatting in the triage/queued lanes. Closed as a posting-scoped
    decline with an honest consent event; this also releases an approved proposal's cap slot
    and, via the declined-job guard, stops the hunt re-proposing a posting already applied to.
    Rejected/withdrawn applications deliberately do NOT close proposals."""
    open_props = db.scalars(
        select(ApplicationProposal).where(
            ApplicationProposal.job_id == application.job_id,
            ApplicationProposal.status.in_(tuple(proposal_svc.OPEN_STATUSES)),
        )
    ).all()
    for prop in open_props:
        try:
            proposal_svc.transition(
                db, prop, "rejected",
                consent={"channel": "frontend", "note": "user marked the application applied"},
                reason=proposal_svc.APPLIED_MANUALLY,
            )
        except proposal_svc.TransitionError:
            # A concurrent transition beat us to a terminal state; the user's status change
            # must not fail over ledger housekeeping.
            continue


def apply_status_effects(db: Session, application: Application, fields: set[str]) -> None:
    """Everything a status change implies, after the new values are set and before the caller
    commits. ``fields`` names what this change set."""
    _stamp_applied_at(application, fields)
    if "status" in fields and application.status in SUBMITTED_STAGES:
        # Marked applied: the job's receipt rows posted before it had an application are its.
        filled_answers.link_unlinked(db, application)
        _close_open_proposals(db, application)


def apply_status_and_notes(db: Session, application: Application, values: dict,
                           source: str = SYNC) -> None:
    """A status and/or notes change queued by the other copy, applied under the same rules as the
    PATCH route, then committed. `source` is who asked on the other copy (the request carries it)."""
    if "status" in values:
        set_status(db, application, values["status"], source)
    if "notes" in values:
        application.notes = values["notes"]
    apply_status_effects(db, application, set(values))
    db.commit()
