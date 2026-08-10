"""Career-KB evidence snapshot, deterministic candidate gate, and auto planner."""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.career_kb import KBEntity, KBProfile
from app.services import placement_targets
from app.services.ats import SkillMatcher, load_config, normalize_term

logger = logging.getLogger(__name__)


def _profile_skills(profile: KBProfile | None) -> list[str]:
    skills: list[str] = []
    for group in (profile.skills_json if profile else None) or []:
        if isinstance(group, str):
            skills.append(group)
            continue
        if not isinstance(group, dict) or not isinstance(group.get("items"), list):
            continue
        skills.extend(str(item) for item in group["items"] if isinstance(item, str))
    return list(dict.fromkeys(skills))


def _tech_list(entity: KBEntity) -> list[str]:
    tech = (entity.detail_json or {}).get("tech")
    if isinstance(tech, list):
        return [str(item) for item in tech if isinstance(item, str)]
    if isinstance(tech, str) and tech.strip():
        return [tech.strip()]
    return []


def load_kb_snapshot(session: Session) -> dict[str, Any]:
    """Load the structured, ID-bearing KB subset used by gap enrichment."""
    profile = session.get(KBProfile, 1)
    entities = session.scalars(
        select(KBEntity)
        .where(KBEntity.status != "archived")
        .options(selectinload(KBEntity.points))
        .order_by(KBEntity.created_at, KBEntity.id)
    ).all()
    return {
        "profile_skills": _profile_skills(profile),
        "entities": [
            {
                "id": str(entity.id),
                "kind": entity.kind,
                "title": entity.title,
                "status": entity.status,
                "tech": _tech_list(entity),
                "points": [
                    {"id": str(point.id), "state": point.state, "text": point.text}
                    for point in entity.points
                    if point.state != "retired"
                ],
            }
            for entity in entities
        ],
    }


def _text_match(matcher: SkillMatcher, jd_skill: str, text: str) -> str | None:
    match = matcher.match_in_text(jd_skill, normalize_term(text))
    return match[0] if match else None


def evidence_match(jd_skill: str, texts: list[str]) -> str | None:
    """First lexical match_form of jd_skill against any text, else None.

    The shared literal-containment gate: candidate verification (here) and
    save-time resolution validation (tailoring_session) must agree on what
    counts as evidence, so both call this.
    """
    if not isinstance(jd_skill, str) or not jd_skill.strip():
        return None
    matcher = SkillMatcher(load_config())
    for text in texts:
        if isinstance(text, str) and text.strip():
            form = _text_match(matcher, jd_skill, text)
            if form:
                return form
    return None


def entry_evidence_texts(section: str, entry: dict[str, Any]) -> list[str]:
    """The text fields of a core entry that can evidence a skill.

    ProjectEntry.tech is a STRING in the schema (a comma list), not a list —
    iterating it would yield characters, silently never matching."""
    texts = [item for item in (entry.get("bullets") or []) if isinstance(item, str)]
    if section == "projects":
        tech = entry.get("tech")
        if isinstance(tech, str):
            texts.append(tech)
        elif isinstance(tech, list):
            texts.extend(item for item in tech if isinstance(item, str))
        if entry.get("name"):
            texts.append(str(entry["name"]))
    else:
        texts.extend(str(entry.get(key)) for key in ("role", "company") if entry.get(key))
    return texts


def _disabled_candidate(
    proposal: dict[str, Any], resume_json: dict[str, Any], jd_skill: str, matcher: SkillMatcher
) -> dict[str, Any] | None:
    section = proposal.get("section")
    index = proposal.get("index")
    if section not in ("experience", "projects") or isinstance(index, bool) or not isinstance(index, int):
        return None
    entries = resume_json.get(section)
    if not isinstance(entries, list) or index < 0 or index >= len(entries):
        return None
    entry = entries[index]
    if not isinstance(entry, dict) or entry.get("enabled") is not False:
        return None

    evidence = entry_evidence_texts(section, entry)
    matched = next(
        ((text, form) for text in evidence if (form := _text_match(matcher, jd_skill, text))),
        None,
    )
    snippet = matched[0] if matched else next((text for text in evidence if text.strip()), "")
    return {
        "kind": "disabled",
        "section": section,
        "index": index,
        "name": str(entry.get("name") or entry.get("role") or entry.get("company") or ""),
        "match_form": matched[1] if matched else "semantic",
        "auto": matched is not None,
        "evidence_snippet": snippet,
    }


def _kb_point_candidate(
    proposal: dict[str, Any],
    kb_snapshot: dict[str, Any],
    resume_json: dict[str, Any],
    jd_skill: str,
    matcher: SkillMatcher,
) -> dict[str, Any] | None:
    entity_id = proposal.get("entity_id")
    point_id = proposal.get("point_id")
    entity = next(
        (
            item
            for item in kb_snapshot.get("entities", [])
            if isinstance(item, dict) and item.get("id") == entity_id
        ),
        None,
    )
    if entity is None:
        return None
    point = next(
        (
            item
            for item in entity.get("points", [])
            if isinstance(item, dict) and item.get("id") == point_id
        ),
        None,
    )
    if point is None:
        logger.debug("dropping hallucinated KB point candidate: %r", proposal)
        return None

    text = point.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    match_form = _text_match(matcher, jd_skill, text)
    target = proposal.get("placement_target")
    canonical_target = None
    if isinstance(target, dict):
        try:
            canonical_target = placement_targets.canonicalize(
                target,
                placement_targets.build_targets(resume_json),
                missing_skill=False,
            )
        except ValueError:
            canonical_target = None
    return {
        "kind": "kb_point",
        "entity_id": entity_id,
        "point_id": point_id,
        "title": str(entity.get("title") or ""),
        "match_form": match_form or "semantic",
        "auto": bool(
            match_form and point.get("state") == "approved" and canonical_target is not None
        ),
        "placement_target": canonical_target,
        "evidence_snippet": text,
    }


