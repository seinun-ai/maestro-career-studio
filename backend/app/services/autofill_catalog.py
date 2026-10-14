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
absent when what it is derived from is. `with_agreement` adds Yes to the
application's own terms and consent boxes, only while the standing agreement
permission (`consent_forms`) is served on.
"""

import re
from dataclasses import dataclass, field, replace
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
    # One Yes/No question (owner, 2026-10-14). The profile reader maps the old values (autofill_profile).
    "eeo.veteran_status": {"no": "No, I am not a veteran", "yes": "Yes, I am a veteran",
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
    # The wording most US forms use; the profile asks now and later apart.
    "derived.sponsorship_now_or_future": ("will need visa sponsorship now or in the future (yes/no; from the "
                                          "applicant's now and later answers)"),
    "eeo.gender": "gender (voluntary self-identification)",
    "eeo.gender_self_describe": "gender in the applicant's own words (voluntary self-identification)",
    "eeo.race_ethnicity": "race or ethnicity (voluntary self-identification, a list)",
    "eeo.hispanic_latino": "is Hispanic or Latino (voluntary self-identification)",
    # A Yes/No answer's description is a proposition WITH a direction: polarity
    # (autofill_polarity) judges a question against it, and "disability status"
    # cannot say whether "are you free of any disability?" asks it or its opposite.
    # "Military Status:" (live Workday) asks it too. The answer is "Are you a
    # veteran?" (owner, 2026-10-14): a No settles every "not a protected veteran" and
    # "I am not a veteran" option, because a person who is no veteran is no protected
    # one; a Yes alone does not (it never says which protected class, if any), so a
    # classification question with a Yes is asked (autofill_pick._veteran_claims).
    # No negation word in it: a description that denies is read as the fact being false.
    "eeo.veteran_status": ("is a veteran (voluntary self-identification; a No also settles every option that "
                           "denies being a veteran or a protected veteran, and a military self-identification "
                           "question whose options are protected-veteran classifications; a Yes alone never says "
                           "which protected class applies, and never answers a branch, a discharge, current "
                           "service or a relative's service)"),
    "eeo.disability_status": "has a disability (voluntary self-identification)",
    # A form asks for it as "salary requirements" or "compensation" as often
    # as "desired salary": one fact, described in each wording.
    "preferences.desired_salary": "desired salary, compensation or salary requirements (expected pay)",
    # iCIMS asked "Are you able to work on-site at our Lewisville, Texas
    # location?" and found no fact (live, 2026-10-01): a Yes to relocating is a
    # Yes to working at the job's site. Not remote work, travel or a shift.
    "preferences.willing_to_relocate": ("willing to relocate for the job, and so able to work on-site at the job's "
                                        "location (yes/no; never remote work, travel, a commute, a shift or "
                                        "where the applicant lives now)"),
    # The SOURCE. A follow-up box asking for a referrer's name took it (live
    # iCIMS, 2026-10-01): a name is not a source.
    "preferences.how_heard": ("how the applicant heard about the job: the source, such as a job board or a "
                              "website (never a referrer's or employee's name, a recruiter, or a reason)"),
    # Said with the boxes beside them that they never answer: offered as
    # "personal: phone" / "personal: address", /map sent the phone number to
    # "Phone Extension" and line 1 to "Address Line 2" (live Workday, 2026-09-27).
    "personal.phone": ("the applicant's full phone number (the whole number; never a phone extension, a fax "
                       "number, a country calling code or a phone type)"),
    "personal.address": ("the applicant's street address, line 1 (never a second address line, an apartment, "
                         "suite or unit, or a county)"),
    # Facts built here rather than read from the profile: one lookup, so the
    # evaluation describes them as production does.
    "derived.full_name": "your full legal name, for name and signature boxes",
    # A dialing-code picker ("Country dialing code", "+1 United States") asks for the country, not the number.
    "derived.phone_country": ("the phone number's country and calling code (a dialing-code picker); "
                              "never the number itself"),
    # The profile holds a number, never what kind of phone it is: a device-type picker is answered Mobile
    # (autofill_pick reports it assumed).
    "derived.phone_type": "the kind of phone the number is (mobile, home or work)",
    "derived.today": "today's date, for a date the applicant signs or fills in today",
    "derived.earliest_start_date": "the earliest date you can start, as a calendar date",
    "derived.previously_employed_here": ("works, or has worked, for this company (from the work history: "
                                         "currently or previously)"),
    # Owner rules (2026-09-30): a background-check authorization is a consent
    # the agreement permission covers; optional opt-ins belong to the separate
    # low-stakes setting, which this fact must not widen.
    "derived.agrees_to_terms": ("agrees to the application's own terms and conditions, privacy notice, "
                                "certification, acknowledgement and background-check authorization statements, "
                                "and a box that signs the form electronically (\"Signature\": checking it equals "
                                "a handwritten signature) "
                                "(yes/no; never an optional opt-in to texts, marketing, job alerts or a talent "
                                "community, never a question about the applicant's willingness or "
                                "circumstances, and never a question about criminal history, convictions or "
                                "charges, or anything a background check might find)"),
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


# The calling code and display name of the countries a profile's Country holds, by the names it is
# written with (casefolded, punctuation dropped). A country this table does not know derives nothing.
_CALLING: dict[str, tuple[str, str]] = {}
for _code, _name, *_aliases in (
        ("1", "United States", "us", "usa", "u s", "u s a", "united states of america", "america"),
        ("1", "Canada", "ca"), ("44", "United Kingdom", "uk", "gb", "great britain", "england"),
        ("91", "India", "in"), ("61", "Australia", "au"), ("49", "Germany", "de"), ("33", "France", "fr"),
        ("34", "Spain", "es"), ("39", "Italy", "it"), ("31", "Netherlands", "nl", "the netherlands"),
        ("353", "Ireland", "ie"), ("41", "Switzerland", "ch"), ("46", "Sweden", "se"), ("47", "Norway", "no"),
        ("45", "Denmark", "dk"), ("358", "Finland", "fi"), ("48", "Poland", "pl"), ("351", "Portugal", "pt"),
        ("32", "Belgium", "be"), ("43", "Austria", "at"), ("52", "Mexico", "mx"), ("55", "Brazil", "br"),
        ("54", "Argentina", "ar"), ("57", "Colombia", "co"), ("56", "Chile", "cl"),
        ("86", "China", "cn"), ("81", "Japan", "jp"), ("82", "South Korea", "kr", "korea"),
        ("65", "Singapore", "sg"), ("852", "Hong Kong", "hk"), ("886", "Taiwan", "tw"),
        ("66", "Thailand", "th"), ("84", "Vietnam", "vn"), ("63", "Philippines", "ph"),
        ("62", "Indonesia", "id"), ("60", "Malaysia", "my"), ("92", "Pakistan", "pk"),
        ("880", "Bangladesh", "bd"), ("94", "Sri Lanka", "lk"), ("971", "United Arab Emirates", "uae", "ae"),
        ("966", "Saudi Arabia", "sa"), ("972", "Israel", "il"), ("90", "Turkey", "tr"),
        ("20", "Egypt", "eg"), ("27", "South Africa", "za"), ("234", "Nigeria", "ng"), ("254", "Kenya", "ke"),
        ("64", "New Zealand", "nz"), ("7", "Russia", "ru"), ("380", "Ukraine", "ua")):
    for _key in (_name, *_aliases):
        _CALLING[re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", _key.casefold())).strip()] = (_code, _name)


def phone_country(country: object) -> str | None:
    """"+1 United States" for a profile country written any usual way; None when it is unset or not in the table."""
    if not isinstance(country, str):
        return None
    found = _CALLING.get(re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", country.casefold())).strip())
    return f"+{found[0]} {found[1]}" if found else None


# A company name as one key: casefold, no suffix (Inc, LLC, Co., GmbH…; dots
# dropped first, so "L.L.C." is "llc"), no punctuation. One rule for placing
# page entries (autofill_sections) and for "worked here before".
_SUFFIX = re.compile(r"\b(inc|llc|llp|ltd|limited|corp|corporation|co|company|plc|gmbh)\b")


def name_key(text: str) -> str:
    """A leading "the" is not part of the name ("The Globex Depot" is "Globex Depot"),
    unless it is the whole name."""
    key = " ".join(_SUFFIX.sub(" ", re.sub(r"[^\w\s]", " ", text.casefold().replace(".", ""))).split())
    return key[4:] if key.startswith("the ") else key


# The URLs a Websites entry holds, one entry each, in this order: profile
# entry k of a Websites section is the k-th of them the profile holds
# (`websites`). LinkedIn is not here: it has its own box, never an entry.
WEBSITES = ("personal.website", "personal.github")
_URLISH = re.compile(r"(?:https?://)?(?:www\.)?([a-z0-9-]+(?:\.[a-z0-9-]+)+)(?::(\d+))?(/[^\s#]*)?(?:#\S*)?",
                     re.IGNORECASE)


def url_key(text: str) -> str:
    """A URL as one key: no scheme, leading `www.`, host case, default port,
    trailing slash or #fragment (the Companion's `asUrl`, shared/fill-loop.js).
    Anything else is its `name_key`."""
    m = _URLISH.fullmatch(text.strip())
    if m is None:
        return name_key(text)
    port = f":{m[2]}" if m[2] and m[2] not in ("80", "443") else ""
    # Only the host is case-folded: a path is case-sensitive ("/Ada" and "/ada"
    # may be two pages), as in `asUrl`. Text that is no URL takes `name_key`,
    # which folds case.
    return f"{m[1].lower()}{port}{(m[3] or '').rstrip('/')}"


def websites(facts: dict[str, "Fact"]) -> list[str]:
    """The Websites slots the profile holds, in entry order."""
    return [slot for slot in WEBSITES if slot in facts]


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
    # Only the derived worked-here No: the name key and currentness of EVERY job in the history, so a
    # question that names an employer can be checked against all of it (`named_employer_fact`). Never
    # sent anywhere, compared or shown.
    employers: tuple[tuple[str, bool], ...] = field(default=(), compare=False, repr=False)
    # The same fact: the name keys of the job's own company (`_company_keys`), so a question that names it
    # is known to (`question_names_company`).
    companies: tuple[str, ...] = field(default=(), compare=False, repr=False)


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


def _names(only: str, where: str | None) -> bool:
    """`only` as a whole word in `where`: "Crate" is not in "Datacrate", "Rome" is not
    in "Jerome, ID". Case-insensitive; this is the job's own text."""
    return bool(where) and re.search(rf"(?<![^\W_]){re.escape(only)}(?![^\W_])", where, re.IGNORECASE) is not None


