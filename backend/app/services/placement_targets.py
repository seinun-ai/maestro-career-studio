"""Placement Targets — the valid destinations on a resume for a gap resolution.

One module owns the contract three consumers share: enrichment coercion
(best-effort, scrubs LLM output), caller-resolution validation (strict, raises),
and the KB resolver's candidate gating. Keeping the rules here prevents the
wrappers from accepting different target shapes — the "placement validation
twins" invariant (SYSTEM.md §6).

The targets dict deliberately stays a plain dict: the frontend's
``buildPlacementTargets`` hand-mirrors this shape (skips disabled entries but
keeps each survivor's ORIGINAL array index), and the two must agree on what a
valid destination is.
"""
from typing import Any

from app.services.resume_projects import extra_entry_live, extra_section_live

PLACEMENT_SECTIONS = ("skills", "experience", "projects", "extra")
# Literal fallback bucket the frontend offers when no existing category fits an
# unverified skill — always a valid skills placement even if the resume has no
# category by this name yet.
ADDITIONAL_SKILLS = "Additional Skills"


def build_targets(resume_json: dict[str, Any]) -> dict[str, Any]:
    """The valid placement destinations, mirroring the frontend's targets: the
    real skills-category names, the FULL-ARRAY indices of ENABLED experience /
    project entries, and enabled custom sections keyed by their stable key.

    The frontend ``buildPlacementTargets`` skips disabled entries but keeps each
    survivor's ORIGINAL array index (``forEach((entry, index) => ...)``), so a
    valid target is a full-array index whose entry is enabled — NOT a position in
    a densely renumbered enabled-only list. Validating against a plain enabled
    count wrongly rejects a valid later entry when an earlier one is disabled."""
    skills_categories = {
        group["category"]
        for group in resume_json.get("skills", [])
        if isinstance(group, dict) and group.get("category")
    }

    def _enabled_indices(section: str) -> set[int]:
        return {
            index
            for index, entry in enumerate(resume_json.get(section, []))
            if isinstance(entry, dict) and entry.get("enabled", True)
        }

    extra_sections: dict[str, dict[str, Any]] = {}
    # `or []` (not `.get(key, [])`): an explicit ``"extra_sections": null`` must
    # read as empty, matching the ATS indexer — the bare default only covers a
    # missing key, so a null value would otherwise raise TypeError (finding F#13).
    # extra_section_live / extra_entry_live are the SAME liveness predicate the
    # indexer uses, so the placement-target view and the ATS-evidence view agree
    # on which custom content is live (enabled omitted/None -> live).
    for section in resume_json.get("extra_sections") or []:
        if not extra_section_live(section) or not isinstance(section.get("key"), str):
            continue
        section_key = section["key"]
        if section.get("type") == "entries":
            extra_sections[section_key] = {
                "type": "entries",
                # As for core entries, retain original array indices while
                # excluding disabled custom entries.
                "indices": {
                    index
                    for index, entry in enumerate(section.get("entries") or [])
                    if extra_entry_live(entry)
                },
            }
        elif section.get("type") == "bullets":
            # A flat-bullets section has no entry index. Its stable section key
            # is also the index_or_category sentinel used by the frontend chip.
            extra_sections[section_key] = {"type": "bullets"}

    return {
        "skills_categories": skills_categories,
        "experience_indices": _enabled_indices("experience"),
        "projects_indices": _enabled_indices("projects"),
        "extra_sections": extra_sections,
    }


def canonicalize(
    placement: Any, resume_targets: dict[str, Any], *, missing_skill: bool
) -> dict[str, Any]:
    """Return a canonical placement or raise ``ValueError``.

    This is the single placement contract shared by best-effort enrichment
    coercion and strict caller-resolution validation. Keeping the rules here
    prevents the two public wrappers from accepting different target shapes.
    """
    if not isinstance(placement, dict):
        raise ValueError("placement target must be an object")
    section = placement.get("section")
    if section not in PLACEMENT_SECTIONS:
        raise ValueError(
            "invalid section (expected one of skills, experience, projects, extra)"
        )
    target = placement.get("index_or_category")

    # Honesty invariant: an unverified (absent) skill may only land in the
    # skills list. A custom section is evidence-bearing in phase 2, so it must
    # be guarded exactly like experience and projects.
    if missing_skill and section != "skills":
        raise ValueError("unverified skill additions must target the skills section")

    if section == "skills":
        if not isinstance(target, str):
            raise ValueError("names an unknown skills category")
        categories = {c.lower() for c in resume_targets.get("skills_categories", set())}
        if target.lower() not in categories and target != ADDITIONAL_SKILLS:
            raise ValueError("names an unknown skills category")
        return {"section": section, "index_or_category": target}

    if section in ("experience", "projects"):
        indices = resume_targets.get(
            "experience_indices" if section == "experience" else "projects_indices", set()
        )
        # bool is an int subclass; a True/False "index" is malformed, not 0/1
        if isinstance(target, bool) or not isinstance(target, int) or target not in indices:
            raise ValueError(f"is not an enabled {section} entry")
        return {"section": section, "index_or_category": target}

    section_key = placement.get("section_key")
    if not isinstance(section_key, str):
        raise ValueError("extra placement must name a section_key")
    extra_section = resume_targets.get("extra_sections", {}).get(section_key)
    if extra_section is None:
        raise ValueError("names an unknown or disabled extra section")
    if extra_section.get("type") == "entries":
        indices = extra_section.get("indices", set())
        if isinstance(target, bool) or not isinstance(target, int) or target not in indices:
            raise ValueError("is not an enabled extra-section entry")
    elif extra_section.get("type") == "bullets":
        if target != section_key:
            raise ValueError(
                "a bullets extra section must use its section_key as index_or_category"
            )
    else:  # defensive: build_targets only emits the two known variants
        raise ValueError("names an unsupported extra section type")
    return {
        "section": section,
        "section_key": section_key,
        "index_or_category": target,
    }


def coerce(
    placement: Any, resume_targets: dict[str, Any], fix_hint: str | None
) -> dict[str, Any] | None:
    """Validate the LLM's suggested placement against the real resume; any
    malformed or unreachable target → None (never persist an invalid target)."""
    try:
        return canonicalize(
            placement, resume_targets, missing_skill=fix_hint == "absent"
        )
    except ValueError:
        return None


def widen_for_enables(
    resume_targets: dict[str, Any] | None, pending_enables: set[tuple[str, int]]
) -> dict[str, Any] | None:
    """Port-target view that also admits entries a projected enable will turn on."""
    if resume_targets is None or not pending_enables:
        return resume_targets
    widened = {
        **resume_targets,
        "experience_indices": set(resume_targets["experience_indices"]),
        "projects_indices": set(resume_targets["projects_indices"]),
    }
    for section, index in pending_enables:
        widened[f"{section}_indices"].add(index)
    return widened
