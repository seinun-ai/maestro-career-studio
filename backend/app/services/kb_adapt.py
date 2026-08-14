"""AI-assisted Career KB → base resume porting.

Two halves, deliberately split so LLM output never lands unreviewed:

- ``adapt_points`` — pure read + one smart-model call. Proposes the final
  bullet set for the target resume's matching entry (rewritten to its voice,
  overlapping points merged, already-covered points dropped with a reason).
  Persists nothing.
- ``apply_adapted`` — takes the user-approved (possibly edited) bullets,
  re-validates everything server-side, and applies through the same typed-op
  + provenance + version + tolerant-render pipeline as the verbatim port.

The LLM sees short aliases (``p1`` for points, ``b0`` for existing bullets)
instead of UUIDs/indices; every alias it returns is resolved and validated
here — unknown refs are discarded, and selected points it forgot come back as
verbatim additions (fail open toward inclusion, never silent loss).
"""

import copy
import logging
from string import Template

from sqlalchemy.orm import Session

from app.models.base_resume import BaseResume
from app.models.career_kb import KBEntity, KBPoint
from app.schemas.career_kb import (
    KBAdaptApplyRequest,
    KBAdaptBullet,
    KBAdaptDropped,
    KBAdaptProposal,
    KBAdaptRequest,
    KBPortItemReport,
    KBPortReport,
)
from app.services import llm, model_settings, prompts
from app.services.career_kb import (
    _KIND_TO_SECTION,
    _build_entry,
    _load_target,
    _match_index,
    _norm,
    _persist_port,
    _resolve_points,
    _validated_ops,
)
from app.services.resume_edit import apply_edits

logger = logging.getLogger(__name__)

# Bullets from other entries shown to the LLM as a voice reference.
_STYLE_SAMPLE_MAX = 8


def _entity_and_section(session: Session, entity_id) -> tuple[KBEntity, str]:
    entity = session.get(KBEntity, entity_id)
    if entity is None:
        raise LookupError(f"entity {entity_id} not found")
    section = _KIND_TO_SECTION.get(entity.kind)
    if section is None or entity.kind == "certification":
        raise ValueError(
            "certification entities port verbatim; there is nothing to adapt"
        )
    if entity.kind == "extra":
        raise ValueError(
            "custom section entities port directly; there is nothing to adapt"
        )
    return entity, section


def adapt_points(session: Session, payload: KBAdaptRequest) -> KBAdaptProposal:
    """Propose an adapted bullet set for the selected points. Persists nothing.

    Raises ``LookupError`` (→404) for unknown target/entity, ``ValueError``
    (→400) for master targets, certification entities, or an empty selection,
    and ``RuntimeError`` (→502) when the LLM provider is unavailable.
    """
    target = _load_target(session, payload.target_slug)
    entity, section = _entity_and_section(session, payload.entity_id)
    points = _resolve_points(session, entity, payload.point_ids)
    if not points:
        raise ValueError("no approved points to adapt")

    data = target.data_json
    idx = _match_index(data, entity, section)
    existing_bullets = (
        [str(b) for b in (data[section][idx].get("bullets") or [])]
        if idx is not None
        else []
    )

    aliases = [f"p{i + 1}" for i in range(len(points))]
    prompt = _build_prompt(
        session, entity, points, aliases, existing_bullets, data, section, idx
    )
    raw = llm.call_openai(
        prompt=prompt,
        model=model_settings.get_smart_model(session),
        response_format="json",
        trace_name="kb-adapt",
    )
    bullets, dropped = _coerce_proposal(raw, points, aliases, existing_bullets)
    return KBAdaptProposal(
        target_slug=payload.target_slug,
        entity_id=entity.id,
        section=section,
        matched_entry_index=idx,
        create_entry=idx is None,
        existing_bullets=existing_bullets,
        bullets=bullets,
        dropped=dropped,
    )


def _build_prompt(
    session: Session,
    entity: KBEntity,
    points: list[KBPoint],
    aliases: list[str],
    existing_bullets: list[str],
    data: dict,
    section: str,
    matched_index: int | None,
) -> str:
    entity_line = f"{entity.kind}: {entity.title}"
    if entity.org:
        entity_line += f" @ {entity.org}"
    points_block = "\n".join(
        f"{alias} | {point.text}" for alias, point in zip(aliases, points)
    )
    entry_block = (
        "\n".join(f"b{i} | {text}" for i, text in enumerate(existing_bullets))
        or "(none — a new entry will be created for this item)"
    )
    style_block = (
        _style_sample(data, section, matched_index)
        or "(no other bullets on this resume)"
    )
    # Single-pass substitution: point/bullet texts containing a literal $token
    # must never be re-expanded (same reason prompt_assembly uses Template).
    return Template(prompts.get_prompt("kb_adapt", session)).safe_substitute(
        entity_line=entity_line,
        existing_bullets=entry_block,
        points=points_block,
        style_sample=style_block,
    )


