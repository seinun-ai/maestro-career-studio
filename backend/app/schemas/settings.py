from typing import Any

from pydantic import BaseModel

from app.schemas.auto_apply import AutoApplySettings
from app.schemas.eeo_consent import EeoConsent
from app.schemas.job_preferences import JobPreferences
from app.schemas.market_settings import MarketSetting


class TextSettingPayload(BaseModel):
    value: str


class AutofillProfilePayload(BaseModel):
    value: dict[str, Any]


class QuickTailorProfilePayload(BaseModel):
    value: dict[str, Any]


class McpWorkflowPayload(BaseModel):
    value: dict[str, Any]


class JobPreferencesPayload(BaseModel):
    value: JobPreferences


class MarketPayload(BaseModel):
    value: MarketSetting


class AutoApplyPayload(BaseModel):
    value: AutoApplySettings


class EeoConsentPayload(BaseModel):
    value: EeoConsent


class PromptPayload(BaseModel):
    value: str


class SettingValue(BaseModel):
    key: str
    value: str
