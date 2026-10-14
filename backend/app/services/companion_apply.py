"""The Companion's Apply switches, stored as the `companion_apply` setting."""

from sqlalchemy.orm import Session

from app.schemas.companion_apply import CompanionApplySettings
from app.services.json_settings import JsonSetting

COMPANION_APPLY = JsonSetting("companion_apply", "companion_apply.json", CompanionApplySettings)
# Key/filename stay importable: the profile bundle mirrors the setting by name.
COMPANION_APPLY_KEY = COMPANION_APPLY.key
COMPANION_APPLY_FILE = COMPANION_APPLY.filename


def get_settings(session: Session | None = None) -> CompanionApplySettings:
    return COMPANION_APPLY.get(session)


def set_settings(value: CompanionApplySettings, session: Session | None = None) -> CompanionApplySettings:
    return COMPANION_APPLY.set(value, session)
