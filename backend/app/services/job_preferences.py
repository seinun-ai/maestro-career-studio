"""Job-search preferences storage: Setting row + file mirror, like
autofill_profile / quick_tailor_profile — but typed end to end. Malformed JSON
or a structurally invalid blob reads as defaults; stale favored roles degrade
per item so one retired catalog key cannot erase every preference on read."""

import json
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.schemas.job_preferences import FavoredRole, JobPreferences
from app.services import text_settings

JOB_PREFERENCES_KEY = "job_preferences"
JOB_PREFERENCES_FILE = "job_preferences.json"


def _degrade_stale_favored_roles(payload: Any) -> Any:
    """Preserve a readable preference blob when one stored role went stale."""
    if not isinstance(payload, dict) or not isinstance(payload.get("favored_roles"), list):
        return payload

    sanitized = dict(payload)
    favored_roles: list[dict[str, Any]] = []
    for raw in payload["favored_roles"]:
        try:
            favored = FavoredRole.model_validate(raw)
        except ValidationError:
            if not isinstance(raw, dict):
                continue
            try:
                favored = FavoredRole(label=raw.get("label") or "")
            except ValidationError:
                continue
        favored_roles.append(favored.model_dump())

    sanitized["favored_roles"] = favored_roles
    # This field is a projection. A stale stored copy must not fail validation
    # before JobPreferences can recompute it from the salvaged parent rows.
    sanitized.pop("role_categories", None)
    return sanitized


def _parse_preferences(raw: str) -> JobPreferences:
    if not raw.strip():
        return JobPreferences()
    try:
        payload = _degrade_stale_favored_roles(json.loads(raw))
        return JobPreferences.model_validate(payload)
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
