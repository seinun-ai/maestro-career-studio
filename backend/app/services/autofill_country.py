"""Which country's work-permit answers a form question gets (owner decision D9).

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
`work_auth_by_country` (`autofill_profile`). `countries_authorized` is derived
from them: every country whose `authorized_now` is Yes, plus what the user's
own list for that country already names.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.schemas.autofill_profile import WorkAuth
from app.services import autofill_profile, countries, markets

# The market a question names that has no answers here, or that no market covers: unknown on any job.
_NOWHERE = ""


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


def _authorized_countries(entries: dict[str, dict[str, Any]]) -> list[str]:
    """The country names of every market whose `authorized_now` reads Yes, in the stored order."""
    names = []
    for market, raw in entries.items():
        if autofill_profile.typed_work_auth(raw).authorized_now is True:
            name = countries.label(markets.country_code(market))
            if name:
                names.append(name)
    return names


def entry(profile: Any, market: str | None, home: str | None = None) -> dict[str, Any]:
    """One market's raw answers as the fill reads them (`{}`: none), with `countries_authorized`
    derived across every market. `home` places a legacy single `work_auth` (a read view has it
    placed already)."""
    entries = autofill_profile.work_auth_entries(profile, home)
    own = dict(entries.get(market or "", {})) if market else {}
    derived = _authorized_countries(entries)
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


def work_auth_for(profile: Any, *, question: str, job_country: str | None,
                  home: str | None = None) -> WorkAuth:
    """The answers a form question gets, typed: `market_for_question` over the job's ISO
    country. `home` places a legacy single `work_auth` in a raw profile."""
    market = market_for_question(question, market_for_job_country(job_country))
    return autofill_profile.typed_work_auth(entry(profile, market, home) if market else {})