def _for_this_job(qa: dict[str, Any], company: str | None, location: str | None) -> bool:
    """A saved answer whose question named a company or city (`only_for`, with
    `only_for_kind` "company" or "city", set when it was learned) holds only
    where that name is in this job's company, or its location, respectively: a
    company scope "Phoenix" is not met by a job located in Phoenix. A row with
    no kind (written by hand or before kinds) is met by either. With no job it
    holds nowhere: an answer about Acme must not look like a standing one at
    the next employer."""
    only = qa.get("only_for")
    if not isinstance(only, str) or not only.strip():
        return True
    only, kind = only.strip(), qa.get("only_for_kind")
    return ((kind != "city" and _names(only, company))
            or (kind != "company" and _names(only, location)))


def custom_for_job(custom: Any, company: str | None, location: str | None) -> list[Any]:
    """The saved answers that hold for this job, for the deterministic fill (the
    context feed); `_custom` makes the same call for the model's catalog."""
    return [qa for qa in (custom if isinstance(custom, list) else [])
            if not isinstance(qa, dict) or _for_this_job(qa, company, location)]


def _custom(out: dict[str, Fact], custom: Any, company: str | None, location: str | None) -> None:
    """Saved answers, each described by its own question. A row for another job
    is skipped but still counts, so the slots `custom.<i>` the rest keep do not
    move."""
    for i, qa in enumerate((custom if isinstance(custom, list) else [])[:MAX_CUSTOM]):
        if isinstance(qa, dict) and qa.get("question") and _for_this_job(qa, company, location):
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
    if _as_text(personal.get("phone")) is not None:
        out["derived.phone_type"] = make_fact("derived.phone_type", "Mobile")
    if (dialing := phone_country(personal.get("country"))) is not None:
        out["derived.phone_country"] = make_fact("derived.phone_country", dialing)
    work_auth = profile.get("work_auth") if isinstance(profile.get("work_auth"), dict) else {}
    status = work_auth.get("status")
    if isinstance(status, str) and status in _US_CITIZEN:
        out["derived.us_citizen"] = make_fact("derived.us_citizen", _US_CITIZEN[status])
    if (either := _now_or_future(work_auth)) is not None:
        out["derived.sponsorship_now_or_future"] = make_fact("derived.sponsorship_now_or_future", either)
    preferences = profile.get("preferences") if isinstance(profile.get("preferences"), dict) else {}
    start = preferences.get("earliest_start_date")
    if isinstance(start, str) and _IMMEDIATE.search(start):
        out["derived.earliest_start_date"] = make_fact("derived.earliest_start_date", today.isoformat())


