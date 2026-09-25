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
# Exact-policy slots are knockout and protected answers: their describe is
# written out in the words a form asks with, so /map tells "sponsorship now"
# from "sponsorship in the future" by meaning, not by a slot path. Value-free.
_DESCRIBES: dict[str, str] = {
    "work_auth.status": "current work-authorization / visa status",
    "work_auth.authorized_now": "legally authorized to work in the country now (yes/no)",
    "work_auth.sponsorship_now": "needs employer visa sponsorship now (yes/no)",
    "work_auth.sponsorship_future": "will need visa sponsorship in the future (yes/no)",
    "work_auth.authorization_expires_on": "date the current work authorization expires",
    "work_auth.countries_authorized": "countries the applicant is authorized to work in (a list)",
    "eligibility.over_18": "is 18 or older (yes/no)",
    "eligibility.previously_employed_here": "has worked for this company before (yes/no)",
    "eligibility.non_compete": "is bound by a non-compete or similar agreement (yes/no)",
    "eeo.gender": "gender (voluntary self-identification)",
    "eeo.gender_self_describe": "gender in the applicant's own words (voluntary self-identification)",
    "eeo.race_ethnicity": "race or ethnicity (voluntary self-identification, a list)",
    "eeo.hispanic_latino": "is Hispanic or Latino (voluntary self-identification)",
    "eeo.veteran_status": "protected veteran status (voluntary self-identification)",
    "eeo.disability_status": "disability status (voluntary self-identification)",
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
    if slot in _DESCRIBES:
        return _DESCRIBES[slot]
    return re.sub(r"\.(\d+)\.", lambda m: f" entry {int(m.group(1)) + 1}: ", slot).replace(".", ": ").replace("_", " ")


def _month(year: str, month: int) -> str | None:
    return f"{year}-{month:02d}" if 1 <= month <= 12 else None


def ym(text: str | None) -> str | None:
    """"Aug 2021" / "August 2021" / "2021-08(-01)" / "08/2021" / "2021" → "2021-08" / "2021"."""
    s = (text or "").strip().lower()
    if m := re.fullmatch(r"(\d{4})-(\d{1,2})(?:-\d{1,2})?", s):
        return _month(m[1], int(m[2]))
    if m := re.fullmatch(r"(\d{1,2})/(\d{4})", s):
        return _month(m[2], int(m[1]))
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


def _profile_sections(out: dict[str, Fact], profile: dict[str, Any]) -> None:
    for section in ("personal", "work_auth", "eligibility", "eeo", "preferences"):
        values = profile.get(section)
        if not isinstance(values, dict):
            continue
        for key, value in values.items():
            if section == "eeo" and key == "gender" and value == "self_describe":
                value = values.get("gender_self_describe")
            if isinstance(value, list):
                value = tuple(str(v).strip() for v in value if str(v).strip())
            _add(out, f"{section}.{key}", value)


def _education(out: dict[str, Fact], education: Any) -> None:
    """Every entry, most recent first (a legacy profile holds one object)."""
    education = [education] if isinstance(education, dict) else education
    entries = [e for e in education if isinstance(e, dict)] if isinstance(education, list) else []
    for i, entry in enumerate(entries[:MAX_EDUCATION]):
        for key, value in entry.items():
            _add(out, f"education.{i}.{key}", value)


def _experience(out: dict[str, Fact], employment: list[dict[str, Any]]) -> None:
    """Every job; dates as YYYY-MM, and a current job has no end."""
    for i, block in enumerate(employment[:MAX_EXPERIENCE]):
        for key in ("employer", "title", "location", "description"):
            _add(out, f"experience.{i}.{key}", block.get(key) or None)
        _add(out, f"experience.{i}.start", ym(block.get("start_date")))
        if not block.get("current"):
            _add(out, f"experience.{i}.end", ym(block.get("end_date")))
        _add(out, f"experience.{i}.current", bool(block.get("current")))


def _custom(out: dict[str, Fact], custom: Any) -> None:
    """Saved answers, each described by its own question."""
    for i, qa in enumerate((custom if isinstance(custom, list) else [])[:MAX_CUSTOM]):
        if isinstance(qa, dict) and qa.get("question"):
            _add(out, f"custom.{i}", qa.get("answer"), f"saved answer to: {qa['question']}")


def build(profile: dict[str, Any], employment: list[dict[str, Any]], skills: list[str]) -> dict[str, Fact]:
    out: dict[str, Fact] = {}
    profile = profile or {}
    _profile_sections(out, profile)
    _education(out, profile.get("education"))
    _experience(out, employment or [])
    _add(out, "skills", tuple(s for s in (skills or []) if s), "applicant skills (a list)")
    _custom(out, profile.get("custom"))
    return dict(list(out.items())[:MAX_SLOTS])
