"""Profile areas to build: frequent skill gaps tiered by what would actually fix them.

Three parts:
1. A gap_frequency-style sweep of the best-scoring base row per job
   (_best_base_gap_rows — a weak secondary base must not manufacture demand for
   skills the resume you would really send already covers), keyed on the
   engine's canonical/alias-folded skill form (raw jd_skill strings count
   "AWS" and "Amazon Web Services" separately; this module folds them).
2. A read-only Career KB join classifying each frequent skill into ``status``:
   - ``missing``  — no KB evidence anywhere,
   - ``in_kb``    — evidence exists (profile skills, approved point text or
                    tags, entity tech, certification titles) but nothing
                    matching was ever ported,
   - ``ported``   — a matching point (or ported certification) has a KBPortLog
                    row, yet the skill still gaps on some base.
3. A ``tier`` per row, because "areas to build" must not list skills the user
   demonstrably has:
   - ``build``    — nothing on the resume AND nothing in the KB, gapping as a
                    missing skill → learn/acquire it. The only real one.
   - ``surface``  — the material exists somewhere (the KB has it, it is already
                    ported to another resume, or it sits on this one but
                    mis-placed or stale) → port, adapt, or corroborate.
                    Document work, not learning.
   - ``wording``  — the skill ONLY ever gaps as a hygiene mirror_wording gap,
                    meaning the resume already matches it lexically at FULL
                    keyword credit (match_credit >= 1.0 — gap_analysis.py sets
                    score_effect on exactly that test). Mirroring the literal
                    JD token then buys recruiter Boolean search and zero
                    composite, so ranking it as a standing deficit charts work
                    with no score to gain. Its adds_credit sibling sits below
                    full credit, where the literal token earns real keyword
                    credit, and stays effective.
                    The discriminator is score movement, NOT auto-resolution:
                    kb_resolver._wording_auto_resolution keys on
                    diagnostic.fix_hint and never reads score_effect, so
                    tailoring auto-mirrors BOTH kinds (and only when the
                    mirror_wording switch is on — quick_tailor.py).

Hygiene occurrences are kept out of n_jobs, avg_potential_points,
requirement_level, category and the ranking entirely, and counted under
wording_jobs instead; one skill can carry both kinds. gap_frequency skips the
very same occurrences through the shared _is_hygiene_wording predicate, so
Overview's "what you keep lacking" teaser can never contradict this panel's
wording footnote.

Matching reuses the ATS engine's primitives (normalize_term and the guarded
SkillMatcher.match_in_text prose search) so Analytics agrees with scoring.
"""
from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.career_kb import KBEntity, KBPoint, KBPortLog, KBProfile
from app.services.ats import SkillMatcher, load_config, normalize_term
from app.services.explore_gaps import (
    _best_base_gap_rows,
    _is_hygiene_wording,
    _most_common,
    _skill_gap_occurrences,
)


