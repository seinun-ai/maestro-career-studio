"""The Jev fill path's slot catalog and substitution policy.

A SLOT is one answered leaf of the autofill profile ("education.discipline").
Jev maps a form field to a slot from its label alone; code reads the value, so
the slot question never carries one. The POLICY says how far a picked option may
drift from that value before we refuse to write it:

- exact: legal and protected answers — a near miss is a false statement.
- flag:  facts about the applicant — a near miss only with the user told.
- any:   preferences — the best available option is the answer.
"""

from typing import Any, Literal

Policy = Literal["any", "flag", "exact"]

FREE_TEXT = "free_text"
NO_SLOT = "none"

_EXACT_SECTIONS = frozenset({"work_auth", "eligibility", "eeo"})
_FLAG_SECTIONS = frozenset({"education", "personal"})


def policy_for(slot: str | None) -> Policy:
    if slot is None:
        return "flag"
    section = slot.split(".", 1)[0]
    if section in _EXACT_SECTIONS:
        return "exact"
    if section in _FLAG_SECTIONS:
        return "flag"
    return "any"


def _as_text(value: Any) -> str | None:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        joined = ", ".join(str(item).strip() for item in value if str(item).strip())
        return joined or None
    return None


def _section_values(section: str, values: Any) -> dict[str, Any] | None:
    """A section's leaves. Education is a list, most recent first (§13
    `autofill-education-shape`; a legacy profile holds one object): a form asks
    about the latest degree, so that entry is the slot. Other lists (`custom`
    Q&A pairs) are not slots — the fast model's prompt carries them."""
    if section == "education" and isinstance(values, list):
        return values[0] if values and isinstance(values[0], dict) else None
    return values if isinstance(values, dict) else None


def flatten(profile: dict[str, Any]) -> dict[str, str]:
    """slot → value text, for every answered leaf of every section."""
    out: dict[str, str] = {}
    for section, values in (profile or {}).items():
        leaves = _section_values(section, values)
        if leaves is None:
            continue
        for key, value in leaves.items():
            text = _as_text(value)
            if text is not None:
                out[f"{section}.{key}"] = text
    return out


def slot_criteria(slots: dict[str, str]) -> dict[str, str]:
    """The Choice criteria for "which slot does this field ask for" — names, no values."""
    criteria = {slot: slot.replace(".", ": ").replace("_", " ") for slot in slots}
    criteria[FREE_TEXT] = (
        "A question that needs a written answer in the applicant's own words, "
        "such as why this company or describe a project"
    )
    criteria[NO_SLOT] = "None of the listed applicant facts answers this field"
    return criteria
