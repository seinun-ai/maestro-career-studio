"""Work-permit answers a citizenship settles, computed on read and never stored.

Only the rules the sources check verified (form_questions.yaml `citizenship`; sources doc changes
1-5): a citizen in their own country, EU/EEA/Swiss citizens in DE, NL and IE, British citizens in
Ireland, Irish citizens in the UK, GCC nationals in the UAE. Anything else stays unknown.

An answer the user gave always wins, and one that contradicts the rule (not allowed to work,
needing sponsorship now or later, or another status than the one it settles) turns the rule off for
that country: the user knows something the rule does not, so nothing is derived beside it
(inv-country-answers-stay-home).

Only readers call `answers_for`; the save path (`autofill_profile._as_stored`,
`work_auth_entries`) never does, so nothing derived reaches the stored profile.
"""

from typing import Any

from app.schemas.form_questions import DerivedAnswer
from app.services import autofill_profile, countries, form_questions, markets

_SETTLED = {"authorized_now": True, "sponsorship_now": False, "sponsorship_future": False}


def citizenships(profile: Any) -> list[str]:
    """`personal.citizenships` as ISO codes, in the order stored; an entry that names no country is
    left out."""
    personal = profile.get("personal") if isinstance(profile, dict) else None
    return countries.codes_in(personal.get(autofill_profile.CITIZENSHIPS) if isinstance(personal, dict) else None)


def derived_for(citizenships: list[str], market: str) -> dict[str, DerivedAnswer]:
    """The answers a citizenship settles in `market`: allowed to work, no sponsorship now or later,
    and the status its rule names when the market's list has it. The market's own citizenship comes
    first, then the others in order, and the first with a rule settles it; {} when none has one."""
    own = markets.country_code(market)
    for code in sorted(citizenships, key=lambda c: c != own):
        rule = form_questions.citizenship_rule(code, market)
        if rule is None:
            continue
        values: dict[str, Any] = dict(_SETTLED)
        if rule.status and rule.status in form_questions.status_values(market):
            values["status"] = rule.status
        return {key: DerivedAnswer(value=value, via=code) for key, value in values.items()}
    return {}


def settled_markets(citizenships: list[str]) -> list[str]:
    """The markets Maestro keeps, in `markets.keys()` order, where a citizenship settles that the
    user may work."""
    return [m for m in markets.keys() if derived_for(citizenships, m)]


def answered_markets(profile: Any, home: str | None = None) -> list[str]:
    """The markets that may hold work-permit answers as readers see them: each stored one, in the
    stored order, then each a citizenship settles (`settled_markets`), once each. `home` places a
    legacy single `work_auth` in a raw profile."""
    stored = autofill_profile.work_auth_entries(profile, home)
    return list(dict.fromkeys([*stored, *settled_markets(citizenships(profile))]))


def derived_in_effect(profile: Any, market: str, home: str | None = None) -> dict[str, DerivedAnswer]:
    """The answers a citizenship settles in `market` that readers use (`derived_for`), or {} when a
    given answer differs from one it settles: the user knows something the rule does not, so the
    rule is off for that country. What the fill reads (`answers_for`) and what Profile shows as
    "From your citizenship" (`form_questions.resolve`) both come from here. `home` places a legacy
    single `work_auth` in a raw profile (a read view has it placed already)."""
    return _in_effect(profile, _key(market), home)[0]


def answers_for(profile: Any, market: str, home: str | None = None) -> dict[str, Any]:
    """One market's permit answers as readers see them: each given answer over the derived ones.

    Two shapes come back, so callers read the result through `typed_work_auth(..., market)`: the
    stored entry as it is when nothing is derived (no citizenship rule, or a given answer that
    differs from one it settles: `derived_in_effect`), else the derived answers with the given ones
    laid over them under the typed keys. A given answer is one the typed reader can use: a blank, a
    status outside the market's list or a non-answer ("maybe") hides nothing."""
    market = _key(market)
    derived, given = _in_effect(profile, market, home)
    if not derived:
        return autofill_profile.work_auth_entries(profile, home).get(market, {})
    return {**{k: d.value for k, d in derived.items()}, **given}


def _key(market: str) -> str:
    return str(market or "").strip().upper()


def _in_effect(
    profile: Any, market: str, home: str | None
) -> tuple[dict[str, DerivedAnswer], dict[str, Any]]:
    """The rule, once: what a citizenship settles in `market` (a key) and the answers the user gave
    there as the typed reader keeps them; the derived side is {} when a given answer differs from
    one it settles. With nothing derived, the given answers are not read ({})."""
    derived = derived_for(citizenships(profile), market)
    if not derived:
        return {}, {}
    stored = autofill_profile.work_auth_entries(profile, home).get(market, {})
    given = autofill_profile.typed_work_auth(stored, market).model_dump(exclude_defaults=True)
    if any(k in given and given[k] != d.value for k, d in derived.items()):
        return {}, given
    return derived, given
