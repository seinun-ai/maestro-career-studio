"""Pure structural base→tailored resume diff with provenance attribution.

LLM-free. Walks two ResumeData-shaped dicts by index (same-schema documents,
index-stable tailor ops) and labels each hunk kb_auto | user | llm by joining
against session resolutions.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

_KB_AUTO_SOURCES = frozenset({"kb_auto", "library_auto", "kb_profile", "wording_auto"})

_ENTRY_SECTIONS = ("experience", "projects", "education")


def _hunk(
    kind: str,
    section: str,
    index: int | None,
    before: Any,
    after: Any,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "section": section,
        "index": index,
        "before": before,
        "after": after,
        "provenance": None,
    }


def _diff_contact(base: dict, customized: dict, hunks: list[dict]) -> None:
    b, a = base.get("contact") or {}, customized.get("contact") or {}
    if b != a:
        hunks.append(_hunk("contact_changed", "contact", None, b, a))


def _diff_summary(base: dict, customized: dict, hunks: list[dict]) -> None:
    b, a = base.get("summary"), customized.get("summary")
    if b != a:
        hunks.append(_hunk("summary_changed", "summary", None, b, a))


def _diff_skills(base: dict, customized: dict, hunks: list[dict]) -> None:
    old = list(base.get("skills") or [])
    new = list(customized.get("skills") or [])
    n = max(len(old), len(new))
    for i in range(n):
        if i >= len(old):
            hunks.append(_hunk("skills_group_changed", "skills", i, None, new[i]))
        elif i >= len(new):
            hunks.append(_hunk("skills_group_changed", "skills", i, old[i], None))
        elif old[i] != new[i]:
            hunks.append(_hunk("skills_group_changed", "skills", i, old[i], new[i]))


def _diff_bullets(
    section: str,
    entry_index: int,
    old_bullets: list,
    new_bullets: list,
    hunks: list[dict],
) -> None:
    old = list(old_bullets or [])
    new = list(new_bullets or [])
    n = max(len(old), len(new))
    for i in range(n):
        if i >= len(old):
            hunks.append(_hunk("bullet_added", section, entry_index, None, new[i]))
        elif i >= len(new):
            hunks.append(_hunk("bullet_removed", section, entry_index, old[i], None))
        elif old[i] != new[i]:
            hunks.append(_hunk("bullet_edited", section, entry_index, old[i], new[i]))


def _entry_enabled(entry: dict | None) -> bool:
    if entry is None:
        return True
    return entry.get("enabled", True) is not False


def _diff_entries(section: str, base: dict, customized: dict, hunks: list[dict]) -> None:
    old = list(base.get(section) or [])
    new = list(customized.get(section) or [])
    n = max(len(old), len(new))
    for i in range(n):
        if i >= len(old):
            hunks.append(_hunk("entry_added", section, i, None, new[i]))
            continue
        if i >= len(new):
            hunks.append(_hunk("entry_removed", section, i, old[i], None))
            continue
        prev, curr = old[i], new[i]
        old_on, new_on = _entry_enabled(prev), _entry_enabled(curr)
        if old_on != new_on:
            kind = "entry_enabled" if new_on else "entry_disabled"
            hunks.append(_hunk(kind, section, i, prev, curr))
        # Field changes other than enabled/bullets still matter for entry_added-like
        # identity; bullet diffs are the content surface the studio reviews.
        _diff_bullets(
            section,
            i,
            prev.get("bullets") if isinstance(prev, dict) else [],
            curr.get("bullets") if isinstance(curr, dict) else [],
            hunks,
        )


def _diff_certifications(base: dict, customized: dict, hunks: list[dict]) -> None:
    old = list(base.get("certifications") or [])
    new = list(customized.get("certifications") or [])
    if old == new:
        return
    # Treat certifications as a flat bullet-like list under section "certifications".
    n = max(len(old), len(new))
    for i in range(n):
        if i >= len(old):
            hunks.append(_hunk("bullet_added", "certifications", i, None, new[i]))
        elif i >= len(new):
            hunks.append(_hunk("bullet_removed", "certifications", i, old[i], None))
        elif old[i] != new[i]:
            hunks.append(_hunk("bullet_edited", "certifications", i, old[i], new[i]))


def _diff_extra_sections(base: dict, customized: dict, hunks: list[dict]) -> None:
    old = list(base.get("extra_sections") or [])
    new = list(customized.get("extra_sections") or [])
    old_by_key = {
        str(s.get("key", "")): (i, s) for i, s in enumerate(old) if isinstance(s, dict)
    }
    new_by_key = {
        str(s.get("key", "")): (i, s) for i, s in enumerate(new) if isinstance(s, dict)
    }
    for key, (i, s) in new_by_key.items():
        if key not in old_by_key:
            hunks.append(_hunk("extra_section_added", "extra_sections", i, None, s))
    for key, (i, s) in old_by_key.items():
        if key not in new_by_key:
            hunks.append(_hunk("extra_section_removed", "extra_sections", i, s, None))
    for key, (new_i, curr) in new_by_key.items():
        prev_pair = old_by_key.get(key)
        if prev_pair is None:
            continue
        _, prev = prev_pair
        if prev == curr:
            continue
        old_on, new_on = _entry_enabled(prev), _entry_enabled(curr)
        if old_on != new_on and {k: v for k, v in prev.items() if k != "enabled"} == {
            k: v for k, v in curr.items() if k != "enabled"
        }:
            kind = "extra_section_enabled" if new_on else "extra_section_disabled"
            hunks.append(_hunk(kind, "extra_sections", new_i, prev, curr))
        else:
            hunks.append(_hunk("extra_section_changed", "extra_sections", new_i, prev, curr))


def diff_resume(base: dict[str, Any], customized: dict[str, Any]) -> list[dict[str, Any]]:
    """Structural walk of base data_json vs application customized_json.

    Returns hunks shaped ``{kind, section, index, before, after, provenance}``.
    ``provenance`` is left ``None`` until :func:`attribute` fills it.
    """
    hunks: list[dict[str, Any]] = []
    _diff_contact(base, customized, hunks)
    _diff_summary(base, customized, hunks)
    _diff_skills(base, customized, hunks)
    for section in _ENTRY_SECTIONS:
        _diff_entries(section, base, customized, hunks)
    _diff_certifications(base, customized, hunks)
    _diff_extra_sections(base, customized, hunks)
    return hunks


def _collapse_provenance(source: Any) -> str:
    if source in _KB_AUTO_SOURCES:
        return "kb_auto"
    return "user"


def _resolution_wording(payload: dict[str, Any]) -> str:
    for key in ("text", "keyword", "wording", "point_text", "value"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _hunk_text_blob(hunk: dict[str, Any]) -> str:
    parts: list[str] = []
    for side in (hunk.get("before"), hunk.get("after")):
        if side is None:
            continue
        if isinstance(side, str):
            parts.append(side)
        elif isinstance(side, dict):
            # skills group / entry
            items = side.get("items")
            if isinstance(items, list):
                parts.extend(str(x) for x in items)
            bullets = side.get("bullets")
            if isinstance(bullets, list):
                parts.extend(str(x) for x in bullets)
            for k in ("name", "heading", "title", "text"):
                if side.get(k):
                    parts.append(str(side[k]))
        elif isinstance(side, list):
            parts.extend(str(x) for x in side)
        else:
            parts.append(str(side))
    return "\n".join(parts)


def _matches_resolution(hunk: dict[str, Any], resolution: dict[str, Any]) -> bool:
    action = resolution.get("action")
    payload = resolution.get("payload") or {}
    if not isinstance(payload, dict):
        return False
    section = payload.get("section")
    index = payload.get("index")
    if section is not None and hunk.get("section") != section:
        return False
    if index is not None and hunk.get("index") != index:
        return False

    wording = _resolution_wording(payload)

    if action == "enable_entry":
        return hunk.get("kind") in {"entry_enabled", "entry_disabled"}

    if action == "port_kb_point":
        if hunk.get("kind") not in {"bullet_added", "bullet_edited"}:
            return False
        if not wording:
            return True
        blob = _hunk_text_blob(hunk).casefold()
        return wording.casefold() in blob

    if action == "add_keyword":
        if hunk.get("kind") != "skills_group_changed":
            # add_keyword into experience/projects lands as a bullet edit/add
            if hunk.get("kind") not in {"bullet_added", "bullet_edited"}:
                return False
        if not wording:
            return True
        blob = _hunk_text_blob(hunk).casefold()
        return wording.casefold() in blob

    # Any other action that shares section+index is a soft match (user edits).
    if section is None and index is None:
        return False
    if wording:
        return wording.casefold() in _hunk_text_blob(hunk).casefold()
    return True


def attribute(
    hunks: list[dict[str, Any]],
    resolutions: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Join hunks against resolution payloads; default unattributable → ``llm``.

    Provenance collapses to three UI values:
    - resolution ``payload.provenance.source`` in {kb_auto, library_auto,
      kb_profile, wording_auto}
      → ``"kb_auto"``
    - any other matched resolution → ``"user"``
    - no match → ``"llm"``
    """
    out: list[dict[str, Any]] = []
    res_list = list(resolutions or [])
    for hunk in hunks:
        labeled = deepcopy(hunk)
        matched: dict[str, Any] | None = None
        for resolution in res_list:
            if not isinstance(resolution, dict):
                continue
            if _matches_resolution(hunk, resolution):
                matched = resolution
                break
        if matched is None:
            labeled["provenance"] = "llm"
        else:
            payload = matched.get("payload") or {}
            provenance = payload.get("provenance") if isinstance(payload, dict) else None
            source = provenance.get("source") if isinstance(provenance, dict) else None
            if source is None:
                labeled["provenance"] = "user"
            else:
                labeled["provenance"] = _collapse_provenance(source)
        out.append(labeled)
    return out