def _now_or_future(work_auth: dict[str, Any]) -> str | None:
    """"Will you now or in the future require sponsorship?", from the two
    answers the profile holds: Yes when either is Yes, No only when both are
    No, nothing otherwise (one missing or unreadable, and no Yes)."""
    answers = []
    for key in ("sponsorship_now", "sponsorship_future"):
        value = work_auth.get(key)
        text = _as_text(value) if isinstance(value, bool) else value if isinstance(value, str) else None
        answers.append(yes_no_word(text, letters=True) if text else None)
    if "Yes" in answers:
        return "Yes"
    return "No" if answers == ["No", "No"] else None


# Where one string names several companies ("Acme, Globex, or Initech"): the commas, semicolons,
# slashes, colons and brackets, "&"-less, and "or" / "and" between them. A name that holds one of these
# itself ("Globex and Sons") still matches whole: the whole string is tried as one name before the parts.
_COMPANY_SEPARATORS = re.compile(r"\s*(?:[,;/:()]|\bor\b|\band\b)\s*", re.IGNORECASE)
# A part is a name once the preposition in front of it is gone ("or at Initech" is "at Initech").
_LEADING_WORD = re.compile(r"^(?:(?:at|for|with|by|of|the|any\s+of|including|include)\s+)+", re.IGNORECASE)
# A suffix's full stop ("Acme, Inc. or …") is not the end of a sentence.
_SUFFIX_STOP = re.compile(r"\b(inc|co|corp|ltd|llc|llp|plc|gmbh|bros|mfg)\.", re.IGNORECASE)


