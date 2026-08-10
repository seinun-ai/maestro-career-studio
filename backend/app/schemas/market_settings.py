from pydantic import BaseModel, field_validator

from app.services import markets


class MarketSetting(BaseModel):
    """Which job market the user applies in.

    Drives the default job currency, whether an EEO question set is offered at
    all, and the work-authorization vocabulary. One setting rather than three so
    they cannot drift out of sync.

    `market` is VALIDATED, never coerced: an unrecognized explicit value 422s
    back to the picker instead of silently becoming US. Same rule as
    `role_category` on base resumes — normalizing human input would make a typo
    indistinguishable from a deliberate choice, and here the wrong answer means
    the wrong currency and the wrong demographic question set.
    """

    market: str = markets.DEFAULT_MARKET

    @field_validator("market", mode="before")
    @classmethod
    def _known_market(cls, value):
        key = str(value or "").strip().upper()
        if not markets.is_supported(key):
            raise ValueError(
                f"market must be one of {markets.keys()}, got {value!r}"
            )
        return key
