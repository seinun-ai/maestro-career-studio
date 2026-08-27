"""Selected-market storage, plus the currency rule that reads it."""

from sqlalchemy.orm import Session

from app.schemas.market_settings import MarketSetting
from app.services import markets
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


def default_currency_for_capture(session: Session | None = None) -> str:
    """ISO 4217 default stamped on a newly captured job that states an amount.

    Uses a NON-MUTATING read: this runs inside the capture transaction, and the
    seeding read would write a Setting row mid-capture.

    Precedence is market first, `HOME_CURRENCY` second. The market setting is
    user-chosen and visible in the UI; the env var is deployment config. When no
    market row exists yet — a pre-existing install that never opened the picker —
    the env var still answers, so behaviour is unchanged until the user opts in.
    Both must never be consulted for the same job; one source per answer.
    """
    stored = peek_market(session)
    if is_set(stored):
        return markets.currency_for(stored.market)
    from app.config import settings

    return settings.home_currency


def offers_eeo(session: Session | None = None) -> bool:
    """Whether to offer an EEO section at all for the selected market."""
    return markets.offers_eeo(peek_market(session).market)
