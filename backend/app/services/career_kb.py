"""Service helpers for the Career Knowledge Base: profile, points, timeline, detail."""

import copy
import logging
import re
from collections import defaultdict
from collections.abc import Sequence

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.base_resume import BaseResume
from app.models.career_kb import KBDocument, KBEntity, KBPoint, KBPortLog, KBProfile
from app.schemas.career_kb import (
    KBDocumentOut,
    KBEntityDetail,
    KBEntitySummary,
    KBPointOut,
    KBPortItemReport,
    KBPortReport,
    KBPortRequest,
    KBTimelineEvent,
    KBUsageOut,
)
from app.schemas.resume_edit import ResumeEditRequest
from app.services import base_resume_render
from app.services import base_resume_data
from app.services.base_resume_data import write_base_resume_json
from app.services.resume_edit import apply_edits
from app.services.resume_versions import record_version

logger = logging.getLogger(__name__)

_LABEL_MAX = 60

# KB entity kinds map to (plural) resume section keys.
_KIND_TO_SECTION = {"experience": "experience", "project": "projects", "education": "education"}

# Phase 1: KB porting targets are FIXED CORE sections only — custom (extra)
# sections are not a KB port destination yet (2026-07-16 custom-sections design:
# "optional composition is NOT phase 1"). Guards the resolved destination so a
# future _KIND_TO_SECTION change can't silently route KB points into an extra
# section, complementing the request-schema rejection of a supplied section_key.
_CORE_PORT_SECTIONS = frozenset({"experience", "projects", "education"})


def get_or_create_profile(session: Session) -> KBProfile:
    """Return the singleton profile row (id=1), creating it if absent.

    Commit-free: flushes so the row is usable, but leaves the transaction to
    the caller.
    """
    profile = session.get(KBProfile, 1)
    if profile is None:
        profile = KBProfile(id=1)
        session.add(profile)
        session.flush()
    return profile


# ---------------------------------------------------------------------------
# Composed career context (beyond-the-resume) + composed resume data
#
# `compose_context` renders a STRUCTURED-FIRST block for the QA / cover-letter /
# cold-message prompts: identity facts come from entities + profile, never from
# relocated free text, and approved point texts are EXCLUDED (those are
# resume-visible; entity/profile NOTES are the beyond-the-resume layer).
# `compose_resume_data` assembles a validated ResumeData from the KB.

CONTEXT_CHAR_CAP = 6_000


def _date_ordinal(raw: str | None) -> tuple[int, int]:
    """(year, month) parsed from a freeform date string; larger == more recent.

    Unparseable / empty strings sort oldest as ``(0, 0)``.
    """
    match = re.search(r"(\d{4})(?:[-/](\d{1,2}))?", raw or "")
    if not match:
        return (0, 0)
    year = int(match.group(1))
    month = int(match.group(2)) if match.group(2) else 0
    return (year, month)


def _end_sort_key(entity: KBEntity) -> tuple[int, int, int]:
    """Newest-first ranking by ``end_date``.

    An empty ``end_date`` (ongoing / present) is treated as the newest, so it
    sorts ahead of any dated entry; among dated entries, more recent sorts
    first (achieved by negating the parsed ordinal).
    """
    raw = (entity.end_date or "").strip()
    if not raw:
        return (0, 0, 0)
    year, month = _date_ordinal(raw)
    return (1, -year, -month)


def _ongoing_then_recent(entity: KBEntity) -> tuple[int, tuple[int, int, int], str]:
    """Ongoing entities first, then most-recent end_date, then title."""
    return (
        0 if entity.status == "ongoing" else 1,
        _end_sort_key(entity),
        entity.title or "",
    )


def _completed_oldest_first(entity: KBEntity) -> tuple[int, int, str]:
    """Oldest ``end_date`` first — the order in which completed notes are trimmed."""
    year, month = _date_ordinal(entity.end_date)
    return (year, month, entity.title or "")


