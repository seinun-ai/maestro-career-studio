"""Every applicant fact the fill loop may write, keyed by slot.

Built from the CONSENT-GATED profile (`eeo_consent.disclosable_profile`) plus
the selected resume's employment blocks and skills. `value` is what code types
or Pick compares against (never sent to Jev during /map); `describe` is the
label-only text /map offers; `policy` is `autofill_slots.policy_for`. Codes
become the words a form shows ("stem_opt" → "F-1 STEM OPT extension").
"""

import re
from dataclasses import dataclass
from typing import Any

from app.services.autofill_slots import Policy, _as_text, policy_for

MAX_SLOTS = 240  # Jev Choice ceiling 255 incl. sentinels
MAX_EDUCATION = 4
MAX_EXPERIENCE = 8
MAX_CUSTOM = 30

_WORDS: dict[str, dict[str, str]] = {
    "work_auth.status": {
        "citizen": "U.S. citizen", "permanent_resident": "Permanent resident (green card holder)",
        "opt": "F-1 OPT", "stem_opt": "F-1 STEM OPT extension", "h1b": "H-1B visa", "tn": "TN visa",
        "other_visa": "Another visa", "not_authorized": "Not authorized to work",
    },
    "eeo.veteran_status": {"not_veteran": "I am not a protected veteran", "veteran": "I am a protected veteran",
                           "decline": "I don't wish to answer"},
    "eeo.disability_status": {"no": "No, I do not have a disability", "yes": "Yes, I have a disability",
                              "decline": "I do not want to answer"},
    "eeo.gender": {"male": "Male", "female": "Female", "non_binary": "Non-binary", "decline": "Decline to self-identify"},
    "eeo.hispanic_latino": {"yes": "Yes", "no": "No", "decline": "Decline to self-identify"},
}
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


@dataclass(frozen=True)
class Fact:
    slot: str
    value: str | tuple[str, ...]
    describe: str
    policy: Policy


def _describe(slot: str) -> str:
    return re.sub(r"\.(\d+)\.", lambda m: f" entry {int(m.group(1)) + 1}: ", slot).replace(".", ": ").replace("_", " ")


def ym(text: str | None) -> str | None:
    """"Aug 2021" / "August 2021" / "2021-08(-01)" / "08/2021" / "2021" → "2021-08" / "2021"."""
    s = (text or "").strip().lower()
    if m := re.fullmatch(r"(\d{4})-(\d{1,2})(?:-\d{1,2})?", s):
        return f"{m[1]}-{int(m[2]):02d}"
    if m := re.fullmatch(r"(\d{1,2})/(\d{4})", s):
        return f"{m[2]}-{int(m[1]):02d}"
    if m := re.fullmatch(r"([a-z]{3})[a-z]*\.?\s+(\d{4})", s):
        month = _MONTHS.get(m[1])
        return f"{m[2]}-{month:02d}" if month else None
    return s if re.fullmatch(r"\d{4}", s) else None


def _add(out: dict[str, Fact], slot: str, value: Any, describe: str | None = None) -> None:
    if isinstance(value, tuple):
        if value:
            out[slot] = Fact(slot, value, describe or _describe(slot), policy_for(slot))
        return
    words = _WORDS.get(re.sub(r"\.\d+\.", ".", slot), {})
    text = (words.get(value) if isinstance(value, str) else None) or _as_text(value)
    if text is not None:
        out[slot] = Fact(slot, text, describe or _describe(slot), policy_for(slot))


def build(profile: dict[str, Any], employment: list[dict[str, Any]], skills: list[str]) -> dict[str, Fact]:
    out: dict[str, Fact] = {}
    profile = profile or {}
    for section in ("personal", "work_auth", "eligibility", "eeo", "preferences"):
        values = profile.get(section)
        if isinstance(values, dict):
            for key, value in values.items():
                if section == "eeo" and key == "gender" and value == "self_describe":
                    value = values.get("gender_self_describe")
                if isinstance(value, list):
                    value = tuple(str(v).strip() for v in value if str(v).strip())
                _add(out, f"{section}.{key}", value)
    education = profile.get("education")
    education = [education] if isinstance(education, dict) else (education or [])
    for i, entry in enumerate([e for e in education if isinstance(e, dict)][:MAX_EDUCATION]):
        for key, value in entry.items():
            _add(out, f"education.{i}.{key}", value)
    for i, block in enumerate((employment or [])[:MAX_EXPERIENCE]):
        for key in ("employer", "title", "location", "description"):
            _add(out, f"experience.{i}.{key}", block.get(key) or None)
        _add(out, f"experience.{i}.start", ym(block.get("start_date")))
        if not block.get("current"):
            _add(out, f"experience.{i}.end", ym(block.get("end_date")))
        _add(out, f"experience.{i}.current", bool(block.get("current")))
    _add(out, "skills", tuple(s for s in (skills or []) if s), "applicant skills (a list)")
    for i, qa in enumerate((profile.get("custom") or [])[:MAX_CUSTOM]):
        if isinstance(qa, dict) and qa.get("question"):
            _add(out, f"custom.{i}", qa.get("answer"), f"saved answer to: {qa['question']}")
    return dict(list(out.items())[:MAX_SLOTS])
