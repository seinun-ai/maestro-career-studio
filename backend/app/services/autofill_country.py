"""Which country's answers a form question gets (owner decision D9).

The rule, one place for every reader (`profile_for_job`, the fill loop's slot
lookup in `routers/autofill`, the knock-out scan):

1. **The country the question names.** "Are you authorised to work in the
   United Kingdom?" takes the UK's answers on any job. The question is read by
   `countries.mentioned_in`, the one sentence parser.
2. **Else the job's country**, its ISO `country_code` mapped to a market
   (`markets.for_country`: "GB" is the market "UK").
3. **Else nothing.** No answers means `missing_source`, and the Companion asks
   on that job, as for any unknown knock-out answer.

Never another country's answers, never a default: a question that names a
country with no answers, a country no market covers, or two countries ("the
United States or Canada", where a Yes in one and a No in the other has no one
true answer) is unknown too.

Answers are keyed by market (the market setting's own key, "UK"), stored under
`work_auth_by_country` (`autofill_profile`), and read as readers see them: the
stored answers over the ones a citizenship settles there
(`autofill_derive.answers_for`). `countries_authorized` is derived from them:
every country whose `authorized_now` reads Yes, a citizenship-settled one
included, plus what the user's own list for that country already names.

A country's own answers (`answers_by_country`, form_questions.yaml `answers`)
follow the same rule: `with_country_answers` writes one market's over the flat
slots they fill (`fills`), and drops every country's map, so no other country's
answer reaches the form.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

from app.schemas.autofill_profile import WorkAuth
from app.services import autofill_catalog, autofill_derive, autofill_profile, countries, form_questions, markets

# The market a question names that has no answers here, or that no market covers: unknown on any job.
_NOWHERE = ""

# Beside `work_auth_market` on a profile resolved for one question: the country that question's answer is
# for, in words, a country no market covers included (`country_for_question`). Never stored.
WORK_AUTH_COUNTRY = autofill_profile.WORK_AUTH_COUNTRY

# Beside `work_auth_market` on a job's profile: the flat slots ("preferences.desired_salary") the job's
# country's own answers filled (`with_country_answers`), so the catalog can word a figure in that
# country's terms only when it is that country's answer. Never stored; absent when none.
COUNTRY_ANSWERED = autofill_profile.COUNTRY_ANSWERED


def market_for_job_country(code: str | None) -> str | None:
    """A job's ISO country ("GB") as its market ("UK"); None when the job has none or no market
    covers it. "UK" in, as typed by hand, reads as GB."""
    return markets.for_country(countries.normalize(code))


def _named_market(question: str) -> str | None:
    """The market of the one country the question names; `_NOWHERE` for a country no market covers
    or for two or more countries; None when it names none."""
    named = countries.mentioned_in(question)
    if not named:
        return None
    if len(named) > 1:
        return _NOWHERE
    return markets.for_country(next(iter(named))) or _NOWHERE


def country_in_question(question: str, apply_in: Iterable[str]) -> str | None:
    """The market among `apply_in` whose country the question names, when it names exactly one."""
    market = _named_market(question)
    return market if market and market in {m.strip().upper() for m in apply_in} else None


def market_for_question(question: str, job_market: str | None) -> str | None:
    """Whose answers this question gets: the market it names, else the job's; None (unknown) when
    neither, or when it names a country with no market or several countries."""
    named = _named_market(question)
    if named is None:
        return job_market
    return named or None


def country_for_question(question: str, job_country: str | None) -> str | None:
    """The ISO country a work-permit question is about: the one it names, else the job's; None when it
    names two or more, or when neither names one. Unlike `market_for_question` it keeps a country no market
    covers ("BR"), so the Companion can say it cannot keep answers there rather than that the country is
    unclear."""
    named = countries.mentioned_in(question)
    if named:
        return next(iter(named)) if len(named) == 1 else None
    return countries.normalize(job_country)


def _authorized_countries(profile: Any, home: str | None) -> list[str]:
    """The country names of every market whose `authorized_now` reads Yes as readers see it
    (`autofill_derive.answers_for`), in `answered_markets` order: the stored markets, then the ones
    a citizenship settles."""
    names = []
    for market in autofill_derive.answered_markets(profile, home):
        answers = autofill_derive.answers_for(profile, market, home)
        if autofill_profile.typed_work_auth(answers, market).authorized_now is True:
            name = countries.label(markets.country_code(market))
            if name and name not in names:
                names.append(name)
    return names


def entry(profile: Any, market: str | None, home: str | None = None) -> dict[str, Any]:
    """One market's answers as the fill reads them (`{}`: none): the stored ones over the ones a
    citizenship settles there (`autofill_derive.answers_for`), with `countries_authorized` derived
    across every market. `home` places a legacy single `work_auth` (a read view has it placed
    already)."""
    own = dict(autofill_derive.answers_for(profile, market, home)) if market else {}
    derived = _authorized_countries(profile, home)
    if not own and not derived:
        return own
    listed = own.get("countries_authorized")
    listed = [str(c).strip() for c in listed if str(c).strip()] if isinstance(listed, list) else []
    known = {countries.normalize(c) or c.casefold() for c in listed}
    merged = listed + [c for c in derived if countries.normalize(c) not in known]
    if not own:
        # Only a cross-country fact: no answer about this market is invented around it.
        return {"countries_authorized": merged}
    return {**own, "countries_authorized": merged} if merged or "countries_authorized" in own else own


def with_work_auth(profile: Any, market: str | None, home: str | None = None) -> Any:
    """The profile with `work_auth` set to one market's answers, so every reader downstream
    (the catalog, the Companion's deterministic fill) stays country-blind, and `work_auth_market`
    naming that market (None: no market, so no country's answers)."""
    if not isinstance(profile, dict):
        return profile
    return {**profile, autofill_profile.WORK_AUTH: entry(profile, market, home),
            autofill_profile.WORK_AUTH_MARKET: market}


def _is_set(value: Any) -> bool:
    return value is not None and not (isinstance(value, str) and not value.strip())


def with_country_answers(profile: Any, market: str | None) -> Any:
    """The profile with one market's own answers (`answers_by_country[market]`) written over the
    flat slots they fill (`form_questions.answer_fills`: "preferences.desired_salary"), and no
    country's map: another country's answers never reach this one's form. A blank answer, or a key
    the market does not ask now, fills nothing, so the generic answer stays. The slots filled are
    named under `COUNTRY_ANSWERED`, always (`[]`: none), which marks the result as a job's view: a
    save refuses it (`autofill_profile.set_profile`). No market (`None`, or one Maestro does not
    keep): nothing is filled, and the map still goes."""
    if not isinstance(profile, dict):
        return profile
    out = {k: v for k, v in profile.items() if k != autofill_profile.ANSWERS_BY_COUNTRY}
    out[COUNTRY_ANSWERED] = []
    if not market:
        return out
    key = market.strip().upper()
    own = autofill_profile.answers_entries(profile).get(key, {})
    filled: list[str] = []
    for answer, slot in form_questions.answer_fills(key).items():
        value = own.get(answer)
        if not _is_set(value):
            continue
        section, leaf = slot.split(".", 1)
        values = out.get(section)
        out[section] = {**(values if isinstance(values, dict) else {}), leaf: value}
        filled.append(slot)
    out[COUNTRY_ANSWERED] = filled
    return out


def for_market(profile: Any, market: str | None, home: str | None = None, today: date | None = None) -> Any:
    """The profile as a form in `market` reads it, the one view every fill reads (the catalog, /choose's
    prompt and Jev's slots, /context): that market's work-permit answers as `work_auth`
    (`with_work_auth`), its own answers over the slots they fill (`with_country_answers`), no
    per-country map at all (no other country's answer is there), and the answers as a form takes them
    on `today` (`autofill_catalog.with_fill_rules`: citizenships as country names, no stale notice).
    /context adds `work_auth_by_country` back for agents."""
    view = with_country_answers(with_work_auth(profile, market, home), market)
    if not isinstance(view, dict):
        return view
    view.pop(autofill_profile.BY_COUNTRY, None)
    return autofill_catalog.with_fill_rules(view, today or date.today())


def work_auth_for(profile: Any, *, question: str, job_country: str | None,
                  home: str | None = None) -> WorkAuth:
    """The answers a form question gets, typed: `market_for_question` over the job's ISO
    country. `home` places a legacy single `work_auth` in a raw profile."""
    market = market_for_question(question, market_for_job_country(job_country))
    return autofill_profile.typed_work_auth(entry(profile, market, home) if market else {}, market)