def _style_sample(data: dict, section: str, matched_index: int | None) -> str:
    """A few enabled bullets from OTHER entries, as a voice/length reference."""
    sample: list[str] = []
    for sec in ("experience", "projects"):
        for i, entry in enumerate(data.get(sec) or []):
            if sec == section and i == matched_index:
                continue
            if entry.get("enabled") is False:
                continue
            for bullet in entry.get("bullets") or []:
                sample.append(str(bullet))
                if len(sample) >= _STYLE_SAMPLE_MAX:
                    return "\n".join(sample)
    return "\n".join(sample)


def _coerce_proposal(
    raw: dict,
    points: list[KBPoint],
    aliases: list[str],
    existing_bullets: list[str],
) -> tuple[list[KBAdaptBullet], list[KBAdaptDropped]]:
    """Validate the LLM proposal against the real selection. Never trust output.

    Unknown aliases are discarded; a proposed bullet with no valid source is
    unverifiable AI content and is dropped entirely; duplicate/invalid
    ``replaces`` targets are coerced to plain additions; selected points that
    the model neither used nor dropped come back as verbatim additions.
    """
    by_alias = dict(zip(aliases, points))
    bullets_out: list[KBAdaptBullet] = []
    used_replaces: set[int] = set()
    accounted: set = set()

    raw_bullets = raw.get("bullets")
    for item in raw_bullets if isinstance(raw_bullets, list) else []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        sources: list[KBPoint] = []
        raw_sources = item.get("sources")
        for ref in raw_sources if isinstance(raw_sources, list) else []:
            point = by_alias.get(str(ref).strip())
            if point is not None and all(p.id != point.id for p in sources):
                sources.append(point)
        if not sources:
            continue
        replaces = _coerce_replaces(
            item.get("replaces"), len(existing_bullets), used_replaces
        )
        if replaces is not None:
            used_replaces.add(replaces)
            action = "replace"
        elif len(sources) > 1:
            action = "merged"
        elif _norm(text) != _norm(sources[0].text):
            action = "rewritten"
        else:
            action = "kept"
        reason = str(item.get("reason") or "").strip() or None
        bullets_out.append(
            KBAdaptBullet(
                text=text,
                source_point_ids=[p.id for p in sources],
                replaces_bullet_index=replaces,
                action=action,
                reason=reason,
            )
        )
        accounted.update(p.id for p in sources)

    dropped_out: list[KBAdaptDropped] = []
    raw_dropped = raw.get("dropped")
    for item in raw_dropped if isinstance(raw_dropped, list) else []:
        if not isinstance(item, dict):
            continue
        point = by_alias.get(str(item.get("point") or "").strip())
        if point is None or point.id in accounted:
            continue
        dropped_out.append(
            KBAdaptDropped(point_id=point.id, reason=str(item.get("reason") or "").strip())
        )
        accounted.add(point.id)

    for point in points:  # fail open: forgotten points come back verbatim
        if point.id not in accounted:
            bullets_out.append(
                KBAdaptBullet(
                    text=point.text, source_point_ids=[point.id], action="kept"
                )
            )
    return bullets_out, dropped_out


