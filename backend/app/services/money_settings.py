"""The user's money settings (`MoneySettings`), stored like every profile setting.

Kept apart from `money.py`, which stays pure arithmetic. The home currency resolves in one
order, one source per answer: the currency you picked, else where you live
(`market_settings.home_market_currency`: the home market's currency once you chose a market,
else the deployment's `HOME_CURRENCY`).
"""

from sqlalchemy.orm import Session

from app.schemas.money import MoneySettings
from app.services import market_settings
from app.services.json_settings import JsonSetting

MONEY = JsonSetting("money", "money.json", MoneySettings)
MONEY_KEY = MONEY.key
MONEY_FILE = MONEY.filename


def get_settings(session: Session | None = None) -> MoneySettings:
    return MONEY.get(session)


def peek_settings(session: Session | None = None) -> MoneySettings:
    """Non-mutating read, for callers inside another transaction."""
    return MONEY.peek(session)


def set_settings(value: MoneySettings, session: Session | None = None) -> MoneySettings:
    return MONEY.set(value, session)


def home_currency(session: Session | None = None) -> str:
    """The ISO 4217 code pay is shown in."""
    return peek_settings(session).home_currency or market_settings.home_market_currency(session)
