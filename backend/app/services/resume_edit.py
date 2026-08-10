import logging
from copy import deepcopy
from typing import Any

from pydantic import TypeAdapter, ValidationError

from app.schemas.resume import (
    ContactInfo,
    EducationEntry,
    ExperienceEntry,
    ExtraSection,
    ProjectEntry,
    ResumeData,
)
from app.schemas.resume_edit import (
    AddBullet,
    AddEntry,
    AddExtraSection,
    AddSkillItem,
    MoveExtraSection,
    RemoveBullet,
    RemoveEntry,
    RemoveExtraSection,
    ReplaceBullet,
    ReplaceCertifications,
    ReplaceContact,
    ReplaceEntry,
    ReplaceExtraSection,
    ReplaceSkillsGroup,
    ReplaceSummary,
    ResumeEdit,
    ToggleEntry,
)

logger = logging.getLogger(__name__)

_SECTION_MODELS = {
    "experience": ExperienceEntry,
    "projects": ProjectEntry,
    "education": EducationEntry,
}

# Discriminated-union validator for a single custom section payload. Reused by
# the add/replace ops; produces a normalized dump so stored custom sections
# always match the Stage-A schema (slug key, exactly one content branch).
_EXTRA_SECTION_ADAPTER: TypeAdapter[ExtraSection] = TypeAdapter(ExtraSection)


def _validate_entry(section: str, value: dict) -> dict:
    try:
        return _SECTION_MODELS[section].model_validate(value).model_dump(mode="json")
    except ValidationError as e:
        raise ValueError(f"invalid {section} entry: {e}") from e


def _validate_extra_section(value: dict) -> dict:
    try:
        return _EXTRA_SECTION_ADAPTER.validate_python(value).model_dump(mode="json")
    except ValidationError as e:
        raise ValueError(f"invalid extra section: {e}") from e


def _extra_sections(resume: dict[str, Any]) -> list[dict[str, Any]]:
    sections = resume.get("extra_sections")
    if not isinstance(sections, list):
        return []
    return sections


def _find_extra_section(sections: list[dict[str, Any]], section_key: str) -> int:
    """Resolve a stored ExtraSection.key to its list index (case-insensitively).

    Missing key -> ValueError (clean 400); a duplicate key is impossible in a
    normalized resume but is treated as ambiguous defensively.
    """
    target = section_key.casefold()
    matches = [
        i
        for i, section in enumerate(sections)
        if isinstance(section, dict) and str(section.get("key", "")).casefold() == target
    ]
    if not matches:
        raise ValueError(f"no extra section with key {section_key!r}")
    if len(matches) > 1:
        raise ValueError(f"ambiguous extra section key {section_key!r}")
    return matches[0]


def _entries(resume: dict[str, Any], section: str) -> list[dict[str, Any]]:
    entries = resume.get(section)
    if not isinstance(entries, list):
        return []
    return entries


def _check_index(section: str, index: int, length: int) -> None:
    if index < 0 or index >= length:
        raise ValueError(f"{section} index {index} out of range")


def _entry_name(entry: dict[str, Any], section: str) -> str | None:
    if section == "experience":
        company = entry.get("company")
        role = entry.get("role")
        if company and role:
            return f"{company} / {role}"
        return company or role
    if section == "projects":
        name = entry.get("name")
        return str(name) if name else None
    if section == "education":
        institution = entry.get("institution")
        degree = entry.get("degree")
        if institution and degree:
            return f"{institution} / {degree}"
        return institution or degree
    return None


def _apply_replace_summary(resume: dict[str, Any], op: ReplaceSummary) -> dict[str, Any]:
    before = resume.get("summary")
    resume["summary"] = op.value
    return {"kind": "replace_summary", "before": before, "after": op.value}


def _apply_toggle_entry(resume: dict[str, Any], op: ToggleEntry) -> dict[str, Any]:
    entries = _entries(resume, op.section)
    _check_index(op.section, op.index, len(entries))
    entry = entries[op.index]
    if not isinstance(entry, dict):
        raise ValueError(f"{op.section} entry {op.index} is malformed")
    before = entry.get("enabled")
    entry["enabled"] = op.enabled
    return {
        "kind": "toggle_entry",
        "section": op.section,
        "index": op.index,
        "name": _entry_name(entry, op.section),
        "before": before,
        "after": op.enabled,
    }


def _apply_replace_bullet(resume: dict[str, Any], op: ReplaceBullet) -> dict[str, Any]:
    entries = _entries(resume, op.section)
    _check_index(op.section, op.index, len(entries))
    entry = entries[op.index]
    if not isinstance(entry, dict):
        raise ValueError(f"{op.section} entry {op.index} is malformed")
    bullets = entry.get("bullets")
    if not isinstance(bullets, list) or not (0 <= op.bullet_index < len(bullets)):
        raise ValueError(f"bullet_index {op.bullet_index} out of range")
    before = bullets[op.bullet_index]
    bullets[op.bullet_index] = op.value
    return {
        "kind": "replace_bullet",
        "section": op.section,
        "index": op.index,
        "name": _entry_name(entry, op.section),
        "bullet_index": op.bullet_index,
        "before": before,
        "after": op.value,
    }


