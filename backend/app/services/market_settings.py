"""Where the user lives and applies (`MarketSetting`): storage, plus the rules that read it."""

from typing import Any

from sqlalchemy.orm import Session

from app.schemas.market_settings import MarketSetting
from app.schemas.money import MoneySettings
from app.services import countries, markets, text_settings
from app.services.json_settings import JsonSetting

MARKET = JsonSetting("market", "market.json", MarketSetting)
# Key/filename stay importable: callers and tests address the setting by
# name, and the constants are now derived from the one definition above.
MARKET_KEY = MARKET.key
MARKET_FILE = MARKET.filename


def get_market(session: Session | None = None) -> MarketSetting:
    return MARKET.get(session)


def peek_market(session: Session | None = None) -> MarketSetting:
    """Non-mutating read — must not lazy-seed a Setting row or file mirror.

    `setup_status` reads through this, and a status request that writes would
    make the derived-not-stored contract a lie (SYSTEM.md §4 Setup status).
    """
    return MARKET.peek(session)


def set_market(setting: MarketSetting, session: Session | None = None) -> MarketSetting:
    """Store where you live and apply. A move of `home` first pins a legacy one-set work-permit answer
    to the home it has been read as (`autofill_profile.pin_legacy_work_auth`), in the same session. The
    pin first, because on its own it changes no read: a refusal or a failure before the move lands
    leaves both settings meaning what they meant."""
    from app.db import SessionLocal
    from app.services import autofill_profile

    owns_session = session is None
    session = session or SessionLocal()
    try:
        before = peek_market(session).home
        if setting.home != before:
            autofill_profile.pin_legacy_work_auth(before, session)
        return MARKET.set(setting, session)
    finally:
        if owns_session:
            session.close()


# What an agent's save of where the user lives takes (`PATCH /api/settings/market`, MCP `set_markets`):
# the market setting's two fields and the money setting's currency, no other money field.
AGENT_FIELDS = frozenset({"home", "apply_in", "home_currency"})


def patch_place(changes: dict[str, Any], session: Session) -> MarketSetting:
    """An agent's save of where the user lives and applies, and of the currency pay reads in, as one
    transaction (`text_settings.one_commit`): `home` alone keeps `apply_in` as stored and the reverse,
    a None field is left as stored, and `home_currency` changes only the money setting's currency
    ("" follows home again; every other money field stays). Both settings are validated before
    either is written (their own ValidationError, the words their PUTs use), so nothing lands unless
    everything does. No field: nothing is written. Returns the market setting as stored."""
    from app.services import money_settings

    refused = sorted(set(changes) - AGENT_FIELDS)
    if refused:
        raise ValueError(
            f"Not written by an agent's save: {', '.join(refused)}. The fields are "
            f"{', '.join(sorted(AGENT_FIELDS))}."
        )
    home, apply_in, currency = (changes.get(k) for k in ("home", "apply_in", "home_currency"))
    if home is None and apply_in is None and currency is None:
        return peek_market(session)
    with text_settings.one_commit(session):
        stored = peek_market(session)
        place = None
        if home is not None or apply_in is not None:
            place = MarketSetting.model_validate({
                "home": stored.home if home is None else home,
                "apply_in": stored.apply_in if apply_in is None else apply_in,
            })
        money = None
        if currency is not None:
            money = MoneySettings.model_validate(
                {**money_settings.peek_settings(session).model_dump(), "home_currency": currency or None}
            )
        if place is not None:
            set_market(place, session)
        if money is not None:
            money_settings.set_settings(money, session)
        saved = peek_market(session)
    return saved


def is_set(setting: MarketSetting) -> bool:
    """Whether the user has actually chosen a market.

    A stored value equal to the default is indistinguishable from never having
    chosen, which is deliberate: both mean "no explicit opinion", and both
    should let HOME_CURRENCY answer for currency purposes.
    """
    return MARKET.is_set(setting)


def home_market_currency(session: Session | None = None) -> str:
    """The currency of where the user lives: the chosen home market's, else `HOME_CURRENCY`.

    Uses a NON-MUTATING read (capture runs it inside its transaction, and the seeding read would
    write a Setting row mid-capture). The market setting is user-chosen and visible in the UI; the
    env var is deployment config. With no market chosen yet (a stored value equal to the default
    counts as none), the env var still answers, so behaviour is unchanged until the user opts in.
    One source per answer, never both.
    """
    stored = peek_market(session)
    if is_set(stored):
        return markets.currency_for(stored.home)
    from app.config import settings

    return settings.home_currency


def default_currency_for_capture(
    session: Session | None = None, job_country_code: str | None = None
) -> str:
    """ISO 4217 default stamped on a newly captured job that states an amount but no currency.

    The job's own country first (`countries.currency`, data: a German job is posted in euros
    wherever the user lives), else the home currency (`home_market_currency`). Either way it is an
    assumption, and the caller marks it `salary_currency_assumed`.
    """
    return countries.currency(job_country_code) or home_market_currency(session)


def offers_eeo(session: Session | None = None, country: str | None = None) -> bool:
    """Whether a checked diversity set exists for `country` (a market key, "UK", or an ISO code,
    "GB"); with no country, whether any market you apply in has one. A country no market covers
    has none: `markets.offers_eeo` falls back to the default market for an unknown key, so it is
    never asked about one. Non-mutating (`setup_status` reads it)."""
    if country is None:
        return any(markets.offers_eeo(market) for market in peek_market(session).apply_in)
    key = country.strip().upper()
    market = key if markets.is_supported(key) else markets.for_country(countries.normalize(key))
    return market is not None and markets.offers_eeo(market)
