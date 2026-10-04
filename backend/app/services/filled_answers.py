"""The answer receipt: what each page run filled into a job's application form.

Writers: the Companion after every fill run, an agent per form page (MCP
`record_filled_answers`). Readers: the job page's What was submitted tab (`receipt`), the
Companion's Check before you submit group (the POST response) and the agent's final review
(`agent_flags`). Per question the latest answer wins across rows. Flags are computed at read
time against the current profile (`answer_flags`), never stored.

SYSTEM.md {#inv-filled-answers-local}: the values stay in this table. An EEO value is kept only
while EEO consent is recorded, through the fill's own gate (`eeo_consent.withhold_unconsented`),
and no agent read returns one. Nothing here imports telemetry, tracing or an LLM client.
"""

import logging
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.filled_answer import FilledAnswer
from app.models.job import Job
from app.models.resume_version import ResumeVersion
from app.schemas.filled_answers import FilledAnswersCreate, FilledField
from app.services import answer_flags, autofill_catalog, eeo_consent
from app.services.autofill_catalog import Fact

logger = logging.getLogger(__name__)


class ApplicationMismatch(ValueError):
    """The posted application belongs to another job."""


class ApplicationNotFound(LookupError):
    """The posted application does not exist."""


def _consented(session: Session) -> bool:
    """The fill's gate, asked the fill's way: does `profile.eeo` survive
    `withhold_unconsented`? An unreadable consent keeps no EEO value."""
    try:
        consent = eeo_consent.get_consent(session).model_dump(mode="json")
    except Exception:  # noqa: BLE001 - an unreadable consent withholds, it never fails a post
        logger.exception("eeo consent could not be read; keeping no EEO values")
        consent = None
    return "eeo" in eeo_consent.withhold_unconsented({"eeo": {}}, consent)


def _has_answer(answer: Any) -> bool:
    if isinstance(answer, list):
        return any(str(item).strip() for item in answer)
    return bool(str(answer or "").strip())


def _stored(field: FilledField, consented: bool, version: int | None) -> dict[str, Any]:
    data = field.model_dump()
    data["eeo"] = field.eeo or answer_flags.is_eeo(field.question, field.slot)
    data["eeo_answered"] = data["eeo"] and _has_answer(field.answer)
    if data["eeo"] and not consented:
        data["answer"] = None
    data["version"] = version if field.source == "upload" and field.slot == "resume" else None
    return data


def _application_id(session: Session, job: Job, application_id: UUID | None) -> UUID | None:
    if application_id is None:
        return None
    app_row = session.get(Application, application_id)
    if app_row is None:
        raise ApplicationNotFound(f"No application {application_id}.")
    if app_row.job_id != job.id:
        raise ApplicationMismatch("That application belongs to another job.")
    return app_row.id


def _resume_version(session: Session, application_id: UUID | None) -> int | None:
    if application_id is None:
        return None
    return session.scalar(
        select(func.max(ResumeVersion.version_number)).where(
            ResumeVersion.resume_kind == "application",
            ResumeVersion.resume_key == str(application_id),
        )
    )


def _host_of(url: str | None) -> str | None:
    return urlsplit(url or "").hostname or None


def flag_context(session: Session, job: Job) -> tuple[dict[str, Fact], set[str]]:
    """What the flags compare against: the profile as the fill would serve it."""
    profile = eeo_consent.disclosable_profile(session)
    facts = autofill_catalog.build(profile, [], [], company=job.company)
    return facts, answer_flags.saved_eeo(profile)


def _flagged_indexes(fields: list[dict[str, Any]], context) -> list[dict[str, Any]]:
    out = []
    for index, field in enumerate(fields):
        flags = answer_flags.flags_for(field, *context)
        if flags:
            out.append({"index": index, "question": field["question"],
                        "section": field.get("section"), "flags": flags})
    return out


def record(session: Session, job: Job, payload: FilledAnswersCreate) -> dict[str, Any]:
    """Store one page run and answer its flags. Settings are read before the row is added:
    a first settings read may seed a row and commit (SYSTEM.md §11 item 35)."""
    application_id = _application_id(session, job, payload.application_id)
    consented = _consented(session)
    context = flag_context(session, job)
    version = _resume_version(session, application_id)
    fields = [_stored(field, consented, version) for field in payload.fields]
    row = FilledAnswer(job_id=job.id, application_id=application_id, channel=payload.channel,
                       host=payload.host or _host_of(job.source_url), step=payload.step,
                       fields=fields)
    session.add(row)
    session.commit()
    flagged = _flagged_indexes(fields, context)
    return {"id": row.id, "application_id": application_id, "flag_count": len(flagged),
            "flags": flagged}


def _rows(session: Session, job_id: UUID) -> list[FilledAnswer]:
    return list(session.scalars(
        select(FilledAnswer).where(FilledAnswer.job_id == job_id)
        .order_by(FilledAnswer.captured_at, FilledAnswer.id)
    ))


def _fold(text: Any) -> str:
    return " ".join(str(text or "").casefold().split())


