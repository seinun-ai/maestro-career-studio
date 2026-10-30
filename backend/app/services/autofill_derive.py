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
    raw = personal.get(autofill_profile.CITIZENSHIPS) if isinstance(personal, dict) else None
    if not isinstance(raw, list):
        return []
    return [code for code in (countries.normalize(c) for c in raw if isinstance(c, str)) if code]


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


def answers_for(profile: Any, market: str, home: str | None = None) -> dict[str, Any]:
    """One market's permit answers as readers see them: each given answer over the derived ones.

    Two shapes come back, so callers read the result through `typed_work_auth(..., market)`: the
    stored entry as it is when nothing is derived (no citizenship rule, or a given answer that
    differs from one it settles), else the derived answers with the given ones laid over them under
    the typed keys. A given answer is one the typed reader can use: a blank, a status outside the market's
    list or a non-answer ("maybe") hides nothing. `home` places a legacy single `work_auth` in a raw
    profile (a read view has it placed already)."""
    market = str(market or "").strip().upper()
    stored = autofill_profile.work_auth_entries(profile, home).get(market, {})
    derived = derived_for(citizenships(profile), market)
    given = autofill_profile.typed_work_auth(stored, market).model_dump(exclude_defaults=True)
    if not derived or any(k in given and given[k] != d.value for k, d in derived.items()):
        return stored
    return {**{k: d.value for k, d in derived.items()}, **given}
