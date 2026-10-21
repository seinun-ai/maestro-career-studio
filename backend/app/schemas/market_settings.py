from pydantic import BaseModel, computed_field, field_validator, model_validator

from app.services import markets


def _known(value) -> str:
    key = str(value or "").strip().upper()
    if not markets.is_supported(key):
        raise ValueError(f"market must be one of {markets.keys()}, got {value!r}")
    return key


class MarketSetting(BaseModel):
    """Where the user lives (`home`: the home currency and date format) and every market they
    apply in (`apply_in`, in the order chosen, each once; empty reads as `[home]`).

    Markets are VALIDATED, never coerced: an unrecognized value 422s back to the picker instead of
    silently becoming US. Same rule as `role_category` on base resumes: normalizing human input
    would make a typo indistinguishable from a deliberate choice, and here the wrong answer means
    the wrong currency and the wrong demographic question set.

    A stored `{"market": X}` from before `home` existed reads as home = X, apply_in = [X]. The
    setting is a JSON text setting with a file mirror and may come from a sync peer that has not
    updated, so it is mapped when read, never migrated (the autofill veteran precedent). For the
    same peers `market` (= `home`) is still written; no reader of it remains in the app (SYSTEM.md
    §13 `market-home-apply-in`).
    """

    home: str = markets.DEFAULT_MARKET
    apply_in: list[str] = []

    @model_validator(mode="before")
    @classmethod
    def _legacy(cls, value):
        if isinstance(value, dict) and "market" in value and "home" not in value:
            return {"home": value["market"], "apply_in": [value["market"]]}
        return value

    @field_validator("home", mode="before")
    @classmethod
    def _known_home(cls, value):
        return _known(value)

    @field_validator("apply_in", mode="before")
    @classmethod
    def _known_list(cls, value):
        if isinstance(value, str):
            raise ValueError("apply_in must be a list of markets")
        seen: list[str] = []
        for item in value or []:
            key = _known(item)
            if key not in seen:
                seen.append(key)
        return seen

    @model_validator(mode="after")
    def _home_counts(self):
        if not self.apply_in:
            self.apply_in = [self.home]
        return self

    @computed_field
    @property
    def market(self) -> str:
        return self.home