def _name_parts(text: str) -> list[str]:
    """The names a string holds: the whole of it, then its parts, each without its leading preposition."""
    return [part for raw in (text, *_COMPANY_SEPARATORS.split(text))
            if (part := _LEADING_WORD.sub("", raw.strip()).strip())]


def _company_keys(company: str | None) -> set[str]:
    """The name keys a company string stands for: the whole string and each part."""
    return {key for part in _name_parts(company or "") if (key := name_key(part))}


def _akin(a: str, b: str) -> bool:
    """One name is the other's start, whole words only ("acme", "acme web services"): a parent
    and a subsidiary, so a history that holds only one of them cannot say No for the other."""
    short, long = sorted((a, b), key=len)
    return long.startswith(f"{short} ")


WORKED_HERE_SLOT = "derived.previously_employed_here"
_VETERAN_WORD = re.compile(r"veteran", re.IGNORECASE)
# The classes a protected-veteran question names, with or without the word "protected" (VEVRAA's: disabled,
# recently separated, active duty wartime or campaign badge, Armed Forces service medal, and how forms word
# them). One pattern reads a question, its options and a chosen option (autofill_pick).
NAMES_PROTECTED_CLASS = re.compile(
    r"\bprotected\b|\bclassifications?\b|\bvevraa\b|\bcategor(?:y|ies)\s+of\b[^.?]*\bveterans?\b"
    r"|\bdisabled\s+veterans?\b|\b(?:recently\s+)?separated\s+veterans?\b|\bactive\s+duty\s+wartime\b"
    r"|\bcampaign\s+badge\b|\barmed\s+forces\s+service\s+medal\b"
    r"|\bcovered\s+veterans?\b|\bservice[-\s]connected\b|\bvietnam[-\s]era\b"
    r"|\bactive\s+duty\b.*\b(?:war|campaign)", re.IGNORECASE)


def names_veteran_off_slot(slot: str | None, question: str, fact: "Fact | None" = None) -> bool:
    """A question that names a veteran, under an answer that is not the veteran answer. Under another
    voluntary-disclosure answer ("Are you a disabled veteran?" under the disability answer) it claims
    veteran status the applicant never gave. Under any other saved Yes/No fact, a saved custom row
    included, it is refused when it names a veteran CLASS: a saved "Are you a veteran?" says nothing about
    which class applies. Only `eeo.veteran_status` answers such a question (autofill_pick guards that)."""
    if not slot or slot == "eeo.veteran_status" or not _VETERAN_WORD.search(question):
        return False
    return slot.startswith("eeo.") or bool(fact is not None and fact.yes_no and NAMES_PROTECTED_CLASS.search(question))


def _history_employers(out: dict[str, Fact], employment: list[dict[str, Any]] | None) -> list[tuple[str, bool]]:
    """Every employer of the history as (name key, whether that job is current): the WHOLE history
    when the raw jobs are at hand (the catalog itself lists only MAX_EXPERIENCE of them), else what
    the catalog lists."""
    if employment is not None:
        pairs = [(name_key(str(block.get("employer") or "")), bool(block.get("current"))) for block in employment]
    else:
        pairs = [(name_key(str(f.value)), getattr(out.get(f"experience.{m[1]}.current"), "value", None) == "Yes")
                 for slot, f in out.items() if (m := re.fullmatch(r"experience\.(\d+)\.employer", slot))]
    return [(key, current) for key, current in pairs if key]


