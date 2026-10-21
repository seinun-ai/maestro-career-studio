"""Knock-out pre-scan: stated JD hard requirements vs the user's own profile.

Compares what the posting states (work authorization, OPT policy, salary)
against what the autofill profile answers, BEFORE tailoring/filling effort is
spent. A stated on-site or hybrid work mode is compared against where you live
and `preferences.willing_to_relocate`. Read-and-compare only — every input already exists on `Job` and in the
autofill profile; this module persists nothing.

Verdict semantics (inv-honesty applied to screening):
- ``conflict``            — a stated requirement contradicts a known answer.
- ``clear``               — at least one stated requirement was evaluated and
                            every evaluable one passed.
- ``incomplete_profile``  — a stated requirement exists that the profile
                            cannot answer. Not a pass.
- ``unstated``            — the posting states no screenable requirement.
                            Not a pass either: "no blockers stated" is a
                            weaker claim than "you clear the stated blockers".

Salary never conflicts — pay is negotiable — it only warns. It compares in one
currency: the posted ceiling is converted into your desired salary's currency
(the one its text names, else your home currency) on the ECB reference rates.
With no rate, or a side that names no currency, the check says it cannot
compare (``cant_compare``), never a pass or a warning.
"""

import re
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.job import Job
from app.schemas.autofill_profile import WorkAuth
from app.services import money

# Statuses that clear a citizen/green-card gate.
_CITIZEN_OR_GC = {"citizen", "permanent_resident"}
# Status → (needs sponsorship now, needs sponsorship in the future) when the
# profile carries no explicit sponsorship answers. TN is deliberately absent:
# TN renewal mechanics vary enough that inferring either answer would guess a
# knockout answer, which the WorkAuth schema forbids.
_STATUS_SPONSORSHIP = {
    "citizen": (False, False),
    "permanent_resident": (False, False),
    "opt": (False, True),
    "stem_opt": (False, True),
    "h1b": (True, True),
    "other_visa": (True, True),
    "not_authorized": (True, True),
}

_OPT_STATUSES = {"opt", "stem_opt"}


def _sponsorship_needs(work_auth: WorkAuth) -> tuple[bool | None, bool | None]:
    """Explicit answers win; status only fills the blanks."""
    now, future = work_auth.sponsorship_now, work_auth.sponsorship_future
    inferred = _STATUS_SPONSORSHIP.get(work_auth.status or "")
    if inferred is not None:
        if now is None:
            now = inferred[0]
        if future is None:
            future = inferred[1]
    return now, future


def _gc_required_verdict(work_auth: WorkAuth) -> tuple[str, str | None]:
    if work_auth.status is None:
        return (
            "profile_missing",
            "This job requires US citizenship or a green card. Add your work "
            "authorization in Profile › Autofill.",
        )
    if work_auth.status in _CITIZEN_OR_GC:
        return "pass", None
    return "conflict", "This job requires US citizenship or a green card."


def _no_sponsorship_verdict(work_auth: WorkAuth) -> tuple[str, str | None]:
    now, future = _sponsorship_needs(work_auth)
    if now or future:
        timing = "now" if now else "in the future"
        return (
            "conflict",
            f"This job doesn't sponsor visas, and you need sponsorship {timing}.",
        )
    if now is None or future is None:
        return (
            "profile_missing",
            "This job doesn't sponsor visas. Answer the sponsorship questions in "
            "Profile › Autofill.",
        )
    return "pass", None


def _work_auth_check(job: Job, work_auth: WorkAuth) -> dict[str, Any]:
    stated = job.work_authorization
    check: dict[str, Any] = {
        "kind": "work_authorization",
        "job_value": stated,
        "profile_value": work_auth.status,
    }
    if not stated or stated == "unstated":
        return {**check, "result": "job_unstated", "message": None}
    if stated == "sponsorship_available":
        return {**check, "result": "pass", "message": "This job sponsors visas."}
    if stated == "citizen_or_gc_required":
        result, message = _gc_required_verdict(work_auth)
    else:  # no_sponsorship
        result, message = _no_sponsorship_verdict(work_auth)
    return {**check, "result": result, "message": message}


def _opt_check(job: Job, work_auth: WorkAuth) -> dict[str, Any] | None:
    stated = job.opt_accepted
    jd_states = bool(stated) and stated != "unstated"
    holder = work_auth.status in _OPT_STATUSES
    if not jd_states and not holder:
        return None
    check: dict[str, Any] = {
        "kind": "opt",
        "job_value": stated if jd_states else None,
        "profile_value": work_auth.status,
    }
    if not jd_states:
        return {**check, "result": "job_unstated", "message": None}
    result, message = _opt_verdict(stated, work_auth.status, holder)
    return {**check, "result": result, "message": message}


