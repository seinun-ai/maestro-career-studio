from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.settings import SettingEnvelope
from app.services import countries

PayPeriod = Literal["year", "month", "hour"]


class MoneySettings(BaseModel):
    """How pay reads (`GET/PUT /api/settings/money`; Settings › Money, hours under Advanced).

    `home_currency` is the ISO 4217 code every figure is shown in. None means "where I live":
    the home market's currency, else `HOME_CURRENCY` (`money_settings.home_currency` resolves
    it), so moving home moves the currency until you pick one yourself. A code is validated
    against the currencies the country data names, never coerced.
    """

    home_currency: str | None = None
    period: PayPeriod = "year"
    show_posted: bool = True
    hours_per_year: int = Field(default=2080, ge=1, le=8784)

    @field_validator("home_currency", mode="before")
    @classmethod
    def _known_currency(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        code = str(value).strip().upper()
        if code not in countries.currency_codes():
            raise ValueError(f"home_currency must be an ISO 4217 code, got {value!r}")
        return code


class MoneySettingsResponse(SettingEnvelope[MoneySettings]):
    """The stored setting plus the currency it resolves to right now."""

    home_currency: str


class FxRatesOut(BaseModel):
    """`GET /api/fx/rates`: the cached ECB reference rates, units per euro.

    No cache yet reads as `date: None` and empty `rates`: the browser then shows posted amounts
    and converts nothing.
    """

    base: str = "EUR"
    date: str | None = None
    rates: dict[str, float] = {}
    fetched_at: str | None = None
    source: str
    source_url: str
