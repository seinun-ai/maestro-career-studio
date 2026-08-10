"""Auto-apply settings storage: Setting row + file mirror.
A hand-edited file that fails validation reads as defaults."""

import json

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.schemas.auto_apply import AutoApplySettings
from app.services import text_settings

AUTO_APPLY_KEY = "auto_apply"
AUTO_APPLY_FILE = "auto_apply.json"


def _parse_settings(raw: str) -> AutoApplySettings:
    if not raw.strip():
        return AutoApplySettings()
    try:
        return AutoApplySettings.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError):
        return AutoApplySettings()


def get_settings(session: Session | None = None) -> AutoApplySettings:
    return _parse_settings(
        text_settings.get_text(AUTO_APPLY_KEY, AUTO_APPLY_FILE, session)
    )


def peek_settings(session: Session | None = None) -> AutoApplySettings:
    return _parse_settings(
        text_settings.peek_text(AUTO_APPLY_KEY, AUTO_APPLY_FILE, session)
    )


def set_settings(settings: AutoApplySettings, session: Session | None = None) -> AutoApplySettings:
    text_settings.set_text(
        AUTO_APPLY_KEY,
        AUTO_APPLY_FILE,
        settings.model_dump_json(indent=2),
        session,
    )
    return settings
