"""Selected-market storage: Setting row + file mirror, like job_preferences.

A hand-edited file that fails validation reads as the default market rather
than 500-ing every consumer — but note the asymmetry with the API: a bad value
arriving from a HUMAN 422s at the schema boundary, while a bad value already on
disk degrades quietly. Same split job_preferences uses.
"""

import json

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.schemas.market_settings import MarketSetting
from app.services import markets, text_settings

MARKET_KEY = "market"
MARKET_FILE = "market.json"


def _parse(raw: str) -> MarketSetting:
    if not raw.strip():
        return MarketSetting()
    try:
        return MarketSetting.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError):
        return MarketSetting()


def get_market(session: Session | None = None) -> MarketSetting:
    return _parse(text_settings.get_text(MARKET_KEY, MARKET_FILE, session))


def peek_market(session: Session | None = None) -> MarketSetting:
    """Non-mutating read — must not lazy-seed a Setting row or file mirror.

    `setup_status` reads through this, and a status request that writes would
    make the derived-not-stored contract a lie (§4 Setup status).
    """
    return _parse(text_settings.peek_text(MARKET_KEY, MARKET_FILE, session))


def set_market(setting: MarketSetting, session: Session | None = None) -> MarketSetting:
    text_settings.set_text(
        MARKET_KEY, MARKET_FILE, setting.model_dump_json(indent=2), session
    )
    return setting


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


def is_set(setting: MarketSetting) -> bool:
    """Whether the user has actually chosen a market.

    A stored value equal to the default is indistinguishable from never having
    chosen, which is deliberate: both mean "no explicit opinion", and both
    should let HOME_CURRENCY answer for currency purposes.
    """
    return setting != MarketSetting()


def offers_eeo(session: Session | None = None) -> bool:
    """Whether to offer an EEO section at all for the selected market."""
    return markets.offers_eeo(peek_market(session).market)