def _worked_here(out: dict[str, Fact], company: str | None,
                 employment: list[dict[str, Any]] | None = None) -> None:
    """The job's company among the history's employers, for THIS application.

    A match is Yes — "Yes, currently" when a matching job is current, else "Yes, previously", so a
    pick between "Current Associate" and "Former Associate" has the words to choose by — and the
    company-agnostic standing answer goes. When the history lists jobs and none is at the company
    (or at any company the string names), it is "No": the resume says where the applicant worked
    (owner, 2026-10-14). The WHOLE history is compared, past the jobs the catalog lists. Nothing is
    derived with no jobs, with no company, when an employer is a parent or a subsidiary of the
    company by name ("Acme" and "Acme Web Services"), or when the standing answer says Yes (the
    user's own word outranks an inference): then the question is asked, as it was.

    The derived No is about THE JOB'S company only; a question that names other companies is read
    again at answer time (`named_employer_fact`), so the fact carries every employer's name key."""
    wanted = _company_keys(company)
    employers = _history_employers(out, employment)
    if not wanted or not employers:
        return
    matched = [current for key, current in employers if key in wanted]
    standing = out.get("eligibility.previously_employed_here")
    if matched:
        answer = "Yes, currently" if any(matched) else "Yes, previously"
    elif (any(_akin(key, name) for key, _ in employers for name in wanted)
          or (standing is not None and yes_no_word(str(standing.value)) == "Yes")):
        return
    else:
        answer = "No"
    out.pop("eligibility.previously_employed_here", None)
    fact = make_fact(WORKED_HERE_SLOT, answer)
    out[WORKED_HERE_SLOT] = replace(fact, employers=tuple(employers), companies=tuple(sorted(wanted)))


# A history "employer" that is not a company: matching a question against it would answer from a word
# ("Freelance", "Contractor"), never from a company the question names.
_NOT_AN_EMPLOYER = frozenset({
    "freelance", "freelancer", "self employed", "independent", "contract", "contractor", "consultant",
    "consulting", "various", "confidential", "stealth", "personal project"})
# The companies a question LISTS follow its "worked for / at / by / with" (or "employee of …"): up to the
# end of the clause, or a word that starts a qualifier ("before", "in the last five years", "as an
# employee"). A list may be introduced by a colon. Nothing else in the text is PARSED as a company, so
# "the field below" lists no "Field"; the safety net below catches what the parser does not read.
_MARKER = (r"(?:worked|work|working|employed|employee|employees|employment|associate|contractor|member|served)"
           r"\s+(?:for|at|by|with|of)")
_LISTED = re.compile(
    rf"\b{_MARKER}\s+(.+?)(?=\s+(?:before|previously|ever|currently|now|in\s+the|within|as\b|prior|since|"
    r"during|at\s+any|including|or\s+any|or\s+its|or\s+one)\b|[?!]|\.(?=\s|$)|$)", re.IGNORECASE)
# An option that is "Yes, <company>" names that company.
_YES_COMPANY = re.compile(r"^\W*yes\s*,\s*(.+)$", re.IGNORECASE)
# What the answer should be when a question names a company that is a parent or a subsidiary of an
# employer of the history, with no exact match, or mentions one in a way the parser cannot read: neither
# a No nor a Yes is true, so nobody answers.
ASK_THE_USER = "ask"
# A phrase that is not a proper name, however a question introduces it.
_NOT_A_NAME = re.compile(r"^(?:an?|any|our|the|federal|government|following)\b", re.IGNORECASE)


def _listed_phrases(question: str, options: tuple[str, ...]) -> list[str]:
    """The company phrases the question lists, and its options that read as a company."""
    phrases: list[str] = []
    for text in (question, *options):
        for m in _LISTED.finditer(_SUFFIX_STOP.sub(r"\1", text)):
            phrases += _name_parts(m[1])
    for text in options:
        phrases += _name_parts(m[1] if (m := _YES_COMPANY.match(text)) else text)
    return phrases


def _listed_company_keys(question: str, options: tuple[str, ...]) -> set[str]:
    """The name keys of the companies a question lists, and of its options that read as a company
    (the whole option, "Yes, <company>", or the company after "employee of / associate at …")."""
    return {key for phrase in _listed_phrases(question, options) if (key := name_key(phrase))} - _NOT_AN_EMPLOYER


