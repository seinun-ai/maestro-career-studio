"""Autofill data feeds for the browser extension (beyond the static profile):
normalized employment blocks for structured work-history form fill, and the
resume's skills for the token inputs an ATS renders its skills picker as.

Both feeds read the RESUME, not the autofill profile. The profile holds the
answers that are the same on every application (name, address, work
authorization); employment and skills are the answers that are tailored per
application, and taking them from anywhere else would let the extension send an
employer something the resume beside it does not say."""

import hashlib
import logging
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.application import Application
from app.models.autofill_field_observation import AutofillFieldObservation
from app.schemas.autofill_choose import ChooseRequest, ChooseResponse
from app.schemas.autofill_telemetry import TelemetryBatch, TelemetryObservation
from app.services import (
    autofill_choose,
    autofill_profile,
    autofill_telemetry,
    base_resume_data,
    eeo_consent,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/autofill", tags=["autofill"])

_CURRENT_TOKENS = {"present", "current", "now"}


def _clean_line(bullet: str) -> str:
    # Strip inline ** bold and backtick spans BEFORE trimming leading bullet
    # markers (the lstrip below would otherwise eat a leading "**"). __ is left
    # intact so dunder identifiers survive (mirrors qa._plain_text, fix B7).
    cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", bullet, flags=re.DOTALL).replace("`", "")
    return cleaned.strip().lstrip("-*•").strip()


def _employment_blocks(resume_json: dict[str, Any]) -> list[dict[str, Any]]:
    blocks = []
    for entry in resume_json.get("experience", []):
        if not isinstance(entry, dict) or not entry.get("enabled", True):
            continue
        end = (entry.get("end_date") or "").strip()
        current = not end or end.lower() in _CURRENT_TOKENS
        blocks.append(
            {
                "employer": entry.get("company") or "",
                "title": entry.get("role") or "",
                # Workday renders a Location box in every work-experience block
                # and it was the block's most-observed unfilled field. The
                # resume model has always carried it; only this payload dropped
                # it, so the extension's rule had nothing to write.
                "location": entry.get("location") or "",
                "start_date": entry.get("start_date") or "",
                "end_date": None if current else end,
                "current": current,
                # Sentence-per-line plain text: no bullet markers, no separators,
                # no title/company prefixes — pasted verbatim into Description
                # textareas by the extension.
                "description": "\n".join(
                    cleaned
                    for bullet in entry.get("bullets") or []
                    if isinstance(bullet, str) and (cleaned := _clean_line(bullet))
                ),
            }
        )
    return blocks


def _resume_skills(resume_json: dict[str, Any]) -> list[str]:
    """Every skill on the resume, flat, in resume order.

    The stored shape is a list of `{category, items}` groups — the resume
    renders them grouped, an ATS skills picker takes them one at a time — so the
    grouping is dropped here rather than in the extension, which has no reason
    to know the resume's section model.

    Order is the resume's own, and it is load-bearing: the extension writes only
    the first N (a master resume carries 75 skills and no application wants all
    of them), so the first group is the one that survives the cap. That is the
    same order the reader of the resume sees first.

    Deliberately NOT capped here. The extension has to report how many it
    skipped, and it can only count that against the true total — a server-side
    cap would make "10 of 14" out of a resume that actually holds 75.

    De-duplicated case-insensitively, first spelling wins: "Python" listed under
    both Languages and ML would otherwise be typed into the form twice.
    """
    skills: list[str] = []
    seen: set[str] = set()
    for group in resume_json.get("skills", []):
        if not isinstance(group, dict):
            continue
        for item in group.get("items") or []:
            if not isinstance(item, str) or not (cleaned := item.strip()):
                continue
            if (key := cleaned.casefold()) in seen:
                continue
            seen.add(key)
            skills.append(cleaned)
    return skills


def _signature_hash(
    host: str, label: str, kind: str, options: list[str] | None
) -> str:
    # sha256 over host + normalized label + kind + sorted option texts
    # (mirrors _hash_text/_hash_extraction in routers/jobs.py).
    norm_label = " ".join(label.strip().lower().split())[:160]
    canonical = "\n".join(
        [host.strip().lower(), norm_label, kind, *sorted(options or [])]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@router.post("/telemetry", status_code=204)
def post_telemetry(
    payload: TelemetryBatch, db: Annotated[Session, Depends(get_db)]
):
    batch_at = datetime.now(UTC).isoformat()
    # Dedupe within the batch in Python BEFORE touching the session: with
    # autoflush=False, two pending inserts for the same unique signature in one
    # flush would both INSERT and IntegrityError (SYSTEM.md §12).
    grouped: dict[str, list[TelemetryObservation]] = {}
    for obs in payload.observations:
        sig = _signature_hash(obs.host, obs.label, obs.kind, obs.options)
        grouped.setdefault(sig, []).append(obs)

    for sig, group in grouped.items():
        first = group[0]
        counts = Counter(obs.outcome for obs in group)
        rule_id = next((obs.rule_id for obs in group if obs.rule_id), None)
        row = db.scalar(
            select(AutofillFieldObservation).where(
                AutofillFieldObservation.signature_hash == sig
            )
        )
        if row is None:
            # First sighting: INSERT inside a SAVEPOINT. A concurrent request can
            # insert the same signature between our SELECT above and this flush;
            # a pure ON CONFLICT would need a clever additive jsonb counter-merge
            # (`||` overwrites, breaking the counters), so instead we catch the
            # unique violation, roll the savepoint back, and merge into the
            # winner's row via the update path below (SYSTEM.md §12).
            try:
                with db.begin_nested():
                    db.add(
                        AutofillFieldObservation(
                            signature_hash=sig,
                            # Belt over the schema length caps: strip+truncate
                            # host and each option text server-side.
                            host=first.host.strip()[:255],
                            label=first.label.strip()[:160],
                            kind=first.kind,
                            options=(
                                [opt.strip()[:200] for opt in first.options[:30]]
                                if first.options
                                else None
                            ),
                            rule_id=rule_id,
                            outcomes=dict(counts),
                            seen_count=len(group),
                            session_marks=[{"at": batch_at, "new": True}],
                        )
                    )
                    db.flush()
                continue
            except IntegrityError:
                row = db.scalar(
                    select(AutofillFieldObservation).where(
                        AutofillFieldObservation.signature_hash == sig
                    )
                )

        merged = dict(row.outcomes)
        for outcome, n in counts.items():
            merged[outcome] = merged.get(outcome, 0) + n
        # JSONB columns: REASSIGN, never mutate in place — no Mutable*
        # tracking on this model, in-place edits are silently lost.
        row.outcomes = merged
        row.seen_count += len(group)
        if rule_id:
            row.rule_id = rule_id
        row.session_marks = [
            *row.session_marks,
            {"at": batch_at, "new": False},
        ][-50:]
    db.commit()
    return Response(status_code=204)


@router.get("/telemetry/summary")
def get_telemetry_summary(db: Annotated[Session, Depends(get_db)]):
    return autofill_telemetry.build_summary(db)


@router.delete("/telemetry")
def clear_telemetry(db: Annotated[Session, Depends(get_db)]) -> dict[str, int]:
    """Delete every stored observation. Returns how many rows went.

    The privacy argument for this table has always been that it has no value
    column — true, and not the whole picture. Each row carries `host` and
    `first_seen_at`, so the accumulated table is a record of WHICH COMPANIES
    were applied to and WHEN. Value-free, still personal. The extension toggle
    stops new rows; nothing removed the old ones, which left a machine-shared-
    or-backed-up Postgres as the user's only recourse.

    Deliberately NOT a capture opt-out: clearing history and declining to
    capture are two decisions, and answering the second while being asked the
    first is the kind of helpfulness nobody consents to. The toggle stays where
    it is (extension card → `⋯`), and the next batch stores normally.

    Returns a count rather than 204 because a destructive control that cannot
    say what it destroyed is one the user has to take on faith.
    """
    deleted = db.execute(delete(AutofillFieldObservation)).rowcount
    db.commit()
    return {"deleted": deleted}


def _selected_resume(
    db: Session, application_id: UUID | None, base: str | None
) -> dict[str, Any]:
    """The resume the extension panel is currently pointed at.

    Shared by both feeds so they can never disagree about WHICH resume: an
    employment history from the tailored application beside a skills list from
    the base resume would be two different documents in one form.
    """
    if (application_id is None) == (base is None):
        raise HTTPException(
            status_code=400, detail="Pass exactly one of application_id or base"
        )
    if application_id is not None:
        application = db.get(Application, application_id)
        if application is None:
            raise HTTPException(status_code=404, detail="Application not found")
        try:
            return application.customized_json or base_resume_data.load_base_resume(
                application.base_resume, db
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        return base_resume_data.load_base_resume(base, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/context")
def get_autofill_context(
    db: Annotated[Session, Depends(get_db)],
    application_id: Annotated[UUID | None, Query()] = None,
    base: Annotated[str | None, Query()] = None,
):
    """Everything one fill needs, resolved from ONE load of the resume.

    Per-section nulls rather than a whole-request failure: the three feeds this
    replaces each degraded independently, and a skills outage must not stop an
    employment fill. A null section means "this feed is unavailable", which the
    widget reports as skipped, not as filled.

    The exception boundary is the resume SELECTION, and it is deliberately
    outside the per-section guard. `_selected_resume` raises for both selectors
    at once, an unknown slug, or a missing application — all questions about
    WHICH resume, none of them a feed outage — so they keep their 400/404.
    Degrading them to a 200 with three nulls would report "every feed is down"
    for what is really a bad query string, and bury the one fault the caller can
    fix. Only the per-feed computation below degrades.

    NEITHER selector is the exception, and it is a valid request: the panel does
    a profile-only fill whenever both of its selects are empty, which a real
    account reaches — the base dropdown renders `<option value=''>` both when
    there are no base resumes and when the list fails to load. Rejecting it
    would leave the widget keeping a separate /api/settings/autofill round-trip
    for exactly the case this endpoint exists to remove. The two resume sections
    are unavailable, which the null contract already covers.

    That relaxation lives HERE, not in `_selected_resume`: that helper is shared
    with /employment-blocks and /skills, whose entire job is to answer "which
    resume?", and where no selector genuinely is a caller error.
    """
    resume_json = (
        None
        if application_id is None and base is None
        else _selected_resume(db, application_id, base)
    )
    # Fixed key set whatever happens, so the client never has to distinguish an
    # absent section from a null one. eeo_consent is metadata only (enabled /
    # policy_version / acknowledged_at) — never EEO answers.
    sections: dict[str, Any] = {
        "profile": None,
        "employment": None,
        "skills": None,
        "eeo_consent": None,
    }
    computations: list[tuple[str, Any]] = [
        ("profile", lambda: autofill_profile.get_profile(db)),
        (
            "eeo_consent",
            lambda: eeo_consent.get_consent(db).model_dump(mode="json"),
        ),
    ]
    if resume_json is not None:
        computations += [
            ("employment", lambda: _employment_blocks(resume_json)),
            ("skills", lambda: _resume_skills(resume_json)),
        ]
    # One guard per section — that, and not the order, is what buys the
    # independent degradation: any single feed can raise and the other two still
    # return. The order below is presentational only.
    for name, compute in computations:
        try:
            sections[name] = compute()
        except Exception:
            # Broad on purpose (see docstring) — but never silent: a null
            # section is indistinguishable from an empty one at the client, so
            # the traceback has to survive somewhere.
            #
            # This would also swallow an HTTPException raised by a feed helper,
            # turning a deliberate 404 into a quiet null. None of the three
            # raises one today; a future feed that wants to fail the request
            # rather than degrade has to be re-raised here explicitly.
            logger.exception("autofill context: the %s section failed", name)
            sections[name] = None

    # EEO answers leave the server ONLY under standing consent, and that is
    # decided here rather than at each consumer (2026-08-04 MCP audit, M1).
    # It used to be enforced only in `mcp_server/client.py`, which meant the
    # endpoint answered with race, gender, veteran and disability answers while
    # `eeo_consent.enabled` was false — and the apply lane drives a real browser,
    # so an agent could read them by navigating to this URL. Protected-class
    # data the user declined to share must not depend on which client asks.
    # The MCP client keeps its own strip: two gates, not a relocated one.
    #
    # Fails CLOSED — a consent section that failed to compute is not consent.
    consent = sections.get("eeo_consent")
    consented = isinstance(consent, dict) and bool(consent.get("enabled"))
    if not consented and isinstance(sections.get("profile"), dict):
        sections["profile"].pop("eeo", None)
    return sections


@router.post("/choose", response_model=ChooseResponse)
def post_choose(
    payload: ChooseRequest,
    db: Annotated[Session, Depends(get_db)],
) -> ChooseResponse:
    """One fast-model pass over the fields the profile fill could not settle.

    application_id is optional and NOT the grounding: the profile is. A job
    sharpens an answer where one exists; its absence must never turn into a
    refusal, because a form you have not tracked yet is the common case for
    this pass. An application_id that IS passed and does not exist stays a
    404 — that is a caller bug, not an absent option.
    """
    application_id = UUID(payload.application_id) if payload.application_id else None
    if application_id is not None and db.get(Application, application_id) is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return ChooseResponse(
        choices=autofill_choose.choose(payload.fields, application_id, db)
    )