def _fmt_dates(entity: KBEntity) -> str:
    """A parenthesised date span for an identity line, or '' when undated."""
    start = (entity.start_date or "").strip()
    end = (entity.end_date or "").strip()
    if start and end:
        return f" ({start}–{end})"
    if end:
        return f" ({end})"
    if start:
        return f" ({start}–present)"
    return ""


def _cert_line(entity: KBEntity) -> str:
    return entity.title if not entity.org else f"{entity.title} ({entity.org})"


def compose_context(session: Session) -> str:
    """Beyond-the-resume context for QA/cover/cold prompts, rendered from the KB.

    STRUCTURED-FIRST: identity facts come from entities/profile, never relocated
    text. EXCLUDES approved point texts (resume-visible); includes entity/profile
    NOTES. Archived entities are omitted entirely.
    """
    profile = get_or_create_profile(session)
    entities = list(session.scalars(select(KBEntity).where(KBEntity.status != "archived")))
    edu = [e for e in entities if e.kind == "education"]
    certs = [e for e in entities if e.kind == "certification"]
    depth = sorted(
        [e for e in entities if e.kind in ("experience", "project")],
        key=_ongoing_then_recent,
    )

    identity = ["IDENTITY"]
    if (profile.summary or "").strip():
        identity.append(f"- {profile.summary.strip()}")
    for e in edu:
        identity.append(
            f"- Education: {e.title}" + (f", {e.org}" if e.org else "") + _fmt_dates(e)
        )
    if certs:
        identity.append("- Certifications: " + "; ".join(_cert_line(e) for e in certs))
    if (profile.notes or "").strip():
        identity.append(profile.notes.strip())

    blocks: list[tuple[KBEntity, str]] = []  # (entity, text)
    for e in depth:
        tech = (e.detail_json or {}).get("tech")
        header = (
            f"## {e.title}"
            + (f" — {e.org}" if e.org else "")
            + f" ({e.status}"
            + (f", {tech}" if tech else "")
            + ")"
        )
        body = header + (f"\n{e.notes.strip()}" if (e.notes or "").strip() else "")
        blocks.append((e, body))

    def assemble(block_texts: list[str]) -> str:
        parts = ["\n".join(identity)]
        if block_texts:
            parts.append("DEPTH BEYOND THE RESUME\n" + "\n\n".join(block_texts))
        return "\n\n".join(parts).strip()

    texts = [b for _, b in blocks]
    out = assemble(texts)
    if len(out) > CONTEXT_CHAR_CAP:
        # Trim NOTES of COMPLETED entities oldest-first (keep their header line).
        # Never trim identity or ongoing-entity notes.
        trimmable = sorted(
            [e for e, _ in blocks if e.status == "completed"], key=_completed_oldest_first
        )
        trimmed_titles: list[str] = []
        header_only: dict = {}
        for e in trimmable:
            header_only[e.id] = (
                f"## {e.title}" + (f" — {e.org}" if e.org else "") + f" ({e.status})"
            )
            texts = [header_only.get(be.id, bt) for be, bt in blocks]
            trimmed_titles.append(e.title)
            out = assemble(texts)
            if len(out) <= CONTEXT_CHAR_CAP:
                break
        logger.warning("compose_context trimmed depth notes for: %s", trimmed_titles)
    return out


