"""Where the user lives and applies (`MarketSetting`): storage, plus the rules that read it."""

from sqlalchemy.orm import Session

from app.schemas.market_settings import MarketSetting
from app.services import countries, markets
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
    return MARKET.set(setting, session)


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


def offers_eeo(session: Session | None = None) -> bool:
    """Whether to offer an EEO section at all. Still reads the single `market` (= home) until
    the diversity set is offered per apply_in country (SYSTEM.md §13 market-home-apply-in)."""
    return markets.offers_eeo(peek_market(session).market)