def _is_capitalised(token: str) -> bool:
    """A capital letter anywhere ("Initech", "eInitech", "iTech"), or a digit first ("3M")."""
    return token[0].isdigit() or any(ch.isupper() for ch in token)


# Words a question or an option capitalises that begin or end no company name of their own: they must
# not make "Yes" ask against "Yes Ledger", or "Current Employee" against "Current Widgets".
_STOP_WORDS = frozenset({
    "yes", "no", "have", "has", "are", "were", "was", "did", "do", "please", "select", "current", "former",
    "employee", "previous", "if", "the", "our", "united", "general"})


def _capital_runs(texts: tuple[str, ...]) -> list[list[str]]:
    """Each stretch of consecutive capitalised words in `texts`."""
    runs: list[list[str]] = []
    for text in texts:
        run: list[str] = []
        for token in [*re.findall(r"\w+", text), ""]:
            if token and _is_capitalised(token):
                run.append(token)
                continue
            if run:
                runs.append(run)
            run = []
    return runs


def _capital_windows(texts: tuple[str, ...]) -> set[str]:
    """The name key of every stretch of consecutive capitalised words in `texts`, and of every part of one
    ("Previous Initech" holds "previous initech", "previous" and "initech"). What a question could be
    naming in a wording nothing parses: an EXACT mention can stand anywhere in a run."""
    return {name_key(" ".join(run[i:j])) for run in _capital_runs(texts)
            for i in range(len(run)) for j in range(i + 1, len(run) + 1)} - {""}


def _capital_remainders(texts: tuple[str, ...]) -> set[str]:
    """The name key of what is left of each capitalised run once its leading and trailing stop-words are
    gone ("Previous Initech Employee" is "initech"). Only that remainder can be a parent or a subsidiary
    of an employer, so a capitalised "Yes", "Current" or "United" starts no match."""
    keys: set[str] = set()
    for run in _capital_runs(texts):
        words = list(run)
        while words and words[0].casefold() in _STOP_WORDS:
            words.pop(0)
        while words and words[-1].casefold() in _STOP_WORDS:
            words.pop()
        if words:
            keys.add(name_key(" ".join(words)))
    return keys - {""}


def _capitalised_mention(key: str, texts: tuple[str, ...]) -> bool:
    """Whether the name `key` stands in `texts` as capitalised words: "Initech" is a mention of "initech",
    "the initech box" is not."""
    return key in _capital_windows(texts)


def _mentions_or_is_akin(employers: list[str], texts: tuple[str, ...]) -> bool:
    """Whether a capitalised stretch of `texts` is an employer's name (anywhere in a run), or, once its
    stop-words are dropped, the start of one or the name it starts ("Initech" and "Initech Software"):
    a mention the parser did not read, which can never be a No."""
    windows, remainders = _capital_windows(texts), _capital_remainders(texts)
    return any(key in windows or any(_akin(key, rest) for rest in remainders) for key in employers)


def question_names_company(facts: dict[str, Fact], question: str) -> bool:
    """Whether a question names a company: a capitalised proper name it lists ("worked for Globex"; not
    "a federal contractor", "any of the following", "our group"), or the job's own or an employer of the
    history as capitalised words. A written answer about a company the applicant has or has not worked for
    must come from the history, never from a model's prose."""
    if any(phrase[0].isupper() and not _NOT_A_NAME.match(phrase) and name_key(phrase)
           for phrase in _listed_phrases(question, ())):
        return True
    fact = facts.get(WORKED_HERE_SLOT)
    known = {key for key, _ in fact.employers} | set(fact.companies) if fact else set()
    known |= {name_key(str(f.value)) for slot, f in facts.items() if re.fullmatch(r"experience\.\d+\.employer", slot)}
    return any(key and key not in _NOT_AN_EMPLOYER and _capitalised_mention(key, (question,)) for key in known)


