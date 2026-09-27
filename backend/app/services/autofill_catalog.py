"""Every applicant fact the fill loop may write, keyed by slot.

Built from the CONSENT-GATED profile (`eeo_consent.disclosable_profile`) plus
the selected resume's employment blocks and skills. `value` is what code types
or Pick compares against (never sent to Jev during /map); `describe` is the
label-only text /map offers; `policy` is `autofill_slots.policy_for`. Codes
become the words a form shows ("stem_opt" → "F-1 STEM OPT extension").

DERIVED facts (`derived.*`) are computed here from the profile and the clock,
in their own section so /map's description says where each comes from: the
full legal name, today's date, US citizenship read off the work-authorization
status, an "immediately" availability as a date, and — for an application
whose company the work history lists — "previously employed here" as Yes,
in place of the standing answer, which is the same for every company. Each is
absent when what it is derived from is.
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, get_args

from app.schemas.autofill_profile import WorkAuthStatus
from app.services.autofill_profile import canonical_identity_from_profile
from app.services.autofill_slots import Policy, _as_text, policy_for

MAX_SLOTS = 240  # Jev Choice ceiling 255 incl. sentinels
MAX_EDUCATION = 4
MAX_EXPERIENCE = 8
MAX_LANGUAGES = 4
MAX_CUSTOM = 30

_WORDS: dict[str, dict[str, str]] = {
    "work_auth.status": {
        "citizen": "U.S. citizen", "permanent_resident": "Permanent resident (green card holder)",
        "opt": "F-1 OPT", "stem_opt": "F-1 STEM OPT extension", "h1b": "H-1B visa", "tn": "TN visa",
        "other_visa": "Another visa", "not_authorized": "Not authorized to work",
    },
    # Worded as a Yes or a No (`is_yes_no`), so a reversed question is read by its meaning.
    "eeo.veteran_status": {"not_veteran": "No, I am not a protected veteran", "veteran": "Yes, I am a protected veteran",
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
    "derived.us_citizen": "is a US citizen (yes/no; derived from the applicant's work authorization)",
    "eeo.gender": "gender (voluntary self-identification)",
    "eeo.gender_self_describe": "gender in the applicant's own words (voluntary self-identification)",
    "eeo.race_ethnicity": "race or ethnicity (voluntary self-identification, a list)",
    "eeo.hispanic_latino": "is Hispanic or Latino (voluntary self-identification)",
    # A Yes/No answer's description is a proposition WITH a direction: polarity
    # (autofill_polarity) judges a question against it, and "disability status"
    # cannot say whether "are you free of any disability?" asks it or its opposite.
    "eeo.veteran_status": "is a protected veteran (voluntary self-identification)",
    "eeo.disability_status": "has a disability (voluntary self-identification)",
    # A form asks for it as "salary requirements" or "compensation" as often
    # as "desired salary": one fact, described in each wording.
    "preferences.desired_salary": "desired salary, compensation or salary requirements (expected pay)",
    # Facts built here rather than read from the profile: one lookup, so the
    # evaluation describes them as production does.
    "derived.full_name": "your full legal name, for name and signature boxes",
    "derived.today": "today's date, for a date the applicant signs or fills in today",
    "derived.earliest_start_date": "the earliest date you can start, as a calendar date",
    "derived.previously_employed_here": ("works, or has worked, for this company (from the work history: "
                                         "currently or previously)"),
    "skills": "applicant skills (a list)",
}
# "Are you a US citizen?", from every status the profile can store: only a
# citizen is one; every other status (a green card, any visa, none) is a No.
# A status the profile cannot store derives nothing.
_US_CITIZEN = {status: "Yes" if status == "citizen" else "No" for status in get_args(WorkAuthStatus)}
# A stored availability that means "today" (the owner's profile says "Immedietly";
# "Immediatly", "Immediate start", "Available: now"): the WHOLE value is the
# word, so "2 weeks from now" or "not immediately" is not.
_IMMEDIATE = re.compile(r"^\W*(available\W*)?(immedi[ae]?t\w*(\s+start)?|asap|now|right\s+away)\W*$",
                        re.IGNORECASE)
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


# A company name as one key: casefold, no suffix (Inc, LLC, Co., GmbH…; dots
# dropped first, so "L.L.C." is "llc"), no punctuation. One rule for placing
# page entries (autofill_sections) and for "worked here before".
_SUFFIX = re.compile(r"\b(inc|llc|llp|ltd|limited|corp|corporation|co|company|plc|gmbh)\b")


def name_key(text: str) -> str:
    """A leading "the" is not part of the name ("The Home Depot" is "Home Depot"),
    unless it is the whole name."""
    key = " ".join(_SUFFIX.sub(" ", re.sub(r"[^\w\s]", " ", text.casefold().replace(".", ""))).split())
    return key[4:] if key.startswith("the ") else key


@dataclass(frozen=True)
class Fact:
    slot: str
    value: str | tuple[str, ...]
    describe: str
    policy: Policy
    # Whether the answer is itself a Yes or a No ("No", "No, I do not have a
    # disability", "Yes, previously"), however the profile stored it. Only such
    # a fact's question has a polarity (autofill_polarity: same or opposite,
    # code flips a plain Yes/No); a status, list or name is never turned into one.
    yes_no: bool = False


_YES_WORDS, _NO_WORDS = {"yes", "true"}, {"no", "false"}
_ANSWER_PREFIX = re.compile(r"(yes|no),\s*", re.IGNORECASE)


def yes_no_word(text: str, *, letters: bool = True) -> str:
    """A Yes or a No however it was typed — the panel's pause row stores
    "yes" as typed, and profiles are hand-edited: yes / true (and y) is "Yes",
    no / false (and n) is "No", a "yes, …" / "no, …" answer is capitalised.
    Anything else is left as it is. `letters`: whether a lone y / n counts
    (never in the personal section, where "Y" may be an initial)."""
    word = text.strip().lower()
    if word in _YES_WORDS or (letters and word == "y"):
        return "Yes"
    if word in _NO_WORDS or (letters and word == "n"):
        return "No"
    if m := _ANSWER_PREFIX.match(text.strip()):
        return f"{'Yes' if m[1].lower() == 'yes' else 'No'}, {text.strip()[m.end():]}"
    return text


def is_yes_no(value: object) -> bool:
    return isinstance(value, str) and (value in ("Yes", "No") or value.startswith(("Yes, ", "No, ")))


def describe_of(slot: str) -> str:
    """A slot's value-free description: the one lookup production and the
    evaluation both read (a saved answer is described by its own question)."""
    if slot in _DESCRIBES:
        return _DESCRIBES[slot]
    if (m := re.fullmatch(r"languages\.(\d+)\.(\w+)", slot)) and m[2] in _LANGUAGE_FACTS:
        return f"language entry {int(m[1]) + 1}: {_LANGUAGE_FACTS[m[2]]}"
    if m := re.fullmatch(r"experience\.(\d+)\.current", slot):
        return f"experience entry {int(m[1]) + 1}: is the applicant's current job (yes/no)"
    return re.sub(r"\.(\d+)\.", lambda m: f" entry {int(m.group(1)) + 1}: ", slot).replace(".", ": ").replace("_", " ")



def make_fact(slot: str, value: str | tuple[str, ...], describe: str | None = None) -> Fact:
    """A fact, described and marked Yes/No by the one rule (`describe_of`,
    `yes_no_word`, `is_yes_no`): the catalog and the evaluation both build here."""
    if isinstance(value, str):
        value = yes_no_word(value, letters=not slot.startswith("personal."))
    return Fact(slot, value, describe or describe_of(slot), policy_for(slot), is_yes_no(value))


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
            out[slot] = make_fact(slot, value, describe)
        return
    words = _WORDS.get(re.sub(r"\.\d+\.", ".", slot), {})
    text = (words.get(value) if isinstance(value, str) else None) or _as_text(value)
    if text is not None:
        out[slot] = make_fact(slot, text, describe)


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


# A language's levels in the words forms offer (Workday: Basic, Fluent,
# Intermediate), whatever their case; any other word is no fact.
_LEVELS = {"basic": "Basic", "intermediate": "Intermediate", "fluent": "Fluent"}
_YES_NO = {True: "Yes", False: "No", "yes": "Yes", "no": "No"}
_LANGUAGE_FACTS = {"language": "the language", "read": "reading level", "speak": "speaking level",
                   "write": "writing level", "native": "a native speaker of it (yes/no)",
                   "fluent": "fluent in it (yes/no)"}


def _language_answer(key: str, value: Any) -> str | None:
    word = value.strip().lower() if isinstance(value, str) else value
    if key == "language":
        return (value.strip() or None) if isinstance(value, str) else None
    if key in ("native", "fluent"):
        return _YES_NO.get(word) if isinstance(word, (str, bool)) else None
    return _LEVELS.get(word) if isinstance(word, str) else None


def _languages(out: dict[str, Fact], languages: Any) -> None:
    """One entry per NAMED language, most important first: its reading,
    speaking and writing levels, and "native" and "fluent" as two separate
    Yes/No answers. An absent or unreadable answer is no fact."""
    # Numbered over NAMED entries only (unlike `_education`): a language fact
    # means nothing without its language, and /sections places entries by it.
    named = [e for e in (languages if isinstance(languages, list) else [])
             if isinstance(e, dict) and _language_answer("language", e.get("language"))]
    for i, entry in enumerate(named[:MAX_LANGUAGES]):
        for key, what in _LANGUAGE_FACTS.items():
            if text := _language_answer(key, entry.get(key)):
                slot = f"languages.{i}.{key}"
                out[slot] = make_fact(slot, text)


def _custom(out: dict[str, Fact], custom: Any) -> None:
    """Saved answers, each described by its own question."""
    for i, qa in enumerate((custom if isinstance(custom, list) else [])[:MAX_CUSTOM]):
        if isinstance(qa, dict) and qa.get("question"):
            _add(out, f"custom.{i}", qa.get("answer"), f"saved answer to: {qa['question']}")


def _derived(out: dict[str, Fact], profile: dict[str, Any], today: date) -> None:
    """Facts computed from the profile and the clock, never invented: each is
    absent when what it is derived from is."""
    personal = profile.get("personal") if isinstance(profile.get("personal"), dict) else {}
    identity = canonical_identity_from_profile({"personal": personal})
    if identity["legal_first"] and identity["legal_last"]:
        out["derived.full_name"] = make_fact("derived.full_name",
                                             f"{identity['legal_first']} {identity['legal_last']}")
    out["derived.today"] = make_fact("derived.today", today.isoformat())
    work_auth = profile.get("work_auth") if isinstance(profile.get("work_auth"), dict) else {}
    status = work_auth.get("status")
    if isinstance(status, str) and status in _US_CITIZEN:
        out["derived.us_citizen"] = make_fact("derived.us_citizen", _US_CITIZEN[status])
    preferences = profile.get("preferences") if isinstance(profile.get("preferences"), dict) else {}
    start = preferences.get("earliest_start_date")
    if isinstance(start, str) and _IMMEDIATE.search(start):
        out["derived.earliest_start_date"] = make_fact("derived.earliest_start_date", today.isoformat())


def _worked_here(out: dict[str, Fact], company: str | None) -> None:
    """The job's company among the history's employers: Yes for THIS
    application — "Yes, currently" when a matching job is current, else "Yes,
    previously", so a pick between "Current Associate" and "Former Associate"
    has the words to choose by — and the company-agnostic standing answer
    goes. Only ever Yes: a company the resume does not list may still be a
    past employer."""
    key = name_key(company or "")
    matched = [m[1] for slot, f in out.items()
               if (m := re.fullmatch(r"experience\.(\d+)\.employer", slot)) and key and name_key(str(f.value)) == key]
    if not matched:
        return
    current = any(getattr(out.get(f"experience.{i}.current"), "value", None) == "Yes" for i in matched)
    out.pop("eligibility.previously_employed_here", None)
    out["derived.previously_employed_here"] = make_fact("derived.previously_employed_here",
                                                        "Yes, currently" if current else "Yes, previously")


def build(profile: dict[str, Any], employment: list[dict[str, Any]], skills: list[str], *,
          today: date | None = None, company: str | None = None) -> dict[str, Fact]:
    """`today`: the clock derived dates read (tests inject it); the server's by
    default. `company`: the application's job's company, when there is one."""
    out: dict[str, Fact] = {}
    profile = profile or {}
    _profile_sections(out, profile)
    _derived(out, profile, today or date.today())
    _education(out, profile.get("education"))
    _experience(out, employment or [])
    _worked_here(out, company)
    _languages(out, profile.get("languages"))
    _add(out, "skills", tuple(s for s in (skills or []) if s))
    _custom(out, profile.get("custom"))
    return dict(list(out.items())[:MAX_SLOTS])