def compose_resume_data(
    session: Session,
    *,
    entity_ids: list[uuid.UUID] | None = None,
) -> dict:
    """Assemble a validated ResumeData from profile + non-archived entities + APPROVED points.

    `entity_ids=None` composes the WHOLE knowledge base — a master view. That is
    what `GET /api/kb/compose`, `/api/kb/context` and chat's `get_career_context`
    want, and their behaviour is unchanged.

    Passing a list narrows it to those entities, for building a role-targeted
    base resume. Note `is not None`: an EMPTY list is a legitimate selection and
    is falsy, so a truthy check would silently compose the entire KB — the exact
    master-vs-base confusion this parameter exists to prevent.

    Scope limit worth knowing: only experience / projects / education /
    certifications come from entities. `contact`, `summary` and `skills` live on
    KBProfile (there is no per-entity skill data to filter by), so a narrowed
    compose still carries the full skills union and the master summary. Callers
    building a role-targeted base should treat those two as needing an edit —
    see `routers/base_resumes.create_from_kb`.
    """
    from app.schemas.resume import ResumeData

    profile = get_or_create_profile(session)
    stmt = (
        select(KBEntity)
        .where(KBEntity.status != "archived")
        .options(selectinload(KBEntity.points))
    )
    if entity_ids is not None:
        stmt = stmt.where(KBEntity.id.in_(entity_ids))
    entities = sorted(session.scalars(stmt), key=_ongoing_then_recent)

    def approved_bullets(entity: KBEntity) -> list[str]:
        return [
            p.text
            for p in sorted(entity.points, key=lambda p: p.created_at)
            if p.state == "approved"
        ]

    data = {
        "contact": profile.contact_json or {"name": "", "email": ""},
        "summary": profile.summary or None,
        "skills": profile.skills_json or [],
        "experience": [
            {
                "company": e.org or "",
                "role": e.title,
                "location": (e.detail_json or {}).get("location"),
                "start_date": e.start_date or "",
                "end_date": e.end_date,
                "bullets": approved_bullets(e),
            }
            for e in entities
            if e.kind == "experience"
        ],
        "projects": [
            {
                "name": e.title,
                "tech": (e.detail_json or {}).get("tech"),
                "link": (e.detail_json or {}).get("link"),
                "date": (e.detail_json or {}).get("date"),
                "bullets": approved_bullets(e),
            }
            for e in entities
            if e.kind == "project"
        ],
        "education": [
            {
                "institution": e.org or "",
                "degree": e.title,
                "field": (e.detail_json or {}).get("field"),
                "gpa": (e.detail_json or {}).get("gpa"),
                "coursework": (e.detail_json or {}).get("coursework") or [],
                "start_date": e.start_date,
                "end_date": e.end_date,
                "bullets": approved_bullets(e),
            }
            for e in entities
            if e.kind == "education"
        ],
        "certifications": [
            (f"{e.title} ({e.org})" if e.org else e.title)
            for e in entities
            if e.kind == "certification"
        ],
        # The KB has no model for arbitrary custom sections yet, so it composes
        # none. Emit the field explicitly (the ResumeData round-trip would add
        # it anyway) to document that KB->extra composition is deliberately NOT
        # phase 1; do not map cert/project entities to extras by display title.
        "extra_sections": [],
    }
    return ResumeData.model_validate(data).model_dump(mode="json")


def _usage_from_logs(logs: Sequence[KBPortLog], point: KBPoint) -> list[KBUsageOut]:
    # Drift means "the KB point changed after the port". Adapted ports rewrite
    # the text on purpose, so compare against source_text (the point snapshot
    # at port time) when present; verbatim ports (source_text NULL) keep the
    # original ported_text comparison — there the two are the same snapshot.
    return [
        KBUsageOut(
            resume_key=log.resume_key,
            section=log.section,
            ported_text=log.ported_text,
            ported_at=log.ported_at,
            drifted=(
                (log.source_text if log.source_text is not None else log.ported_text) or ""
            ).strip()
            != (point.text or "").strip(),
        )
        for log in logs
    ]


def point_usage(session: Session, point: KBPoint) -> list[KBUsageOut]:
    """Port-log provenance for a point, flagging drift from the current text."""
    logs = session.scalars(
        select(KBPortLog).where(KBPortLog.point_id == point.id).order_by(KBPortLog.ported_at)
    ).all()
    return _usage_from_logs(logs, point)


