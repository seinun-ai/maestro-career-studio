"""Deterministic base-resume → Career KB classification and apply.

Zero LLM calls. Classification is read-only; apply writes drafts, drift notes,
and — on a near-identity hit whose base-side role title is strictly richer —
entity title upgrades, the one entity write here that changes a pre-existing row.
Reuses consolidation's identity keys, its near-identity matcher, and the pinned
local embedder.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base_resume import BaseResume
from app.models.career_kb import KBEntity, KBPoint, KBPortLog, KBProfile
from app.schemas.career_kb import ConsolidationReport
from app.services.base_resume_data import load_base_resume
from app.services.kb_consolidation import (
    _existing_cert_index,
    _existing_edu_index,
    _existing_exp_index,
    _existing_extra_index,
    _existing_proj_index,
    _merge_skills,
    _norm,
    collect_entries,
    find_near_identity,
    identity_key,
    point_text_key,
    richer_experience_title,
    upgrade_experience_title,
)

SYNC_DRIFT_COSINE = 0.90  # conservative; borderline rephrasing -> "new"

# (point_id, resume_key, section, normalized text) — see _drift_key.
DriftKey = tuple[UUID | None, str, str, str]


@dataclass
class SyncItem:
    # "in_sync" | "drift" | "recorded" | "new". The tier is "recorded" while
    # the count key is "recorded_drift" — deliberate, not a typo.
    tier: str
    section: str
    entity_id: UUID | None
    entity_proposal: dict | None
    matched_point_id: UUID | None
    text: str
    # Set only when this item reached its entity by NEAR match and the base's
    # role title is strictly richer than the stored one. classify() computes it
    # (a proposal costs no write); apply() is what performs the rename. None
    # everywhere else, including on every exact-key hit.
    title_upgrade: str | None = None


def _indexes(session: Session) -> dict[str, dict[tuple, KBEntity]]:
    return {
        "experience": _existing_exp_index(session),
        "projects": _existing_proj_index(session),
        "education": _existing_edu_index(session),
        "certifications": _existing_cert_index(session),
        "extra": _existing_extra_index(session),
    }


# Dated sections: entity-proposal field -> resume-entry field. Certifications
# (bare string) and extra sections (detail_json payload) stay special-cased.
_DATED_PROPOSAL_FIELDS = {
    "experience": {"kind": "experience", "title": "role", "org": "company",
                   "start_date": "start_date", "end_date": "end_date"},
    "projects": {"kind": "project", "title": "name", "org": None,
                 "start_date": "date", "end_date": None},
    "education": {"kind": "education", "title": "degree", "org": "institution",
                  "start_date": "start_date", "end_date": "end_date"},
}


def _proposal(section: str, entry: Any) -> dict:
    if section == "certifications":
        return {"kind": "certification", "title": str(entry or "").strip(), "org": None}
    e = entry if isinstance(entry, dict) else {}
    spec = _DATED_PROPOSAL_FIELDS.get(section)
    if spec is None:  # extra sections
        return {
            "kind": "extra",
            "title": e.get("heading") or e.get("section_title") or e.get("title") or "",
            "org": None,
            "detail": {
                "section_key": e.get("section_key"),
                "section_type": e.get("section_type"),
                "section_title": e.get("section_title"),
            },
        }
    out: dict[str, Any] = {"kind": spec["kind"]}
    for field, src in spec.items():
        if field == "kind":
            continue
        value = e.get(src) if src else None
        out[field] = (value or "") if field == "title" else (value or None)
    return out


def _active_points(entity: KBEntity) -> list[KBPoint]:
    return [p for p in entity.points if p.state != "retired"]


def _best_cosine(text: str, points: list[KBPoint]) -> tuple[float, KBPoint | None]:
    """Best cosine vs existing points; (0, None) when embeddings are unavailable."""
    if not points:
        return 0.0, None
    try:
        from app.services.ats.embeddings import cosine, embed_texts

        vectors = embed_texts([text] + [p.text for p in points])
        best_point = None
        best_score = -1.0
        query = vectors[0]
        for point, vector in zip(points, vectors[1:], strict=True):
            score = cosine(query, vector)
            if score > best_score:
                best_score = score
                best_point = point
        return best_score, best_point
    except Exception:
        return 0.0, None


def _ladder_bullet(text: str, entity: KBEntity) -> SyncItem:
    points = _active_points(entity)
    key = point_text_key(text)
    for point in points:
        if point_text_key(point.text) == key:
            return SyncItem(
                tier="in_sync",
                section=entity.kind if entity.kind != "project" else "projects",
                entity_id=entity.id,
                entity_proposal=None,
                matched_point_id=point.id,
                text=text,
            )
    score, matched = _best_cosine(text, points)
    if matched is not None and score >= SYNC_DRIFT_COSINE:
        return SyncItem(
            tier="drift",
            section=entity.kind if entity.kind != "project" else "projects",
            entity_id=entity.id,
            entity_proposal=None,
            matched_point_id=matched.id,
            text=text,
        )
    return SyncItem(
        tier="new",
        section=entity.kind if entity.kind != "project" else "projects",
        entity_id=entity.id,
        entity_proposal=None,
        matched_point_id=None,
        text=text,
        )


def _bullets_of(section: str, entry: Any) -> list[str]:
    if section in ("education", "certifications", "extra"):
        return []
    e = entry if isinstance(entry, dict) else {}
    return [b for b in (e.get("bullets") or []) if isinstance(b, str) and b.strip()]


def _skills_new(session: Session, data: dict) -> list[str]:
    profile = session.get(KBProfile, 1)
    have: set[str] = set()
    if profile is not None:
        for grp in profile.skills_json or []:
            if not isinstance(grp, dict):
                continue
            for item in grp.get("items") or []:
                if isinstance(item, str) and item.strip():
                    have.add(_norm(item))
    out: list[str] = []
    seen: set[str] = set()
    for grp in data.get("skills") or []:
        if not isinstance(grp, dict):
            continue
        for item in grp.get("items") or []:
            if not (isinstance(item, str) and item.strip()):
                continue
            key = _norm(item)
            if key in have or key in seen:
                continue
            seen.add(key)
            out.append(item.strip())
    return out


def _drift_key(
    point_id: UUID | None, resume_key: str, section: str, text: str
) -> DriftKey:
    """Identity of one recorded association: this wording, against this point."""
    return (point_id, resume_key, section, _norm(text))


def _recorded_drift_keys(db: Session, slug: str) -> set[DriftKey]:
    """Keys of every KB association already recorded for this base resume.

    Matches port-log rows in ANY direction, NULL included: "recorded" means a
    KB association already documents this wording against this point, whoever
    wrote the row —

      - sync drift notes, from `_apply_drift` below (`from_source`);
      - import-time consolidation provenance, from `kb_consolidation`'s
        `_cluster_points_for_entity` and `_write_verbatim_points`
        (`from_source`);
      - ports back out to a resume, from `career_kb._persist_port`
        (`to_resume`); `tailoring_session` writes these too, but its rows are
        `resume_kind="application"` keyed by application UUID, so this
        slug-scoped query never matches them;
      - legacy pre-migration rows, whose `direction` is NULL.

    Both consequences are intended. Excluding NULL rows would break `apply`
    idempotency against legacy data — a second sync would write a duplicate
    provenance row for one association, rendered twice in point usage (see the
    `direction` contract on `KBPortLog`). And a base resume that was imported
    but never synced classifies a KB-side edit as "recorded" rather than
    "drift": nothing actionable is hidden, because the point's Drifted badge
    already lights from these same rows, and the sync pill exists to count
    only unrecorded material.
    """
    rows = db.scalars(select(KBPortLog).where(KBPortLog.resume_key == slug)).all()
    return {_drift_key(r.point_id, r.resume_key, r.section, r.ported_text) for r in rows}


def _classify_bullets(
    se, entity: KBEntity | None, slug: str, recorded: set[DriftKey]
) -> list[SyncItem]:
    bullets = _bullets_of(se.section, se.entry)
    if entity is None:
        proposal = _proposal(se.section, se.entry)
        return [
            SyncItem(
                tier="new",
                section=se.section,
                entity_id=None,
                entity_proposal=proposal,
                matched_point_id=None,
                text=text,
            )
            for text in bullets
        ]
    items = []
    for text in bullets:
        item = _ladder_bullet(text, entity)
        item.section = se.section
        if item.tier == "drift" and (
            _drift_key(item.matched_point_id, slug, item.section, item.text) in recorded
        ):
            item.tier = "recorded"
        items.append(item)
    return items


def _classify_identity_only(se, entity: KBEntity | None) -> SyncItem:
    # education / certifications / extra: identity-key presence only
    return SyncItem(
        tier="in_sync" if entity is not None else "new",
        section=se.section,
        entity_id=entity.id if entity is not None else None,
        entity_proposal=None if entity is not None else _proposal(se.section, se.entry),
        matched_point_id=None,
        text=_identity_label(se.section, se.entry),
    )


def _match_entity(
    indexes: dict[str, dict[tuple, KBEntity]], se
) -> tuple[KBEntity | None, str | None]:
    """(entity, proposed title upgrade) for one source entry.

    Exact identity key first; on a miss, the conservative near-identity second
    pass, so a base resume whose role title gained a client name stops proposing
    a fresh entity next to the one it already has.

    The upgrade is only PROPOSED here — classify() is read-only, and renaming an
    entity is a write. See ``apply`` for where it lands.
    """
    index = indexes[se.section]
    key = identity_key(se.section, se.entry)
    entity = index.get(key)
    if entity is not None:
        return entity, None
    entity = find_near_identity(se.section, key, index)
    if entity is None or se.section != "experience":
        # Certs and projects never rename on a near hit: their titles carry the
        # exam code / issuer and the only name the project has.
        return entity, None
    role = se.entry.get("role") if isinstance(se.entry, dict) else None
    return entity, richer_experience_title(entity.title, role)


def classify(db: Session, slug: str) -> dict:
    """Read-only tier ladder of one base resume against the Career KB.

    Drift already written to the port log comes back as "recorded", not
    "drift", so a synced resume stops re-reporting the same items forever.
    """
    data = load_base_resume(slug, db)
    indexes = _indexes(db)
    recorded = _recorded_drift_keys(db, slug)
    items: list[SyncItem] = []
    for se in collect_entries([(slug, data)]):
        entity, upgrade = _match_entity(indexes, se)
        if se.section in ("experience", "projects"):
            entry_items = _classify_bullets(se, entity, slug, recorded)
        else:
            entry_items = [_classify_identity_only(se, entity)]
        if upgrade:
            # The proposal rides on the entry's ITEMS, which is where apply()
            # will look. An experience entry with no bullets produces no items
            # at all (see `_classify_bullets`), so its upgrade is dropped here
            # — sync already says nothing whatsoever about a bulletless entry,
            # and the rename inherits exactly that pre-existing scope rather
            # than opening a channel of its own.
            for item in entry_items:
                item.title_upgrade = upgrade
        items.extend(entry_items)
    skills_new = _skills_new(db, data)
    counts = {
        "in_sync": sum(1 for i in items if i.tier == "in_sync"),
        "drift": sum(1 for i in items if i.tier == "drift"),
        "recorded_drift": sum(1 for i in items if i.tier == "recorded"),
        "new": sum(1 for i in items if i.tier == "new"),
        "skills_new": len(skills_new),
    }
    row = db.get(BaseResume, slug)
    return {
        "items": items,
        "skills_new": skills_new,
        "counts": counts,
        "last_kb_synced_at": row.last_kb_synced_at if row is not None else None,
    }


def _identity_label(section: str, entry: Any) -> str:
    if section == "certifications":
        return str(entry or "").strip()
    e = entry if isinstance(entry, dict) else {}
    if section == "education":
        return " ".join(x for x in (e.get("degree"), e.get("institution")) if x)
    return str(e.get("heading") or e.get("section_title") or e.get("title") or "")


def _entity_from_proposal(proposal: dict) -> KBEntity:
    return KBEntity(
        kind=proposal["kind"],
        title=(proposal.get("title") or "").strip() or "(untitled)",
        org=proposal.get("org") or None,
        start_date=proposal.get("start_date") or None,
        end_date=proposal.get("end_date") or None,
        status="completed",
        detail_json=proposal.get("detail") or {},
        origin="base_sync",
    )


def _apply_drift(
    db: Session, slug: str, item: SyncItem, seen_logs: set[DriftKey]
) -> str:
    """Record the base's variant wording as a from_source drift note. Returns
    'drifted', 'seen', or a skip reason."""
    if item.matched_point_id is None or item.entity_id is None:
        return "drift_without_match"
    key = _drift_key(item.matched_point_id, slug, item.section, item.text)
    if key in seen_logs:
        return "seen"
    db.add(
        KBPortLog(
            entity_id=item.entity_id,
            point_id=item.matched_point_id,
            resume_kind="base",
            resume_key=slug,
            section=item.section,
            ported_text=item.text,
            source_text=item.text,
            direction="from_source",
        )
    )
    seen_logs.add(key)
    return "drifted"


def _resolve_entity(
    db: Session, item: SyncItem, created_entities: dict[str, KBEntity]
) -> KBEntity | None:
    if item.entity_id is not None:
        return db.get(KBEntity, item.entity_id)
    if not item.entity_proposal:
        return None
    pkey = json.dumps(item.entity_proposal, sort_keys=True, default=str)
    entity = created_entities.get(pkey)
    if entity is None:
        entity = _entity_from_proposal(item.entity_proposal)
        db.add(entity)
        db.flush()
        created_entities[pkey] = entity
    return entity


def _apply_new(
    db: Session, item: SyncItem, created_entities: dict[str, KBEntity]
) -> str:
    """Create the draft point (and entity if needed). Returns 'created',
    'entity_only', or a skip reason."""
    entity = _resolve_entity(db, item, created_entities)
    if entity is None:
        return "no_entity"
    if item.section in ("education", "certifications", "extra"):
        # Identity-key add: the entity IS the payload; no point.
        return "entity_only"
    if point_text_key(item.text) in {point_text_key(p.text) for p in _active_points(entity)}:
        return "duplicate"
    db.add(
        KBPoint(
            entity_id=entity.id,
            text=item.text,
            state="draft",
            origin="base_sync",
            provenance="user_authored",
        )
    )
    return "created"


def _apply_title_upgrade(db: Session, item: SyncItem) -> str | None:
    """Perform the rename classify() proposed; the applied title, or None.

    This is where the sync path's rename belongs. classify() is read-only and
    ``_entity_from_proposal`` only ever builds a BRAND-NEW entity — a near match
    resolves to an existing one, so it never runs — leaving apply() as the only
    place that touches a matched entity at all. The check is re-run against the
    live row rather than trusted from the report, so nothing renames twice or on
    stale evidence: the second item under a just-renamed entity gets None back.
    """
    if not item.title_upgrade or item.entity_id is None:
        return None
    entity = db.get(KBEntity, item.entity_id)
    if entity is None:
        return None
    if not upgrade_experience_title(entity, item.title_upgrade):
        return None
    return entity.title


def apply(db: Session, slug: str) -> dict:
    """Write drafts, drift notes, title upgrades, and additive skills from
    classify(); stamp sync time.

    The title upgrade is the only entity write here that changes a row this sync did
    not create — a near-matched entity renamed to the base resume's strictly
    richer role title — so it is reported back in ``renamed`` rather than done
    quietly.
    """
    report = classify(db, slug)
    created_entities: dict[str, KBEntity] = {}
    created_points = 0
    drifted = 0
    renamed: list[str] = []
    skipped: list[dict] = []

    seen_logs = _recorded_drift_keys(db, slug)

    for item in report["items"]:
        # Before the tier dispatch: an in_sync/recorded item is still evidence
        # of a near match whose richer title the KB should carry.
        if (upgraded := _apply_title_upgrade(db, item)) is not None:
            renamed.append(upgraded)
        if item.tier in ("in_sync", "recorded"):
            continue
        if item.tier == "drift":
            outcome = _apply_drift(db, slug, item, seen_logs)
            if outcome == "drifted":
                drifted += 1
            elif outcome != "seen":
                skipped.append({"text": item.text, "reason": outcome})
            continue
        outcome = _apply_new(db, item, created_entities)
        if outcome == "created":
            created_points += 1
        elif outcome != "entity_only":
            skipped.append({"text": item.text, "reason": outcome})

    data = load_base_resume(slug, db)
    merge_report = ConsolidationReport()
    _merge_skills(db, [(slug, data)], merge_report)

    row = db.get(BaseResume, slug)
    if row is not None:
        row.last_kb_synced_at = datetime.now(UTC)

    db.flush()
    return {
        "created": created_points,
        "drifted": drifted,
        # Entities renamed to the base resume's richer role title on a near
        # match. Empty on every ordinary sync.
        "renamed": renamed,
        "skipped": skipped,
        # Categories touched, then the skills themselves. `skills` alone cannot
        # be counted — two new items in one category is one entry — so anything
        # summarising this sync reads `skills_added`.
        "skills": list(merge_report.skills_merged),
        "skills_added": list(merge_report.skills_items_added),
        "last_kb_synced_at": row.last_kb_synced_at if row is not None else None,
    }
