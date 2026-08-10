from dataclasses import dataclass, field
from typing import Any

from app.services.ats.matching import normalize_term

_LEVEL_RANK = {"required": 2, "preferred": 1, "mentioned": 0}


@dataclass(frozen=True)
class JdSkill:
    name: str
    canonical: str
    requirement_level: str  # required | preferred | mentioned
    category: str | None = None


@dataclass(frozen=True)
class JdProfile:
    title: str
    role_category: str | None
    years_experience_min: int | None
    years_experience_max: int | None
    skills: list[JdSkill] = field(default_factory=list)
    # JD-side text for the L6 semantic layer: responsibilities + qualifications,
    # falling back to skill names when both lists are empty.
    requirement_lines: list[str] = field(default_factory=list)


def _requirement_lines(extracted_json: dict[str, Any], skills: list[JdSkill]) -> list[str]:
    lines = [
        stripped
        for key in ("responsibilities", "qualifications")
        for raw in (extracted_json.get(key) or [])
        if raw is not None and (stripped := str(raw).strip())
    ]
    # fallback: skill names keep the semantic layer meaningful when a JD carries
    # no prose (skills are always present — normalize_jd rejects empty ones)
    return lines or [s.name for s in skills]


def normalize_jd(extracted_json: dict[str, Any]) -> JdProfile:
    raw_skills = extracted_json.get("skills") or []
    if not raw_skills:
        raise ValueError("Job has no extracted skills; ATS scoring needs extracted_json.skills")

    by_canonical: dict[str, JdSkill] = {}
    for raw in raw_skills:
        name = str(raw.get("skill_name") or "").strip()
        if not name:
            continue
        level = str(raw.get("requirement_level") or "mentioned").lower()
        if level not in _LEVEL_RANK:
            level = "mentioned"
        canonical = normalize_term(name)
        existing = by_canonical.get(canonical)
        if existing is None or _LEVEL_RANK[level] > _LEVEL_RANK[existing.requirement_level]:
            by_canonical[canonical] = JdSkill(
                name=name,
                canonical=canonical,
                requirement_level=level,
                category=raw.get("skill_category"),
            )

    skills = list(by_canonical.values())
    return JdProfile(
        title=str(extracted_json.get("title") or ""),
        role_category=extracted_json.get("role_category"),
        years_experience_min=extracted_json.get("years_experience_min"),
        years_experience_max=extracted_json.get("years_experience_max"),
        skills=skills,
        requirement_lines=_requirement_lines(extracted_json, skills),
    )
