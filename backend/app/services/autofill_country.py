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
each citizenship's own country first, then every country whose `authorized_now`
reads Yes, a citizenship-settled one included, after what the user's own list
for that country already names.

A country's own answers (`answers_by_country`, form_questions.yaml `answers`)
follow the same rule: `with_country_answers` writes one market's over the flat
slots they fill (`fills`), and drops every country's map, so no other country's
answer reaches the form. Pay included: once countries are chosen the home's
`desired_salary` reaches only the home's jobs and a job with no market, and a
country with no pay of its own gets none (`autofill_profile.pay_for`).
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
# country's own answers filled (`with_country_answers`; `[]` for none), the home's `desired_salary` on
# a home job included once countries are chosen, so the catalog can word a figure in that country's
# terms only when it is that country's answer. Every job's view carries it, and a save that does is
# refused (`autofill_profile.job_view_refusal`); never stored.
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
    """The country names the user may work in, each once: first each citizenship's own country, in
    the stored order (a citizen may work there, a country no market covers included, unless their own
    answer for its market says No), then every market whose `authorized_now` reads Yes as readers see
    it (`autofill_derive.answers_for`), in `answered_markets` order: the stored markets, then the ones
    a citizenship settles."""
    def authorized(market: str) -> bool | None:
        answers = autofill_derive.answers_for(profile, market, home)
        return autofill_profile.typed_work_auth(answers, market).authorized_now

    own = [code for code in autofill_derive.citizenships(profile)
           if (market := markets.for_country(code)) is None or authorized(market) is not False]
    settled = [markets.country_code(m) for m in autofill_derive.answered_markets(profile, home)
               if authorized(m) is True]
    names: list[str] = []
    for code in [*own, *settled]:
        name = countries.label(code)
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


def _with_slot(view: dict[str, Any], slot: str, value: Any) -> None:
    """`value` written into `view`'s flat slot ("preferences.current_ctc"), its section copied, not
    changed in place; None takes the slot out (a section that never held it is left as it is)."""
    section, leaf = slot.split(".", 1)
    values = view.get(section)
    values = values if isinstance(values, dict) else {}
    if value is not None:
        view[section] = {**values, leaf: value}
    elif leaf in values:
        view[section] = {k: v for k, v in values.items() if k != leaf}


def with_country_answers(profile: Any, market: str | None, *, chosen_home: str | None) -> Any:
    """The profile with one market's own answers (`answers_by_country[market]`) written over the
    flat slots they fill (`form_questions.answer_fills`: "preferences.current_ctc"), and no
    country's map: another country's answers never reach this one's form. Apart from pay (below), a
    blank answer, or a key the market does not ask now, fills nothing, so the generic answer stays.

    Pay is the one answer whose slot, `preferences.desired_salary`, is also the home's: it holds
    `autofill_profile.pay_for(profile, market, chosen_home)`, and with none the slot leaves the
    view, so the form's pay question is left and the Companion asks on that job (owner decision 1
    of docs/plans/2026-11-02-start-and-pay-design.md: a figure in another country's currency and
    terms is no answer here). `chosen_home` is `autofill_profile.chosen_home()`, passed by every
    caller, never inferred: chosen, a home job reads the home's `desired_salary` and any other
    country its own `expected_pay` or nothing; unchosen (None), the one figure stays for every
    country that has none of its own, as before any country was chosen.

    The slots filled are named under `COUNTRY_ANSWERED`, always (`[]`: none), which marks the result
    as a job's view: a save refuses it (`autofill_profile.set_profile`). Pay is named when the figure
    is that country's own: another market's `expected_pay`, and, once chosen, the home's
    `desired_salary` on a home job, so the catalog words it in that country's terms
    (`autofill_catalog._pay_describe`). No market (`None`, or one Maestro does not keep): nothing is
    filled, the home pay stays, and the map still goes."""
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
        if answer == autofill_profile.EXPECTED_PAY:
            pay = autofill_profile.pay_for(profile, key, chosen_home)
            _with_slot(out, slot, pay)
            # Chosen, every figure `pay_for` gives is a country's own (the home's on a home job, else
            # the market's); unchosen, only a market's own `expected_pay` is, not the one figure.
            is_own = chosen_home is not None or autofill_profile.own_pay(profile, key) is not None
            if pay is not None and is_own:
                filled.append(slot)
            continue
        value = own.get(answer)
        if _is_set(value):
            _with_slot(out, slot, value)
            filled.append(slot)
    out[COUNTRY_ANSWERED] = filled
    return out


def for_market(
    profile: Any, market: str | None, *, chosen_home: str | None, today: date | None = None
) -> Any:
    """The profile as a form in `market` reads it, the one view every fill reads (the catalog, /choose's
    prompt and Jev's slots, /context): that market's work-permit answers as `work_auth`
    (`with_work_auth`), its own answers over the slots they fill and its pay, or none
    (`with_country_answers`, by `chosen_home`), no per-country map at all (no other country's answer
    is there), and the answers as a form takes them on `today` (`autofill_catalog.with_fill_rules`:
    citizenships as country names, notice in words as well as days, no stale notice). `profile` is a
    read view (`get_profile`), its legacy one-set `work_auth` already placed as the home's, so no
    stored home is taken here: the one home this view takes is `chosen_home`, the pay's. /context
    adds `work_auth_by_country` back for agents."""
    view = with_country_answers(with_work_auth(profile, market), market, chosen_home=chosen_home)
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