def _to_point_out(
    session: Session, point: KBPoint, port_logs: Sequence[KBPortLog] | None = None
) -> KBPointOut:
    usage = _usage_from_logs(port_logs, point) if port_logs is not None else point_usage(session, point)
    return KBPointOut(
        id=point.id,
        entity_id=point.entity_id,
        text=point.text,
        state=point.state,
        origin=point.origin,
        origin_detail=point.origin_detail,
        source_document_id=point.source_document_id,
        tags=point.tags_json or [],
        merge_sources=point.merge_sources_json,
        approved_at=point.approved_at,
        created_at=point.created_at,
        updated_at=point.updated_at,
        usage=usage,
    )


def _truncate(text: str) -> str:
    text = text.strip()
    if len(text) <= _LABEL_MAX:
        return text
    return text[: _LABEL_MAX - 1].rstrip() + "…"


def _capture_timeline_events(point: KBPoint) -> list[KBTimelineEvent]:
    """Return one agent-capture event, or none for hand-written points."""
    if point.origin not in {"mcp", "chat"}:
        return []
    captured_by = point.origin_detail or point.origin
    return [
        KBTimelineEvent(
            ts=point.created_at,
            type="point_captured",
            label=f"{_truncate(point.text)} — added by {captured_by}",
        )
    ]


def entity_timeline(
    entity: KBEntity,
    points: Sequence[KBPoint],
    documents: Sequence[KBDocument],
    port_logs: Sequence[KBPortLog],
) -> list[KBTimelineEvent]:
    """Derive a newest-first activity timeline from the entity's rows."""
    # Agent-written rows say who; web/legacy rows keep the bare label.
    created_by = entity.origin_detail or entity.origin
    events: list[KBTimelineEvent] = [
        KBTimelineEvent(
            ts=entity.created_at,
            type="created",
            label=f"Entity created by {created_by}" if created_by else "Entity created",
        )
    ]
    for doc in documents:
        events.append(KBTimelineEvent(ts=doc.created_at, type="doc_added", label=doc.filename))
        if doc.ingest_status == "minted":
            events.append(
                KBTimelineEvent(
                    ts=doc.created_at,
                    type="points_minted",
                    label=doc.ingest_summary or "Points minted",
                )
            )
    for point in points:
        # Only agent captures earn a row. Hand-typed points would flood the
        # timeline of any real entity with no information in return.
        events.extend(_capture_timeline_events(point))
        if point.approved_at is not None:
            events.append(
                KBTimelineEvent(
                    ts=point.approved_at, type="point_approved", label=_truncate(point.text)
                )
            )
    for log in port_logs:
        events.append(
            KBTimelineEvent(ts=log.ported_at, type="ported", label=f"→ {log.resume_key}")
        )
    events.sort(key=lambda ev: ev.ts, reverse=True)
    return events


def entity_summary(session: Session, entity: KBEntity) -> KBEntitySummary:
    points = entity.points
    documents = entity.documents
    last_activity = entity.updated_at
    if points:
        last_activity = max(last_activity, max(p.updated_at for p in points))
    if documents:
        last_activity = max(last_activity, max(d.created_at for d in documents))
    return KBEntitySummary(
        id=entity.id,
        kind=entity.kind,
        title=entity.title,
        org=entity.org,
        status=entity.status,
        origin=entity.origin,
        origin_detail=entity.origin_detail,
        start_date=entity.start_date,
        end_date=entity.end_date,
        point_count=len(points),
        draft_count=sum(1 for p in points if p.state == "draft"),
        document_count=len(documents),
        last_activity=last_activity,
    )


def entity_detail(session: Session, entity: KBEntity) -> KBEntityDetail:
    points = list(entity.points)  # relationship is ordered by created_at
    documents = list(entity.documents)
    point_ids = [p.id for p in points]
    port_logs: Sequence[KBPortLog] = []
    logs_by_point: dict = defaultdict(list)
    if point_ids:
        port_logs = session.scalars(
            select(KBPortLog).where(KBPortLog.point_id.in_(point_ids)).order_by(KBPortLog.ported_at)
        ).all()
        for log in port_logs:
            logs_by_point[log.point_id].append(log)
    summary = entity_summary(session, entity)
    return KBEntityDetail(
        **summary.model_dump(),
        detail=entity.detail_json or {},
        notes=entity.notes,
        points=[
            _to_point_out(session, p, port_logs=logs_by_point.get(p.id, [])) for p in points
        ],
        documents=[KBDocumentOut.model_validate(d) for d in documents],
        timeline=entity_timeline(entity, points, documents, port_logs),
    )


