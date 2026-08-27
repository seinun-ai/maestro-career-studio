"""Job-search preferences storage.

The one setting with a real salvage rule: stale favored roles degrade PER ITEM
so a single retired catalog key cannot erase every other preference on read.
"""

from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.schemas.job_preferences import FavoredRole, JobPreferences
from app.services.json_settings import JsonSetting


class _JobPreferencesSetting(JsonSetting[JobPreferences]):
    def migrate(self, payload: Any) -> Any:
        """Preserve a readable preference blob when one stored role went stale."""
        if not isinstance(payload, dict) or not isinstance(
            payload.get("favored_roles"), list
        ):
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
        # This field is a projection. A stale stored copy must not fail
        # validation before JobPreferences can recompute it from the salvaged
        # parent rows.
        sanitized.pop("role_categories", None)
        return sanitized


JOB_PREFERENCES = _JobPreferencesSetting(
    "job_preferences", "job_preferences.json", JobPreferences
)
# Key/filename stay importable: callers and tests address the setting by
# name, and the constants are now derived from the one definition above.
JOB_PREFERENCES_KEY = JOB_PREFERENCES.key
JOB_PREFERENCES_FILE = JOB_PREFERENCES.filename


def get_preferences(session: Session | None = None) -> JobPreferences:
    return JOB_PREFERENCES.get(session)


def peek_preferences(session: Session | None = None) -> JobPreferences:
    return JOB_PREFERENCES.peek(session)


def set_preferences(prefs: JobPreferences, session: Session | None = None) -> JobPreferences:
    return JOB_PREFERENCES.set(prefs, session)


def is_set(prefs: JobPreferences) -> bool:
    return JOB_PREFERENCES.is_set(prefs)