def _keyed(row: FilledAnswer, field: dict[str, Any], seen: dict[tuple, int]) -> tuple:
    """step, section, question, and which occurrence of that label this is in its row: a form
    may repeat a label (two "Job Title" boxes under Work Experience)."""
    label = (_fold(field.get("section")), _fold(field.get("question")))
    seen[label] = seen.get(label, -1) + 1
    return (row.step or "", *label, seen[label])


def latest_fields(rows: list[FilledAnswer]) -> list[tuple[FilledAnswer, dict[str, Any]]]:
    """Per question occurrence, the newest answer. Rows run oldest first, so a later row's field
    replaces the same occurrence on the same step and keeps the place the question first had;
    the same question on another step is another answer."""
    latest: dict[tuple, tuple[FilledAnswer, dict[str, Any]]] = {}
    for row in rows:
        seen: dict[tuple, int] = {}
        for field in row.fields or []:
            latest[_keyed(row, field, seen)] = (row, field)
    return list(latest.values())


def _section(step: dict[str, Any], name: str | None) -> dict[str, Any]:
    for section in step["sections"]:
        if section["section"] == name:
            return section
    section = {"section": name, "fields": []}
    step["sections"].append(section)
    return section


def _readable(field: dict[str, Any], flags: list[dict[str, str]], consented: bool) -> dict[str, Any]:
    """The field as the tab reads it. Consent is asked again at read time: an EEO value stored
    while it was recorded is not served once it is withdrawn (`eeo_answered` still says it was)."""
    view = {**field, "flags": flags}
    if field.get("eeo") and not consented:
        view["answer"] = None
    return view


def _step_heads(rows: list[FilledAnswer]) -> dict[str, dict[str, Any]]:
    """Each step's host, channel and time from its NEWEST row, in the order the steps first came."""
    heads: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row.step or ""
        position = heads[key]["order"] if key in heads else len(heads)
        heads[key] = {"order": position, "step": row.step, "host": row.host,
                      "channel": row.channel, "captured_at": row.captured_at, "sections": []}
    return heads


def _grouped(latest, context, rows: list[FilledAnswer], consented: bool) -> tuple[list[dict[str, Any]], int]:
    steps = _step_heads(rows)
    flagged = 0
    for row, field in latest:
        flags = answer_flags.flags_for(field, *context)
        flagged += bool(flags)
        _section(steps[row.step or ""], field.get("section"))["fields"].append(
            _readable(field, flags, consented))
    ordered = sorted(steps.values(), key=lambda step: step["order"])
    return [{k: v for k, v in step.items() if k != "order"} for step in ordered], flagged


def receipt(session: Session, job: Job) -> dict[str, Any]:
    rows = _rows(session, job.id)
    if not rows:
        return {"job_id": job.id, "steps": []}
    steps, flagged = _grouped(latest_fields(rows), flag_context(session, job), rows,
                              _consented(session))
    return {"job_id": job.id, "host": rows[-1].host, "pages": len(steps),
            "captured_at": rows[-1].captured_at, "flag_count": flagged, "steps": steps}


def has_any(session: Session, job_id: UUID) -> bool:
    return bool(session.scalar(select(exists().where(FilledAnswer.job_id == job_id))))


def _stamped(fields: list[dict[str, Any]], version: int | None) -> list[dict[str, Any]] | None:
    """The fields with the resume version on each resume upload that has none; None when
    nothing changes (the column is a plain JSON value, so a changed list is a new list)."""
    stamped = [{**field, "version": version}
               if field.get("source") == "upload" and field.get("slot") == "resume"
               and field.get("version") is None else field for field in fields]
    return stamped if stamped != fields else None


def link_unlinked(session: Session, application: Application) -> int:
    """Late linking: the job's rows posted before it had an application belong to this one,
    and their resume uploads take the application's latest resume version, as a post made with
    the application would have. The caller commits; `application.id` must be set (flushed)
    and the version recorded first."""
    rows = session.scalars(select(FilledAnswer).where(
        FilledAnswer.job_id == application.job_id, FilledAnswer.application_id.is_(None))).all()
    version = _resume_version(session, application.id)
    for row in rows:
        row.application_id = application.id
        if version is not None and (stamped := _stamped(row.fields or [], version)) is not None:
            row.fields = stamped
    return len(rows)


def _agent_view(row: FilledAnswer, field: dict[str, Any], flags: list[dict[str, str]]) -> dict[str, Any]:
    view = {"step": row.step, "question": field.get("question"), "section": field.get("section"),
            "source": field.get("source"), "eeo": bool(field.get("eeo")), "flags": flags}
    if view["eeo"]:
        view["eeo_answered"] = bool(field.get("eeo_answered"))
    else:
        view["answer"] = field.get("answer")
    return view


def agent_flags(session: Session, job: Job | None) -> list[dict[str, Any]]:
    """The job's flagged answers for an agent's final review, latest per question. An EEO
    answer's value never goes to an agent, consent or not: `eeo_answered` says whether one was
    given (SYSTEM.md {#inv-filled-answers-local})."""
    rows = _rows(session, job.id) if job is not None else []
    if not rows:
        return []
    context = flag_context(session, job)
    flagged = ((row, field, answer_flags.flags_for(field, *context))
               for row, field in latest_fields(rows))
    return [_agent_view(row, field, flags) for row, field, flags in flagged if flags]