def _opt_verdict(stated: str, status: str | None, holder: bool) -> tuple[str, str | None]:
    if status is None:
        return (
            "profile_missing",
            "This job states an OPT policy. Add your work authorization in "
            "Profile › Autofill.",
        )
    if not holder:
        return "pass", None
    if stated == "no" or (stated == "stem_opt_ok" and status != "stem_opt"):
        policy = "doesn't accept OPT" if stated == "no" else "accepts STEM OPT only"
        return "conflict", f"This job {policy}."
    return "pass", None


def parse_desired_salary(raw: Any) -> Decimal | None:
    """First number in a free-text desired salary; '150k' style honored.

    Returns None when nothing parses — the scan then stays silent rather than
    comparing against a guess.
    """
    return money.parse_amount(raw)[0]


def _plain(amount: Decimal, currency: str | None) -> str:
    figure = f"{amount.normalize():f}" if amount == amount.to_integral() else str(amount)
    return f"{figure} {currency}" if currency else figure


def _rated(code: str, rates: Mapping[str, Any] | None) -> bool:
    return money.convert(Decimal(1), code, str((rates or {}).get("base") or "EUR"), rates) is not None


def _cannot_compare(posted: str | None, wanted: str | None, rates: Mapping[str, Any] | None) -> str:
    if posted is None:
        return "This job's pay names no currency, so it can't be compared with your desired salary."
    if wanted is None:
        return "Your desired salary names no currency, so this pay can't be compared with it."
    missing = posted if not _rated(posted, rates) else wanted
    return (f"There's no exchange rate for {missing} yet, so this pay can't be compared with your "
            "desired salary.")