def named_employer_fact(facts: dict[str, Fact], question: str,
                        options: tuple[str, ...] | list[str] = ()) -> Fact | str | None:
    """What a worked-here question says once it is read again, when the derived answer is No. That No is
    about the job's company, and "Acme, Globex, or Initech?" also asks about Initech.

    A Fact (Yes): a company the question lists, or an option that is one, is an employer of the history
    (the WHOLE history). `ASK_THE_USER`: no exact match, but a listed company is a parent or a subsidiary
    of an employer ("Acme" and "Acme Web Services"), OR an employer of the history stands anywhere in the
    question or its options as capitalised words (the safety net: a wording the parser does not read can
    never become a No). None: nothing of the history is mentioned; the fact stands. A history "employer"
    that is no company (Freelance, Contractor …) never counts."""
    fact = facts.get(WORKED_HERE_SLOT)
    if fact is None:
        return None
    options = tuple(options)
    listed = _listed_company_keys(question, options)
    if fact.value != "No":
        # A derived Yes is about the job's company. A question that lists only a parent or a subsidiary of an
        # employer ("Acme Labs" for a history of "Acme") is about another company: neither is true.
        employers = [key for key, _ in fact.employers if key not in _NOT_AN_EMPLOYER]
        akin = any(_akin(key, name) and key != name for key in employers for name in listed)
        return ASK_THE_USER if akin and not set(fact.companies) & listed else None
    employers = [(key, current) for key, current in fact.employers if key not in _NOT_AN_EMPLOYER]
    named = [current for key, current in employers if key in listed]
    if named:
        return make_fact(WORKED_HERE_SLOT, "Yes, currently" if any(named) else "Yes, previously")
    generic = {name for name in listed if set(name.split()) <= _STOP_WORDS}   # "yes", "current employee"
    if (any(_akin(key, name) for key, _ in employers for name in listed - generic)
            or _mentions_or_is_akin([key for key, _ in employers], (question, *options))):
        return ASK_THE_USER
    return None


# The shapes of a question that asks whether the APPLICANT worked for the company: an ALLOWLIST, not a
# list of what to exclude. Each ends where the company must follow (`_company_follows`). "Have you ever
# worked for Acme?", "Were you employed by Acme?", "Did you work for Acme?", "Are you currently an employee of
# Acme?". Never "eligible to work for", "willing to", "want to work at", a household member, a competitor.
_YOU = r"\byou\s+(?:ever\s+|previously\s+)*"
_ROLE = r"(?:an?\s+)?(?:employee|intern|contractor)(?:\s+(?:or|and|/)\s+(?:an?\s+)?(?:employee|intern|contractor))?"
# "been DIRECTLY employed with", "been formally employed by": an adverb may stand before the verb.
_EMPLOYMENT = (rf"(?:been\s+)?(?:(?:directly|formally|officially|ever|previously)\s+)?"
               rf"(?:worked|employed|{_ROLE}|interned|contracted)\s+(?:(?:for|at|by|with|of)\s+)?")
_WORKED_SHAPES = tuple(re.compile(rx, re.IGNORECASE) for rx in (
    rf"\b(?:have|has)\s+{_YOU}{_EMPLOYMENT}",
    rf"\b(?:were|was)\s+{_YOU}(?:(?:directly|formally|officially)\s+)?(?:employed|{_ROLE})\s+(?:by|at|of|with)\s+",
    rf"\bdid\s+{_YOU}work\s+(?:for|at)\s+",
    rf"\bare\s+you\s+(?:currently\s+)?{_ROLE}\s+(?:of|at|for|with)\s+",
    r"\bare\s+you\s+currently\s+employed\s+(?:by|at|with)\s+",
))
# "a current or former employee", "an ex-Acme contractor": a company, when named, follows "of" or comes first.
_FORMER_ROLE = re.compile(
    r"\b(?:are|were|was)\s+you\b[^?.]*?\b(?:previous|former|current|ex-?)(?:\s+or\s+(?:previous|former|current))?[\s-]+"
    r"(?:(?P<co>[A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,3})\s+)?(?:employee|intern|contractor)\b"
    r"(?:\s+(?:or|and)\s+(?:employee|intern|contractor)\b)?(?:\s+(?:of|at|for|with)\s+(?P<rest>.*))?", re.IGNORECASE)
# The backstop behind the allowlist: what turns a question that names the company into another question: kin and
# friends, referrals, applications and interviews, convictions, work authorization and sponsorship, clearance and
# background checks, terminations, non-competes, where the applicant heard of the job, eligibility, willingness,
# other people's employment, competitors, customers and vendors.
_NOT_WORKED_HERE = re.compile(
    r"relat(?:ed|ive)|family|friend|spouse|anyone|someone|referr|applied|interview|convict|criminal|felony|authori|"
    r"sponsor|visa|clearance|background|terminat|non-?compete|hear\s+about|eligib|legal|able\s+to|willing|want|"
    r"h-?1b|petition|permit|household|member|compet|fired|disciplin|dismiss|customer|product|vendor|partner|"
    # the company listed beside a KIND of organisation is another question ("Acme or a federal contractor")
    r"government|federal|\bstate\b|\blocal\b|agency|public\s+sector|military|defen[cs]e|\bu\.s\b|united\s+states|"
    # a time window ("in the last 12 months") narrows the question past "ever worked here"; a plain "in the past" does not
    r"(?:last|past)\s+(?:\d+|few|several|two|three|five|ten|twelve)\s+(?:months?|years?)|within\b|"
    r"since\s+(?:19|20)\d\d|\b\d+\s+(?:months?|years?)\b",
    re.IGNORECASE)