def _apply_add_bullet(resume: dict[str, Any], op: AddBullet) -> dict[str, Any]:
    entries = _entries(resume, op.section)
    _check_index(op.section, op.index, len(entries))
    entry = entries[op.index]
    if not isinstance(entry, dict):
        raise ValueError(f"{op.section} entry {op.index} is malformed")
    bullets = entry.setdefault("bullets", [])
    if not isinstance(bullets, list):
        raise ValueError(f"{op.section} entry {op.index} bullets is malformed")
    bullets.append(op.text)
    return {
        "kind": "add_bullet",
        "section": op.section,
        "index": op.index,
        "name": _entry_name(entry, op.section),
        "bullet_index": len(bullets) - 1,
        "after": op.text,
    }


def _apply_replace_skills_group(resume: dict[str, Any], op: ReplaceSkillsGroup) -> dict[str, Any]:
    groups = _entries(resume, "skills")
    target = op.category.casefold()
    matches = [g for g in groups if str(g.get("category", "")).casefold() == target]
    if not matches:
        raise ValueError(f"No skills group matches category {op.category!r}")
    if len(matches) > 1:
        raise ValueError(f"Ambiguous skills group: {len(matches)} groups match {op.category!r}")
    existing_items = matches[0].get("items", [])
    new_norms = {str(i).casefold() for i in op.items}
    removed = [str(i) for i in existing_items if str(i).casefold() not in new_norms]
    if removed:
        logger.warning(
            "replace_skills_group on category %r removes items: %s", op.category, sorted(removed)
        )
    before = list(existing_items)
    matches[0]["items"] = list(op.items)
    return {
        "kind": "replace_skills_group",
        "category": matches[0].get("category"),
        "before": before,
        "after": list(op.items),
    }


def _apply_add_skill_item(resume: dict[str, Any], op: AddSkillItem) -> dict[str, Any]:
    groups = _entries(resume, "skills")
    target = op.category.casefold()
    matches = [g for g in groups if str(g.get("category", "")).casefold() == target]
    if matches:
        items = matches[0].setdefault("items", [])
        if op.item.casefold() not in {str(i).casefold() for i in items}:
            items.append(op.item)
        category = matches[0].get("category")
    else:
        groups.append({"category": op.category, "items": [op.item]})
        resume["skills"] = groups  # in case skills was missing/non-list
        category = op.category
    return {
        "kind": "add_skill_item",
        "category": category,
        "after": op.item,
    }


def _apply_add_entry(resume: dict[str, Any], op: AddEntry) -> dict[str, Any]:
    entries = resume.setdefault(op.section, [])
    if not isinstance(entries, list):
        raise ValueError(f"{op.section} is malformed")
    validated = _validate_entry(op.section, op.value)
    entries.append(validated)
    return {
        "kind": "add_entry",
        "section": op.section,
        "index": len(entries) - 1,
        "name": _entry_name(validated, op.section),
    }


def _apply_replace_entry(resume: dict[str, Any], op: ReplaceEntry) -> dict[str, Any]:
    entries = _entries(resume, op.section)
    _check_index(op.section, op.index, len(entries))
    before = entries[op.index]
    validated = _validate_entry(op.section, op.value)
    entries[op.index] = validated
    return {
        "kind": "replace_entry",
        "section": op.section,
        "index": op.index,
        "name": _entry_name(validated, op.section),
        "before": before,
        "after": validated,
    }


def _apply_remove_entry(resume: dict[str, Any], op: RemoveEntry) -> dict[str, Any]:
    entries = _entries(resume, op.section)
    _check_index(op.section, op.index, len(entries))
    removed = entries.pop(op.index)
    name = _entry_name(removed, op.section) if isinstance(removed, dict) else None
    return {
        "kind": "remove_entry",
        "section": op.section,
        "index": op.index,
        "name": name,
        "before": removed,
    }


def _apply_remove_bullet(resume: dict[str, Any], op: RemoveBullet) -> dict[str, Any]:
    entries = _entries(resume, op.section)
    _check_index(op.section, op.index, len(entries))
    entry = entries[op.index]
    if not isinstance(entry, dict):
        raise ValueError(f"{op.section} entry {op.index} is malformed")
    bullets = entry.get("bullets")
    if not isinstance(bullets, list) or not (0 <= op.bullet_index < len(bullets)):
        raise ValueError(f"bullet_index {op.bullet_index} out of range")
    before = bullets.pop(op.bullet_index)
    return {
        "kind": "remove_bullet",
        "section": op.section,
        "index": op.index,
        "name": _entry_name(entry, op.section),
        "bullet_index": op.bullet_index,
        "before": before,
    }