# ---------------------------------------------------------------------------
# Port approved points / entities into a base resume


def _norm(s: str | None) -> str:
    return " ".join((s or "").lower().split())


def _resolve_points(
    session: Session, entity: KBEntity, point_ids: Sequence
) -> list[KBPoint]:
    """Resolve the points to port for an entity.

    Explicit ids must each belong to the entity and be approved; an empty list
    means "all approved points of this entity" (ordered oldest-first).
    """
    if point_ids:
        points: list[KBPoint] = []
        for pid in point_ids:
            point = session.get(KBPoint, pid)
            if point is None or point.entity_id != entity.id or point.state != "approved":
                raise ValueError(
                    f"point {pid} is not an approved point of entity {entity.id}"
                )
            points.append(point)
        return points
    return list(
        session.scalars(
            select(KBPoint)
            .where(KBPoint.entity_id == entity.id, KBPoint.state == "approved")
            .order_by(KBPoint.created_at)
        )
    )


def _match_index(data: dict, entity: KBEntity, section: str) -> int | None:
    """Return the index of an existing resume entry that identifies `entity`."""
    entries = data.get(section) or []
    if section == "experience":
        for i, e in enumerate(entries):
            if (
                _norm(e.get("company")) == _norm(entity.org)
                and _norm(e.get("role")) == _norm(entity.title)
                and (e.get("start_date") or "") == (entity.start_date or "")
            ):
                return i
    elif section == "projects":
        for i, e in enumerate(entries):
            if _norm(e.get("name")) == _norm(entity.title):
                return i
    elif section == "education":
        for i, e in enumerate(entries):
            if _norm(e.get("institution")) == _norm(entity.org) and _norm(
                e.get("degree")
            ) == _norm(entity.title):
                return i
    return None


def _build_entry(entity: KBEntity, section: str, points: Sequence[KBPoint]) -> dict:
    """Build a new resume entry dict from entity fields; optional keys only when present."""
    detail = entity.detail_json or {}
    bullets = [p.text for p in points]
    if section == "experience":
        entry: dict = {
            "company": entity.org or "",
            "role": entity.title,
            "start_date": entity.start_date or "",
            "bullets": bullets,
        }
        if entity.end_date:
            entry["end_date"] = entity.end_date
        if detail.get("location"):
            entry["location"] = detail["location"]
        return entry
    if section == "projects":
        entry = {"name": entity.title, "enabled": False, "bullets": bullets}
        if detail.get("tech"):
            entry["tech"] = detail["tech"]
        if detail.get("link"):
            entry["link"] = detail["link"]
        date_val = detail.get("date") or entity.start_date or entity.end_date
        if date_val:
            entry["date"] = date_val
        return entry
    # education
    entry = {
        "institution": entity.org or "",
        "degree": entity.title,
        "coursework": detail.get("coursework") or [],
        "bullets": bullets,
    }
    if detail.get("field"):
        entry["field"] = detail["field"]
    if detail.get("gpa"):
        entry["gpa"] = detail["gpa"]
    if detail.get("location"):
        entry["location"] = detail["location"]
    if entity.start_date:
        entry["start_date"] = entity.start_date
    if entity.end_date:
        entry["end_date"] = entity.end_date
    if detail.get("graduation_date"):
        entry["graduation_date"] = detail["graduation_date"]
    return entry


