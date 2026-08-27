"""Auto-apply settings storage."""

from sqlalchemy.orm import Session

from app.schemas.auto_apply import AutoApplySettings
from app.services.json_settings import JsonSetting

AUTO_APPLY = JsonSetting("auto_apply", "auto_apply.json", AutoApplySettings)
# Key/filename stay importable: callers and tests address the setting by
# name, and the constants are now derived from the one definition above.
AUTO_APPLY_KEY = AUTO_APPLY.key
AUTO_APPLY_FILE = AUTO_APPLY.filename


def get_settings(session: Session | None = None) -> AutoApplySettings:
    return AUTO_APPLY.get(session)


def peek_settings(session: Session | None = None) -> AutoApplySettings:
    return AUTO_APPLY.peek(session)


def set_settings(settings: AutoApplySettings, session: Session | None = None) -> AutoApplySettings:
    return AUTO_APPLY.set(settings, session)
