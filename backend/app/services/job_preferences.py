"""Job-search preferences storage: Setting row + file mirror, like
autofill_profile / quick_tailor_profile — but typed end to end (the shape is
new, there is no legacy JSON to tolerate). A hand-edited file that fails
validation reads as defaults: a blank picker beats a 500 on every consumer."""

import json

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.schemas.job_preferences import JobPreferences
from app.services import text_settings

JOB_PREFERENCES_KEY = "job_preferences"
JOB_PREFERENCES_FILE = "job_preferences.json"


def _parse_preferences(raw: str) -> JobPreferences:
    if not raw.strip():
        return JobPreferences()
    try:
        return JobPreferences.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError):
        return JobPreferences()


def get_preferences(session: Session | None = None) -> JobPreferences:
    return _parse_preferences(
        text_settings.get_text(JOB_PREFERENCES_KEY, JOB_PREFERENCES_FILE, session)
    )


def peek_preferences(session: Session | None = None) -> JobPreferences:
    return _parse_preferences(
        text_settings.peek_text(JOB_PREFERENCES_KEY, JOB_PREFERENCES_FILE, session)
    )


def set_preferences(prefs: JobPreferences, session: Session | None = None) -> JobPreferences:
    text_settings.set_text(
        JOB_PREFERENCES_KEY,
        JOB_PREFERENCES_FILE,
        prefs.model_dump_json(indent=2),
        session,
    )
    return prefs


def is_set(prefs: JobPreferences) -> bool:
    return prefs != JobPreferences()