def _salary_check(job: Job, preferences: dict[str, Any] | None, home_currency: str | None = None,
                  rates: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    ceiling = job.salary_max if job.salary_max is not None else job.salary_min
    if ceiling is None:
        return None
    # Yearly figures only: desired_salary is a yearly expectation, and
    # comparing it to an hourly/monthly rate would need a conversion guess.
    yearly = job.salary_period == "year" or (
        job.salary_period is None and Decimal(ceiling) >= 10000
    )
    if not yearly:
        return None
    desired, named = money.parse_amount((preferences or {}).get("desired_salary"))
    if desired is None:
        return None
    wanted = named or (home_currency.strip().upper() if home_currency else None)
    posted = job.salary_currency.strip().upper() if job.salary_currency else None
    check: dict[str, Any] = {
        "kind": "salary",
        "job_value": _plain(Decimal(ceiling), posted),
        "profile_value": _plain(desired, wanted),
    }
    if posted == wanted:
        # The same currency, or (a direct call with no home currency) neither side names one.
        compared = Decimal(ceiling)
    elif posted is None or wanted is None:
        compared = None
    else:
        compared = money.convert(Decimal(ceiling), posted, wanted, rates)
    if compared is None:
        return {**check, "result": "cant_compare", "message": _cannot_compare(posted, wanted, rates)}
    if compared < desired:
        return {
            **check,
            "result": "warning",
            "message": "The posted pay tops out below your desired salary.",
        }
    return {**check, "result": "pass", "message": None}


def _experience_check(job: Job, years_experience: int | None) -> dict[str, Any] | None:
    """Stated minimum years vs the profile's stated years (job_preferences).

    Warning severity like salary, never a conflict: "N+ years" is the classic
    soft-hard requirement — real ATS knockouts exist, but the bar is routinely
    cleared with less, and both numbers are self-reported. Omitted when either
    side is unstated; the years come from the user's own Job preferences field,
    never derived from KB date spans (a false conflict from an incomplete KB
    would be worse than an honest omission).
    """
    if job.years_experience_min is None or years_experience is None:
        return None
    check: dict[str, Any] = {
        "kind": "experience",
        "job_value": f"{job.years_experience_min}+",
        "profile_value": str(years_experience),
    }
    if years_experience < job.years_experience_min:
        return {
            **check,
            "result": "warning",
            "message": (
                f"This job asks for {job.years_experience_min}+ years. "
                f"Your profile says {years_experience}."
            ),
        }
    return {**check, "result": "pass", "message": None}


# The job's work mode: the stored key (`schemas/job_extraction.work_mode_key`: remote | hybrid |
# on_site), and any older spelling ("onsite", "In office"), all read as one.
_WORK_MODES = {"remote": "remote", "hybrid": "hybrid", "onsite": "onsite", "inoffice": "onsite",
               "office": "onsite", "inperson": "onsite"}
# A US state as its two-letter code, whichever way it was written: the extraction writes codes,
# the profile holds what the user typed.
_US_STATES = {
    "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar", "california": "ca",
    "colorado": "co", "connecticut": "ct", "delaware": "de", "district of columbia": "dc",
    "washington dc": "dc", "florida": "fl", "georgia": "ga", "hawaii": "hi", "idaho": "id",
    "illinois": "il", "indiana": "in", "iowa": "ia", "kansas": "ks", "kentucky": "ky",
    "louisiana": "la", "maine": "me", "maryland": "md", "massachusetts": "ma", "michigan": "mi",
    "minnesota": "mn", "mississippi": "ms", "missouri": "mo", "montana": "mt", "nebraska": "ne",
    "nevada": "nv", "new hampshire": "nh", "new jersey": "nj", "new mexico": "nm",
    "new york": "ny", "north carolina": "nc", "north dakota": "nd", "ohio": "oh",
    "oklahoma": "ok", "oregon": "or", "pennsylvania": "pa", "rhode island": "ri",
    "south carolina": "sc", "south dakota": "sd", "tennessee": "tn", "texas": "tx", "utah": "ut",
    "vermont": "vt", "virginia": "va", "washington": "wa", "west virginia": "wv",
    "wisconsin": "wi", "wyoming": "wy",
}
_CITY_ALIASES = {"nyc": "new york", "new york city": "new york", "sf": "san francisco"}
_RELOCATE = {"yes": "yes", "y": "yes", "true": "yes", "no": "no", "n": "no", "false": "no"}
# Countries as a two-letter code, whichever way they were written.
_COUNTRIES = {
    "us": "us", "usa": "us", "united states": "us", "united states of america": "us",
    "gb": "gb", "uk": "gb", "united kingdom": "gb", "great britain": "gb",
    "ca": "ca", "canada": "ca",
}
_CA_PROVINCES = {"ab", "bc", "mb", "nb", "nl", "ns", "nt", "nu", "on", "pe", "qc", "sk", "yt"}


def _words(value: Any) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", str(value or "").casefold()).split())


def _work_mode(raw: Any) -> str | None:
    return _WORK_MODES.get(re.sub(r"[\s_-]", "", str(raw or "").casefold()))


def city_key(value: Any) -> str:
    """A city as one comparable key: casefolded words, "NYC" is "new york"."""
    return _CITY_ALIASES.get(_words(value), _words(value))


def state_code(value: Any) -> str:
    """A US state as its code; "D.C." and "N.Y." come out as dc and ny."""
    words = _words(value)
    if re.fullmatch(r"\w( \w)+", words):
        words = words.replace(" ", "")
    return _US_STATES.get(words, words)


_city, _state = city_key, state_code   # this module's own short names


def _country(country: Any, state: Any) -> str:
    """The country as a code; with none stated, the state says it when it can (a US state,
    a Canadian province), else empty. A full name this table does not know is unknown, so it
    never disagrees."""
    named = _words(country)
    if named:
        return _COUNTRIES.get(named, named if len(named) == 2 else "")
    code = _state(state)
    if code in _US_STATES.values():
        return "us"
    return "ca" if code in _CA_PROVINCES else ""


def _agree(one: str, other: str) -> bool:
    """Two values disagree only when both are stated and differ."""
    return not (one and other and one != other)


def _city_then_state(location: str, city: str, code: str) -> bool:
    """`location` (padded words) holds the city with the state right after it."""
    names = {code, *(name for name, abbr in _US_STATES.items() if abbr == code)}
    return any(f" {city} {name} " in location for name in names)


def _listed_city(job: Job, personal: dict[str, Any]) -> bool:
    """A posting that lists several places ("New York, NY or San Francisco, CA") names your city
    among them: its words hold your city as a whole run, followed by your state when you gave
    one ("Portland, ME" is not Portland, OR)."""
    location, city = f" {_words(job.location_raw)} ", _city(personal.get("city"))
    state = _state(personal.get("state"))
    if not city:
        return False
    return _city_then_state(location, city, state) if state else f" {city} " in location


def _same_place(job: Job, personal: dict[str, Any]) -> bool:
    if not _agree(_country(job.country, job.state), _country(personal.get("country"),
                                                             personal.get("state"))):
        return False
    job_state, home_state = _state(job.state), _state(personal.get("state"))
    if _city(job.city) and _city(job.city) == _city(personal.get("city")):
        if _agree(job_state, home_state):
            return True
    if job_state and job_state == home_state:
        return True
    return _listed_city(job, personal)


def _relocate_answer(preferences: dict[str, Any] | None) -> str | None:
    """`willing_to_relocate` as yes or no, or None: unset, or typed words that are neither
    ("Open to relocating for the right role" is a real answer, and not a yes)."""
    value = (preferences or {}).get("willing_to_relocate")
    if isinstance(value, bool):
        return "yes" if value else "no"
    return _RELOCATE.get(_words(value))


def _on_site_verdict(job: Job, mode: str, answer: str | None,
                     personal: dict[str, Any]) -> tuple[str, str | None]:
    where = job.city or job.state or job.location_raw or "another location"
    kind = "on-site" if mode == "onsite" else "hybrid"
    if answer == "yes":
        return "pass", None
    if not (_words(personal.get("city")) or _words(personal.get("state"))):
        return "profile_missing", (f"This job is {kind} in {where}. Add your city and state in "
                                   "Profile › Autofill.")
    if answer == "no":
        return "conflict", f"This job is {kind} in {where}. Your profile says you won't relocate."
    return "profile_missing", (f"This job is {kind} in {where}. Answer Willing to relocate in "
                               "Profile › Autofill.")


def _on_site_check(job: Job, preferences: dict[str, Any] | None,
                   personal: dict[str, Any]) -> dict[str, Any] | None:
    """Remote is a pass; on-site or hybrid where you live is a pass; elsewhere the relocation
    answer decides. An unknown work mode, or an on-site job with no city or state to compare
    ("On-site, United States"), states nothing, so it adds no check."""
    mode = _work_mode(job.work_mode)
    if mode is None:
        return None
    answer = _relocate_answer(preferences)
    check: dict[str, Any] = {"kind": "on_site", "job_value": mode, "profile_value": answer}
    if mode == "remote":
        return {**check, "result": "pass", "message": None}
    if not (_city(job.city) or _state(job.state)):
        return None
    if _same_place(job, personal):
        return {**check, "result": "pass", "message": None}
    result, message = _on_site_verdict(job, mode, answer, personal)
    return {**check, "result": result, "message": message}


def _work_auth_for_job(job: Job, by_market: dict[str, WorkAuth], home_market: str | None) -> WorkAuth:
    """The job's country's work-permit answers (inv-work-permit-per-country). A job that names no
    country is screened with the home market's, the one assumption this advisory scan makes (a form
    on that job still gets none, `autofill_country`); a country no market covers has none."""
    from app.services import autofill_country

    market = autofill_country.market_for_job_country(job.country_code) if job.country_code else home_market
    return by_market.get(market or "") or WorkAuth()


def scan_job(
    job: Job,
    work_auth: WorkAuth | None = None,
    preferences: dict[str, Any] | None = None,
    years_experience: int | None = None,
    personal: dict[str, Any] | None = None,
    *,
    work_auth_by_market: dict[str, WorkAuth] | None = None,
    home_market: str | None = None,
    home_currency: str | None = None,
    rates: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """`work_auth`: the answers to screen with; None reads the job's country's from
    `work_auth_by_market` (`scan_args`). `home_currency` and `rates` (ECB, `fx_rates.current`)
    put the salary check in one currency."""
    if work_auth is None:
        work_auth = _work_auth_for_job(job, work_auth_by_market or {}, home_market)
    # settings/autofill.json is hand-editable loose JSON; `preferences` and `personal` may
    # arrive as any shape.
    if not isinstance(preferences, dict):
        preferences = None
    personal = personal if isinstance(personal, dict) else {}
    optional = (
        _opt_check(job, work_auth),
        _salary_check(job, preferences, home_currency, rates),
        _experience_check(job, years_experience),
        _on_site_check(job, preferences, personal),
    )
    checks = [_work_auth_check(job, work_auth), *(c for c in optional if c is not None)]

    results = {c["result"] for c in checks}
    if "conflict" in results:
        status = "conflict"
    elif "profile_missing" in results:
        status = "incomplete_profile"
    elif results & {"pass", "warning"}:
        status = "clear"
    else:
        status = "unstated"
    return {"status": status, "checks": checks}


def scan_args(session: Session) -> dict[str, Any]:
    """The stored profile as `scan_job`'s keyword arguments, read once: a batch reuses it. Every
    market's work-permit answers ride along, and each job is screened with its own country's."""
    from app.services import autofill_profile, fx_rates, job_preferences, market_settings, money_settings

    profile = autofill_profile.get_profile(session)
    return {
        "home_currency": money_settings.home_currency(session),
        "rates": fx_rates.current(session),
        "work_auth_by_market": {
            market: autofill_profile.typed_work_auth(raw)
            for market, raw in autofill_profile.work_auth_entries(profile, None).items()
        },
        "home_market": market_settings.peek_market(session).home,
        "preferences": profile.get("preferences"),
        "years_experience": job_preferences.get_preferences(session).years_experience,
        "personal": profile.get("personal"),
    }


def scan_for(session: Session, job: Job) -> dict[str, Any]:
    """`scan_job` over the stored profile: the ONE reader behind the job page, the agent's final
    review and the Companion's `/api/jobs/match`. The profile is read once."""
    return scan_job(job, **scan_args(session))
