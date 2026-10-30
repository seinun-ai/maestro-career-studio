"""Work-permit answers a citizenship settles, computed on read and never stored.

Only the rules the sources check verified (form_questions.yaml `citizenship`; sources doc changes
1-5): a citizen in their own country, EU/EEA/Swiss citizens in DE, NL and IE, British citizens in
Ireland, Irish citizens in the UK, GCC nationals in the UAE. Anything else stays unknown, and an
answer the user gave always wins (inv-country-answers-stay-home).

Only readers call `answers_for`; the save path (`autofill_profile._as_stored`,
`work_auth_entries`) never does, so nothing derived reaches the stored profile.
"""

from typing import Any

from app.schemas.form_questions import DerivedAnswer
from app.services import autofill_profile, countries, form_questions

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
    """The answers the first citizenship with a rule for `market` settles: allowed to work, no
    sponsorship now or later, and the status the rule names when the market's list has it. {} when
    no citizenship has a rule there."""
    for code in citizenships:
        rule = form_questions.citizenship_rule(code, market)
        if rule is None:
            continue
        values: dict[str, Any] = dict(_SETTLED)
        if rule.status and rule.status in form_questions.status_values(market):
            values["status"] = rule.status
        return {key: DerivedAnswer(value=value, via=code) for key, value in values.items()}
    return {}


def _given(value: Any) -> bool:
    """Whether a stored value is an answer: a blank select ("") is none, as the typed reader has it."""
    return value is not None and not (isinstance(value, str) and not value.strip())


def answers_for(profile: Any, market: str, home: str | None = None) -> dict[str, Any]:
    """One market's permit answers as readers see them: each stored answer over the derived ones.
    With nothing derived, the stored answers as they are. `home` places a legacy single `work_auth`."""
    stored = autofill_profile.work_auth_entries(profile, home).get(market, {})
    derived = derived_for(citizenships(profile), market)
    if not derived:
        return stored
    # Under the typed keys, so a legacy pair the user gave is not hidden by a derived typed key.
    given = {k: v for k, v in autofill_profile.typed_shape(stored).items() if _given(v)}
    return {**{k: d.value for k, d in derived.items()}, **given}