def build_areas(
    db: Session,
    role_category: str | None = None,
    level: str | None = None,
    employment_type: str | None = None,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    matcher = SkillMatcher(load_config())

    effective_job_ids: dict[str, set] = defaultdict(set)
    hygiene_job_ids: dict[str, set] = defaultdict(set)
    effective_points: dict[str, list[float]] = defaultdict(list)
    effective_categories: dict[str, Counter] = defaultdict(Counter)
    req_levels: dict[str, Counter] = defaultdict(Counter)
    raw_names: dict[str, Counter] = defaultdict(Counter)

    for job_id, gaps in _best_base_gap_rows(
        db, role_category, level, employment_type
    ):
        for cat_key, gap, raw in _skill_gap_occurrences(gaps):
            canonical = (gap.get("diagnostic") or {}).get(
                "canonical"
            ) or normalize_term(raw)
            key = matcher.canonical(canonical)
            # Raw names feed the display label, so both occurrence kinds vote:
            # a wording-only skill still needs something to call itself.
            raw_names[key][raw] += 1
            if _is_hygiene_wording(cat_key, gap):
                hygiene_job_ids[key].add(job_id)
                continue
            effective_job_ids[key].add(job_id)
            effective_points[key].append(float(gap.get("potential_points") or 0.0))
            if cat_key is not None:
                effective_categories[key][cat_key] += 1
            if gap.get("requirement_level"):
                req_levels[key][gap["requirement_level"]] += 1

    top = sorted(
        effective_job_ids.items(),
        key=lambda kv: (
            -len(kv[1]),
            -(sum(effective_points[kv[0]]) / len(effective_points[kv[0]])),
            kv[0],
        ),
    )[:limit]
    # Wording-only skills rank after every effective one no matter how often they
    # recur — they are a footnote, not competitors for the panel's slots. So they
    # spend only the budget effective gaps left over: limit means limit, and a
    # zero-score-movement row can never displace a real gap that got truncated.
    wording_only = sorted(
        (
            (key, ids)
            for key, ids in hygiene_job_ids.items()
            if not effective_job_ids.get(key)
        ),
        key=lambda kv: (-len(kv[1]), kv[0]),
    )[: max(0, limit - len(top))]

    emitted = top + wording_only
    if not emitted:
        return []

    evidence = _kb_evidence(db, matcher, [key for key, _ in emitted])

    rows = []
    for key, _ in emitted:
        found = evidence[key]
        eff_jobs = effective_job_ids.get(key) or set()
        eff_points = effective_points.get(key) or []
        hygiene_jobs = hygiene_job_ids.get(key) or set()
        category = _most_common(effective_categories.get(key) or Counter())
        if not eff_jobs:
            tier = "wording"
        elif found["status"] == "missing" and category == "missing_skills":
            tier = "build"
        else:
            tier = "surface"
        rows.append(
            {
                "skill": _most_common(raw_names.get(key) or Counter()) or key,
                "n_jobs": len(eff_jobs),
                "avg_potential_points": round(sum(eff_points) / len(eff_points), 1)
                if eff_points
                else 0.0,
                "requirement_level": _most_common(req_levels.get(key) or Counter()),
                "status": found["status"],
                "kb_points": found["kb_points"],
                "kb_entities": found["kb_entities"],
                "tier": tier,
                "category": category,
                "wording_jobs": len(hygiene_jobs),
            }
        )
    return rows


def _kb_evidence(
    db: Session, matcher: SkillMatcher, keys: list[str]
) -> dict[str, dict[str, Any]]:
    """Classify each canonical skill key against KB evidence in one pass."""
    profile = db.get(KBProfile, 1)
    profile_items = {
        normalize_term(str(item))
        for group in (profile.skills_json if profile else None) or []
        for item in group.get("items") or []
        if str(item).strip()
    }

    points = db.scalars(
        select(KBPoint).where(KBPoint.state == "approved")
    ).all()
    entities = {
        entity.id: entity for entity in db.scalars(select(KBEntity)).all()
    }
    ported_point_ids = set(
        db.scalars(
            select(KBPortLog.point_id).where(KBPortLog.point_id.is_not(None)).distinct()
        ).all()
    )
    # Certification & extra-section ports without points log point_id=None;
    # their provenance lives on entity_id, so collect those separately.
    ported_entity_only_ids = set(
        db.scalars(
            select(KBPortLog.entity_id)
            .where(KBPortLog.point_id.is_(None))
            .distinct()
        ).all()
    )

    point_texts = [(point, normalize_term(point.text or "")) for point in points]
    entity_extra: list[tuple[Any, str]] = []
    for entity in entities.values():
        tech = str((entity.detail_json or {}).get("tech") or "")
        text = (
            f"{entity.title or ''} {entity.org or ''}"
            if (entity.kind in ("certification", "extra"))
            else tech
        )
        if text.strip():
            entity_extra.append((entity, normalize_term(text)))

    results: dict[str, dict[str, Any]] = {}
    for key in keys:
        forms = [form for form in matcher.all_forms(key) if form]
        # Prose search goes through the matcher's guarded API: short alias
        # forms like "tf" are unsearchable in free text (TF-IDF would count as
        # TensorFlow evidence otherwise) — the same rule the scoring engine
        # applies, so Analytics agrees with scoring.
        matched_points = [
            point
            for point, text in point_texts
            if text and matcher.match_in_text(key, text) is not None
        ]
        matched_tags = [
            point
            for point in points
            if point not in matched_points
            and any(
                normalize_term(str(tag)) in forms for tag in (point.tags_json or [])
            )
        ]
        matched_points.extend(matched_tags)
        matched_entities = [
            entity
            for entity, text in entity_extra
            if matcher.match_in_text(key, text) is not None
        ]
        in_profile = any(form in profile_items for form in forms)

        entity_titles: list[str] = []
        for point in matched_points:
            entity = entities.get(point.entity_id)
            if entity and entity.title not in entity_titles:
                entity_titles.append(entity.title)
        for entity in matched_entities:
            if entity.title not in entity_titles:
                entity_titles.append(entity.title)

        has_evidence = bool(matched_points or matched_entities or in_profile)
        if not has_evidence:
            status = "missing"
        elif any(point.id in ported_point_ids for point in matched_points) or any(
            entity.kind in ("certification", "extra") and entity.id in ported_entity_only_ids
            for entity in matched_entities
        ):
            status = "ported"
        else:
            status = "in_kb"
        results[key] = {
            "status": status,
            "kb_points": len(matched_points),
            "kb_entities": entity_titles[:3],
        }
    return results