def default_target_for_entity(
    entity: dict[str, Any], resume_json: dict[str, Any]
) -> dict[str, Any] | None:
    """Map a KB entity to an ENABLED base entry by case-insensitive title match,
    as a placement target for porting its points. None when nothing matches."""
    title = str(entity.get("title") or "").strip().casefold()
    if not title:
        return None
    for section in ("projects", "experience"):
        for index, entry in enumerate(resume_json.get(section) or []):
            if not isinstance(entry, dict) or entry.get("enabled", True) is False:
                continue
            name = str(
                entry.get("name") or entry.get("role") or entry.get("company") or ""
            ).strip().casefold()
            if name and name == title:
                return {"section": section, "index_or_category": index}
    return None


def verify_candidate(
    proposal: dict[str, Any],
    kb_snapshot: dict[str, Any],
    resume_json: dict[str, Any],
    jd_skill: str,
) -> dict[str, Any] | None:
    """Resolve and gate an enrichment proposal against real evidence."""
    if not isinstance(proposal, dict) or not isinstance(jd_skill, str):
        return None
    matcher = SkillMatcher(load_config())
    kind = proposal.get("kind")
    if kind == "disabled":
        return _disabled_candidate(proposal, resume_json, jd_skill, matcher)
    if kind == "kb_point":
        return _kb_point_candidate(proposal, kb_snapshot, resume_json, jd_skill, matcher)
    if kind == "profile":
        for skill in kb_snapshot.get("profile_skills", []):
            if not isinstance(skill, str):
                continue
            match_form = _text_match(matcher, jd_skill, skill)
            if match_form:
                return {"kind": "profile", "match_form": match_form, "auto": True}
        return None
    logger.debug("dropping unknown KB candidate kind: %r", proposal)
    return None


def _skills_category(gap: dict[str, Any], candidate_category: Any = None) -> str:
    """Which skills group an auto keyword lands in: an explicit candidate category,
    else the enrichment-suggested skills group, else the frontend's literal
    "Additional Skills" bucket (always a valid skills placement)."""
    suggested = (gap.get("enrichment") or {}).get("suggested_placement") or {}
    if isinstance(candidate_category, str) and candidate_category:
        return candidate_category
    if suggested.get("section") == "skills" and isinstance(
        suggested.get("index_or_category"), str
    ):
        return suggested["index_or_category"]
    return placement_targets.ADDITIONAL_SKILLS


def _wording_auto_resolution(gap: dict[str, Any]) -> dict[str, Any] | None:
    """mirror_wording only: the skill is already evidenced on the resume — the
    literal JD token is all that's missing, so adding that token to the skills
    list is deterministic, honest, and needs no KB. Deliberately NOT extended to
    dual_place (the token is already in skills; its fix is prose corroboration)
    or absent (the honesty rule's territory — user consent required)."""
    diagnostic = gap.get("diagnostic")
    hint = diagnostic.get("fix_hint") if isinstance(diagnostic, dict) else None
    if hint != "mirror_wording" or "add_keyword" not in (gap.get("actions") or []):
        return None
    wording = str(gap.get("jd_skill") or "").strip()
    if not wording:
        return None
    return {
        "gap_id": gap.get("gap_id"),
        "action": "add_keyword",
        "payload": {
            "placement_target": {
                "section": "skills",
                "index_or_category": _skills_category(gap),
            },
            "wording": wording,
            "provenance": {"source": "wording_auto"},
        },
    }


def auto_resolution_for_gap(gap: dict[str, Any]) -> dict[str, Any] | None:
    """Choose the strongest verified candidate and build its stored resolution;
    with no verified candidate, fall back to the deterministic exact-token add
    for mirror_wording gaps."""
    candidates = [
        candidate
        for candidate in gap.get("library_candidates", [])
        if isinstance(candidate, dict) and candidate.get("auto") is True
    ]
    rank = {"disabled": 0, "kb_point": 1, "profile": 2}
    candidate = min(candidates, key=lambda item: rank.get(item.get("kind"), 99), default=None)
    if candidate is None or candidate.get("kind") not in rank:
        return _wording_auto_resolution(gap)

    gap_id = gap.get("gap_id")
    if candidate["kind"] == "disabled":
        return {
            "gap_id": gap_id,
            "action": "enable_entry",
            "payload": {
                "section": candidate["section"],
                "index": candidate["index"],
                "name": candidate.get("name", ""),
                "provenance": {"source": "library_auto"},
            },
        }
    if candidate["kind"] == "kb_point":
        point_id = candidate["point_id"]
        entity_id = candidate["entity_id"]
        return {
            "gap_id": gap_id,
            "action": "port_kb_point",
            "payload": {
                "kb_point_id": point_id,
                "kb_entity_id": entity_id,
                "placement_target": candidate["placement_target"],
                "wording": candidate["evidence_snippet"],
                "provenance": {
                    "source": "kb_auto",
                    "kb_point_id": point_id,
                    "kb_entity_id": entity_id,
                },
            },
        }

    target = _skills_category(gap, candidate.get("category"))
    return {
        "gap_id": gap_id,
        "action": "add_keyword",
        "payload": {
            "placement_target": {"section": "skills", "index_or_category": target},
            "wording": str(gap.get("jd_skill") or ""),
            "provenance": {"source": "kb_profile"},
        },
    }