def _apply_replace_contact(resume: dict[str, Any], op: ReplaceContact) -> dict[str, Any]:
    before = resume.get("contact")
    try:
        resume["contact"] = ContactInfo.model_validate(op.value).model_dump(mode="json")
    except ValidationError as e:
        raise ValueError(f"invalid contact: {e}") from e
    return {"kind": "replace_contact", "before": before, "after": resume["contact"]}


def _apply_replace_certifications(resume: dict[str, Any], op: ReplaceCertifications) -> dict[str, Any]:
    before = list(resume.get("certifications") or [])
    resume["certifications"] = [c.strip() for c in op.items if c.strip()]
    return {
        "kind": "replace_certifications",
        "before": before,
        "after": resume["certifications"],
    }


def _apply_add_extra_section(resume: dict[str, Any], op: AddExtraSection) -> dict[str, Any]:
    sections = resume.setdefault("extra_sections", [])
    if not isinstance(sections, list):
        raise ValueError("extra_sections is malformed")
    # Uniqueness / reserved-key collisions are enforced by the final
    # ResumeData.model_validate in apply_edits (single source of truth).
    validated = _validate_extra_section(op.value)
    sections.append(validated)
    return {
        "kind": "add_extra_section",
        "section_key": validated.get("key"),
        "index": len(sections) - 1,
    }


def _apply_replace_extra_section(resume: dict[str, Any], op: ReplaceExtraSection) -> dict[str, Any]:
    sections = _extra_sections(resume)
    idx = _find_extra_section(sections, op.section_key)
    new_section = _validate_extra_section(op.value)
    if new_section["key"].casefold() != op.section_key.casefold():
        raise ValueError(
            f"replace_extra_section may not change the key: "
            f"{op.section_key!r} -> {new_section['key']!r}"
        )
    before = sections[idx]
    sections[idx] = new_section
    return {
        "kind": "replace_extra_section",
        "section_key": op.section_key,
        "index": idx,
        "before": before,
        "after": new_section,
    }


def _apply_remove_extra_section(resume: dict[str, Any], op: RemoveExtraSection) -> dict[str, Any]:
    sections = _extra_sections(resume)
    idx = _find_extra_section(sections, op.section_key)
    before = sections.pop(idx)
    return {
        "kind": "remove_extra_section",
        "section_key": op.section_key,
        "index": idx,
        "before": before,
    }


def _apply_move_extra_section(resume: dict[str, Any], op: MoveExtraSection) -> dict[str, Any]:
    sections = _extra_sections(resume)
    idx = _find_extra_section(sections, op.section_key)
    # Valid targets are the permutation positions 0..len-1 of the section.
    if op.to_index < 0 or op.to_index >= len(sections):
        raise ValueError(f"extra section index {op.to_index} out of range")
    section = sections.pop(idx)
    sections.insert(op.to_index, section)
    return {
        "kind": "move_extra_section",
        "section_key": op.section_key,
        "index": idx,
        "to_index": op.to_index,
    }


_OP_HANDLERS: dict[type, Any] = {
    ReplaceSummary: _apply_replace_summary,
    ToggleEntry: _apply_toggle_entry,
    ReplaceBullet: _apply_replace_bullet,
    AddBullet: _apply_add_bullet,
    ReplaceSkillsGroup: _apply_replace_skills_group,
    AddSkillItem: _apply_add_skill_item,
    AddEntry: _apply_add_entry,
    ReplaceEntry: _apply_replace_entry,
    RemoveEntry: _apply_remove_entry,
    RemoveBullet: _apply_remove_bullet,
    ReplaceContact: _apply_replace_contact,
    ReplaceCertifications: _apply_replace_certifications,
    AddExtraSection: _apply_add_extra_section,
    ReplaceExtraSection: _apply_replace_extra_section,
    RemoveExtraSection: _apply_remove_extra_section,
    MoveExtraSection: _apply_move_extra_section,
}


def _apply_op(resume: dict[str, Any], op: ResumeEdit) -> dict[str, Any]:
    handler = _OP_HANDLERS.get(type(op))
    if handler is None:
        raise ValueError(f"Unsupported edit op: {op!r}")  # defensive; discriminator guards this
    return handler(resume, op)


def apply_edits(
    base: dict[str, Any],
    ops: list[ResumeEdit],
    *,
    applied: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Apply typed edit ops onto a deep copy of `base`, validate, return the new dict.

    Out-of-range indices and missing/ambiguous skills categories raise ValueError
    (callers map that to HTTP 400). The final dict is round-tripped through
    ResumeData.model_validate so an invalid result never reaches storage.

    When ``applied`` is provided, each successful op appends an echo record
    (kind, section/index/name, before/after as applicable) so callers can
    confirm which full-array entry was touched — including ``enabled: false``
    rows that PDF render omits.
    """
    result = deepcopy(base)
    for op in ops:
        record = _apply_op(result, op)
        if applied is not None:
            applied.append(record)
    ResumeData.model_validate(result)
    return result