def _coerce_replaces(value, bullet_count: int, used: set[int]) -> int | None:
    """Resolve a ``replaces`` ref ("b2", "2", or 2) to a valid unused index, else None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        index = value
    else:
        ref = str(value).strip().lower()
        if ref.startswith("b"):
            ref = ref[1:]
        if not ref.isdigit():
            return None
        index = int(ref)
    if 0 <= index < bullet_count and index not in used:
        return index
    return None


def apply_adapted(
    session: Session, payload: KBAdaptApplyRequest
) -> tuple[BaseResume, KBPortReport]:
    """Apply user-approved adapted bullets to the target base resume.

    Everything is re-validated here — the proposal is client-held state.
    Raises ``LookupError`` (→404) for unknown target/entity and ``ValueError``
    (→400) for master targets, certification entities, non-approved or
    cross-entity source points, invalid/duplicate replace targets, or a
    fully-deduplicated (empty) result.
    """
    target = _load_target(session, payload.target_slug)
    entity, section = _entity_and_section(session, payload.entity_id)

    points_by_id: dict = {}
    for bullet in payload.bullets:
        for pid in bullet.source_point_ids:
            if pid in points_by_id:
                continue
            point = session.get(KBPoint, pid)
            if point is None or point.entity_id != entity.id or point.state != "approved":
                raise ValueError(
                    f"point {pid} is not an approved point of entity {entity.id}"
                )
            points_by_id[pid] = point

    working = copy.deepcopy(target.data_json)
    idx = _match_index(working, entity, section)

    ops: list[dict] = []
    applied: list = []  # KBAdaptApplyBullet actually landing in the resume
    skipped_ids: list = []

    if idx is None:
        if any(b.replaces_bullet_index is not None for b in payload.bullets):
            raise ValueError(
                "replaces_bullet_index requires a matching entry in the target "
                "resume; it no longer matches — re-run adapt"
            )
        texts: list[str] = []
        seen_norms: set[str] = set()
        for bullet in payload.bullets:
            if _norm(bullet.text) in seen_norms:
                skipped_ids.extend(bullet.source_point_ids)
                continue
            seen_norms.add(_norm(bullet.text))
            texts.append(bullet.text)
            applied.append(bullet)
        entry = _build_entry(entity, section, [])
        entry["bullets"] = texts
        ops.append({"kind": "add_entry", "section": section, "value": entry})
        created_entry = True
    else:
        entry = working[section][idx]
        existing = [str(b) for b in (entry.get("bullets") or [])]
        replace_items = []
        add_items = []
        used_replaces: set[int] = set()
        for bullet in payload.bullets:
            replaces = bullet.replaces_bullet_index
            if replaces is None:
                add_items.append(bullet)
                continue
            if not 0 <= replaces < len(existing):
                raise ValueError(
                    f"replaces_bullet_index {replaces} is out of range for the "
                    "matched entry — re-run adapt"
                )
            if replaces in used_replaces:
                raise ValueError(f"two bullets replace the same index {replaces}")
            # The index alone can silently point at a bullet the user never
            # reviewed if the entry was edited between adapt and apply.
            if _norm(bullet.replaces_text) != _norm(existing[replaces]):
                raise ValueError(
                    "the matched entry changed since the proposal — re-run adapt"
                )
            used_replaces.add(replaces)
            replace_items.append(bullet)

        final = existing[:]
        for bullet in replace_items:
            final[bullet.replaces_bullet_index] = bullet.text
        norms = {_norm(t) for t in final}
        kept_adds = []
        for bullet in add_items:
            if _norm(bullet.text) in norms:
                skipped_ids.extend(bullet.source_point_ids)
                continue
            norms.add(_norm(bullet.text))
            kept_adds.append(bullet)
            final.append(bullet.text)

        if not replace_items and not kept_adds:
            raise ValueError(
                "nothing to apply — every bullet already exists on the entry"
            )
        if section == "education":
            # AddBullet can't target education; recompose in one ReplaceEntry.
            value = copy.deepcopy(entry)
            value["bullets"] = final
            ops.append(
                {"kind": "replace_entry", "section": "education", "index": idx, "value": value}
            )
        else:
            for bullet in replace_items:
                ops.append(
                    {
                        "kind": "replace_bullet",
                        "section": section,
                        "index": idx,
                        "bullet_index": bullet.replaces_bullet_index,
                        "value": bullet.text,
                    }
                )
            for bullet in kept_adds:
                ops.append(
                    {"kind": "add_bullet", "section": section, "index": idx, "text": bullet.text}
                )
        applied = replace_items + kept_adds
        created_entry = False

    working = apply_edits(working, _validated_ops(ops))

    port_log_rows: list[dict] = []
    ported_ids: list = []
    for bullet in applied:
        for pid in bullet.source_point_ids:
            port_log_rows.append(
                {
                    "entity_id": entity.id,
                    "point_id": pid,
                    "section": section,
                    "ported_text": bullet.text,
                    "source_text": points_by_id[pid].text,
                }
            )
            if pid not in ported_ids:
                ported_ids.append(pid)
    skipped_unique = [
        pid for pid in dict.fromkeys(skipped_ids) if pid not in ported_ids
    ]

    target = _persist_port(
        session,
        target,
        working,
        port_log_rows,
        summary=f"Adapted {len(ported_ids)} point(s) from Career KB",
    )
    report = KBPortReport(
        items=[
            KBPortItemReport(
                entity_id=entity.id,
                ported_point_ids=ported_ids,
                skipped_duplicate_point_ids=skipped_unique,
                created_entry=created_entry,
            )
        ]
    )
    return target, report