def _compose_item_ops(
    entity: KBEntity,
    points: Sequence[KBPoint],
    working: dict,
    report_items: list[KBPortItemReport],
    port_log_rows: list[dict],
) -> list[dict]:
    """Compose the edit ops for one port item against the CURRENT ``working`` copy.

    Matching, bullet-dedup, education deepcopy, and cert-dedup all read from
    ``working`` (not the original snapshot) so items applied earlier in the same
    call are visible here — the caller applies the returned ops immediately.
    Mutates ``report_items`` and ``port_log_rows`` in place.
    """
    ops: list[dict] = []

    if entity.kind == "certification":
        cert_str = entity.title if not entity.org else f"{entity.title} ({entity.org})"
        report_items.append(KBPortItemReport(entity_id=entity.id, created_entry=False))
        existing_certs = list(working.get("certifications") or [])
        if _norm(cert_str) not in {_norm(c) for c in existing_certs}:
            ops.append(
                {"kind": "replace_certifications", "items": existing_certs + [cert_str]}
            )
            port_log_rows.append(
                {
                    "entity_id": entity.id,
                    "point_id": None,
                    "section": "certifications",
                    "ported_text": cert_str,
                }
            )
        return ops

    section = _KIND_TO_SECTION.get(entity.kind)
    if section not in _CORE_PORT_SECTIONS:
        raise ValueError(
            f"entity {entity.id} kind {entity.kind!r} has no core resume section; "
            "Career KB porting targets core sections only, not custom sections"
        )

    idx = _match_index(working, entity, section)
    if idx is not None:
        entry = working[section][idx]
        existing_norms = {_norm(b) for b in (entry.get("bullets") or [])}
        new_points = [p for p in points if _norm(p.text) not in existing_norms]
        skipped = [p for p in points if _norm(p.text) in existing_norms]
        if section == "education":
            # AddBullet can't target education; append via a single ReplaceEntry.
            if new_points:
                value = copy.deepcopy(entry)
                value["bullets"] = list(entry.get("bullets") or []) + [
                    p.text for p in new_points
                ]
                ops.append(
                    {
                        "kind": "replace_entry",
                        "section": "education",
                        "index": idx,
                        "value": value,
                    }
                )
        else:
            for p in new_points:
                ops.append(
                    {"kind": "add_bullet", "section": section, "index": idx, "text": p.text}
                )
        for p in new_points:
            port_log_rows.append(
                {
                    "entity_id": entity.id,
                    "point_id": p.id,
                    "section": section,
                    "ported_text": p.text,
                }
            )
        report_items.append(
            KBPortItemReport(
                entity_id=entity.id,
                ported_point_ids=[p.id for p in new_points],
                skipped_duplicate_point_ids=[p.id for p in skipped],
                created_entry=False,
            )
        )
    else:
        new_entry = _build_entry(entity, section, points)
        ops.append({"kind": "add_entry", "section": section, "value": new_entry})
        if points:
            for p in points:
                port_log_rows.append(
                    {
                        "entity_id": entity.id,
                        "point_id": p.id,
                        "section": section,
                        "ported_text": p.text,
                    }
                )
        else:
            port_log_rows.append(
                {
                    "entity_id": entity.id,
                    "point_id": None,
                    "section": section,
                    "ported_text": "",
                }
            )
        report_items.append(
            KBPortItemReport(
                entity_id=entity.id,
                ported_point_ids=[p.id for p in points],
                skipped_duplicate_point_ids=[],
                created_entry=True,
            )
        )
    return ops


def _compose_tail_ops(
    session: Session, payload: KBPortRequest, skills_merged: list[str]
) -> list[dict]:
    """Compose profile-level skill-merge and summary ops (no port-log rows)."""
    if not (payload.skill_categories or payload.include_profile_summary):
        return []
    profile = get_or_create_profile(session)
    ops: list[dict] = []
    if payload.skill_categories:
        groups = {
            str(g.get("category", "")).casefold(): g for g in (profile.skills_json or [])
        }
        for cat in payload.skill_categories:
            group = groups.get(cat.casefold())
            if group is None:
                continue
            cat_name = group.get("category", cat)
            for skill_item in group.get("items") or []:
                ops.append(
                    {"kind": "add_skill_item", "category": cat_name, "item": skill_item}
                )
            skills_merged.append(cat_name)
    if payload.include_profile_summary and profile.summary:
        ops.append({"kind": "replace_summary", "value": profile.summary})
    return ops


