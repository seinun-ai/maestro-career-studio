"""The resume feeds a fill reads: employment blocks and the flat skills list.

Both read the RESUME, not the autofill profile. The profile holds the answers
that are the same on every application (name, address, work authorization);
employment and skills are the answers that are tailored per application, and
taking them from anywhere else would let the extension send an employer
something the resume beside it does not say. Shared by GET /api/autofill/context
and the fill loop's fact catalog (/map, /pick), so the two cannot disagree.
"""

import re
from typing import Any

_CURRENT_TOKENS = {"present", "current", "now"}


def clean_line(bullet: str) -> str:
    # Strip inline ** bold and backtick spans BEFORE trimming leading bullet
    # markers (the lstrip below would otherwise eat a leading "**"). __ is left
    # intact so dunder identifiers survive (mirrors qa._plain_text, fix B7).
    cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", bullet, flags=re.DOTALL).replace("`", "")
    return cleaned.strip().lstrip("-*•").strip()


def employment_blocks(resume_json: dict[str, Any]) -> list[dict[str, Any]]:
    blocks = []
    for entry in resume_json.get("experience", []):
        if not isinstance(entry, dict) or not entry.get("enabled", True):
            continue
        end = (entry.get("end_date") or "").strip()
        current = not end or end.lower() in _CURRENT_TOKENS
        blocks.append(
            {
                "employer": entry.get("company") or "",
                "title": entry.get("role") or "",
                # Workday renders a Location box in every work-experience block
                # and it was the block's most-observed unfilled field. The
                # resume model has always carried it; only this payload dropped
                # it, so the extension's rule had nothing to write.
                "location": entry.get("location") or "",
                "start_date": entry.get("start_date") or "",
                "end_date": None if current else end,
                "current": current,
                # Sentence-per-line plain text: no bullet markers, no separators,
                # no title/company prefixes — pasted verbatim into Description
                # textareas by the extension.
                "description": "\n".join(
                    cleaned
                    for bullet in entry.get("bullets") or []
                    if isinstance(bullet, str) and (cleaned := clean_line(bullet))
                ),
            }
        )
    return blocks


def resume_skills(resume_json: dict[str, Any]) -> list[str]:
    """Every skill on the resume, flat, in resume order.

    The stored shape is a list of `{category, items}` groups — the resume
    renders them grouped, an ATS skills picker takes them one at a time — so the
    grouping is dropped here rather than in the extension, which has no reason
    to know the resume's section model.

    Order is the resume's own, and it is load-bearing: the extension writes only
    the first N (a master resume carries 75 skills and no application wants all
    of them), so the first group is the one that survives the cap. That is the
    same order the reader of the resume sees first.

    Deliberately NOT capped here. The extension has to report how many it
    skipped, and it can only count that against the true total — a server-side
    cap would make "10 of 14" out of a resume that actually holds 75.

    De-duplicated case-insensitively, first spelling wins: "Python" listed under
    both Languages and ML would otherwise be typed into the form twice.
    """
    skills: list[str] = []
    seen: set[str] = set()
    for group in resume_json.get("skills", []):
        if not isinstance(group, dict):
            continue
        for item in group.get("items") or []:
            if not isinstance(item, str) or not (cleaned := item.strip()):
                continue
            if (key := cleaned.casefold()) in seen:
                continue
            seen.add(key)
            skills.append(cleaned)
    return skills