# Where the company list ends in a clause.
_CLAUSE_END = re.compile(
    r"[?!;]|\.(?=\s|$)|\b(?:before|previously|ever|currently|now|in\s+the|within|since|during|at\s+any|as\s+an?|"
    r"prior|including)\b", re.IGNORECASE)


def _names_company(rest: str, companies: set[str]) -> bool:
    """Whether the text that follows a worked-here phrase STARTS with the job's company: "Acme, Globex or
    Initech" does; "a competitor of Acme" and "Acme products" do not (their key is not the company's)."""
    clause = _CLAUSE_END.split(_SUFFIX_STOP.sub(r"\1", rest), maxsplit=1)[0]
    return bool(companies & {key for part in _name_parts(clause) if (key := name_key(part))})


def asks_worked_here(facts: dict[str, Fact], question: str, options: tuple[str, ...] | list[str] = ()) -> bool:
    """Whether a question asks whether the applicant worked for the job's company, by one of the allowlisted
    shapes (`_WORKED_SHAPES`, a former/current employee) and none of the backstop's words (`_NOT_WORKED_HERE`)."""
    fact = facts.get(WORKED_HERE_SLOT)
    if fact is None or _NOT_WORKED_HERE.search(question) or any(_NOT_WORKED_HERE.search(o) for o in options):
        return False
    companies = set(fact.companies)
    for shape in _WORKED_SHAPES:
        if (m := shape.search(question)) and _names_company(question[m.end():], companies):
            return True
    if (m := _FORMER_ROLE.search(question)) and (
            _names_company(m["rest"], companies) if m["rest"] else
            _names_company(m["co"], companies) if m["co"] else True):
        return True
    return False


def lists_job_company(facts: dict[str, Fact], question: str, options: tuple[str, ...] | list[str] = ()) -> bool:
    """Whether a question (or its options) lists the company applied to: "Have you worked for Acme, Globex or
    Initech?" on an Acme job. A listed name, or the company as capitalised words anywhere in it. False with no
    worked-here fact (no company is known, or the history cannot say). Such a question is the worked-here
    answer's, whatever else it lists (`named_employer_fact` reads the rest). Needs the wording too
    (`asks_worked_here`, an allowlist of shapes): a question that only NAMES the company ("referred by an employee of Acme", "legally
    authorized to work for Acme") asks something else."""
    fact = facts.get(WORKED_HERE_SLOT)
    if fact is None or not fact.companies:
        return False
    options = tuple(options)
    return bool(set(fact.companies) & _listed_company_keys(question, options)
                or any(_capitalised_mention(key, (question, *options)) for key in fact.companies))


AGREES_TO_TERMS = "derived.agrees_to_terms"


def with_agreement(facts: dict[str, Fact], agrees: bool) -> dict[str, Fact]:
    """The catalog, plus Yes to the application's own terms and consent boxes
    when `agrees` — the standing agreement permission as SERVED (on, and not
    lapsed; owner, 2026-09-26: with it on, consent and terms ticks are the
    Companion's to fill). Without it there is no such fact at all."""
    if agrees is not True:
        return facts
    # Inside the cap: a full catalog gives up its last fact, never this one.
    return dict(list(facts.items())[:MAX_SLOTS - 1]) | {AGREES_TO_TERMS: make_fact(AGREES_TO_TERMS, "Yes")}


def build(profile: dict[str, Any], employment: list[dict[str, Any]], skills: list[str], *,
          today: date | None = None, company: str | None = None,
          location: str | None = None) -> dict[str, Fact]:
    """`today`: the clock derived dates read (tests inject it); the server's by
    default. `company`, `location`: the application's job's, when there is one."""
    out: dict[str, Fact] = {}
    profile = profile or {}
    _profile_sections(out, profile)
    _derived(out, profile, today or date.today())
    _education(out, profile.get("education"))
    _experience(out, employment or [])
    _worked_here(out, company, employment or [])
    _languages(out, profile.get("languages"))
    _add(out, "skills", tuple(s for s in (skills or []) if s))
    _custom(out, profile.get("custom"), company, location)
    return dict(list(out.items())[:MAX_SLOTS])