def port_to_resume(
    session: Session, payload: KBPortRequest
) -> tuple[BaseResume, KBPortReport]:
    """Port selected KB entities/points into a base resume, with a provenance log.

    Returns the mutated ``BaseResume`` row and a report. Raises ``LookupError``
    (→404) if the target slug or a referenced entity is unknown, and
    ``ValueError`` (→400) for a master target, a non-approved / cross-entity
    point, or an invalid resulting resume.

    Ops are composed and applied INCREMENTALLY per item against a running
    ``working`` copy, so two items that identity-match the same resume entry
    accumulate cleanly (no education clobber, no experience double-append). Ops
    only ever append or edit-in-place — never RemoveEntry — so indices stay valid.
    """
    target = _load_target(session, payload.target_slug)
    working = copy.deepcopy(target.data_json)
    report_items: list[KBPortItemReport] = []
    port_log_rows: list[dict] = []

    for item in payload.items:
        entity = session.get(KBEntity, item.entity_id)
        if entity is None:
            raise LookupError(f"entity {item.entity_id} not found")
        points = _resolve_points(session, entity, item.point_ids)
        item_ops = _compose_item_ops(entity, points, working, report_items, port_log_rows)
        # Apply now so the next item sees this item's changes.
        working = apply_edits(working, _validated_ops(item_ops))

    skills_merged: list[str] = []
    tail_ops = _compose_tail_ops(session, payload, skills_merged)
    if tail_ops:
        working = apply_edits(working, _validated_ops(tail_ops))

    target = _persist_port(
        session,
        target,
        working,
        port_log_rows,
        summary=f"Ported {len(payload.items)} item(s) from Career KB",
    )
    return target, KBPortReport(items=report_items, skills_merged=skills_merged)


def _load_target(session: Session, target_slug: str) -> BaseResume:
    """Resolve a portable target base resume, rejecting soft-deleted rows."""
    target = session.scalars(
        select(BaseResume).where(
            BaseResume.slug == target_slug, base_resume_data.active_filter()
        )
    ).first()
    if target is None:
        raise LookupError(f"Base resume not found: {target_slug}")
    return target


def _persist_port(
    session: Session,
    target: BaseResume,
    working: dict,
    port_log_rows: list[dict],
    *,
    summary: str,
) -> BaseResume:
    """Persist a port result: data_json, version row, provenance logs, JSON file, PDF.

    Shared by the verbatim port and the adapted port so both get the same
    tolerant-render semantics.
    """
    target.data_json = working
    record_version(session, "base", target.slug, working, source="import", summary=summary)
    for row in port_log_rows:
        session.add(KBPortLog(**row, resume_kind="base", resume_key=target.slug))
    session.commit()

    write_base_resume_json(target.slug, working)
    # Ported text is LLM/user-derived and can break pdflatex. Mirror the base
    # resume edit path: the port is already committed, so a compile failure
    # records render_error rather than losing the edit.
    try:
        base_resume_render.render_base_resume(target.slug, session)
    except LookupError:
        raise
    except ValueError:
        raise
    except Exception as e:  # noqa: BLE001 — LaTeX failure leaves the PDF stale, not the port lost
        logger.warning(
            "PDF re-render failed after KB port for %s", target.slug, exc_info=True
        )
        session.rollback()
        target = session.get(BaseResume, target.slug)
        target.render_error = str(e)[:2000]
        session.commit()
    session.refresh(target)
    return target


def _validated_ops(ops: list[dict]) -> list:
    """Coerce raw op dicts into typed ResumeEdit models via the discriminated union."""
    return ResumeEditRequest.model_validate({"ops": ops}).ops
