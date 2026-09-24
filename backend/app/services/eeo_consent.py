"""EEO standing-consent storage.

Values here are consent metadata only — never EEO answers.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.eeo_consent import CURRENT_POLICY_VERSION, EeoConsent
from app.services.json_settings import JsonSetting

logger = logging.getLogger(__name__)

EEO_CONSENT = JsonSetting("eeo_consent", "eeo_consent.json", EeoConsent)
# Key/filename stay importable: callers and tests address the setting by
# name, and the constants are now derived from the one definition above.
EEO_CONSENT_KEY = EEO_CONSENT.key
EEO_CONSENT_FILE = EEO_CONSENT.filename


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def get_consent(session: Session | None = None) -> EeoConsent:
    return EEO_CONSENT.get(session)


def peek_consent(session: Session | None = None) -> EeoConsent:
    return EEO_CONSENT.peek(session)


def set_consent(consent: EeoConsent, session: Session | None = None) -> EeoConsent:
    """Persist standing consent. Enabling without an acknowledgement stamp
    gets a server-side timestamp and the current policy version — auditability
    must not depend on the client clock.
    """
    if (consent.enabled or consent.consent_forms) and not consent.acknowledged_at:
        consent = consent.model_copy(
            update={
                "acknowledged_at": _now_iso(),
                "policy_version": CURRENT_POLICY_VERSION,
            }
        )
    return EEO_CONSENT.set(consent, session)


def withhold_unconsented(profile: Any, consent: Any) -> Any:
    """THE gate for protected-class answers (SYSTEM.md inv-eeo-standing-consent).

    `profile.eeo` leaves the server only when `consent` (the record as
    `model_dump(mode="json")` gives it) says `enabled`. Fails CLOSED: a consent
    that could not be computed (None, anything not a dict) is not consent. Every
    reader that hands the profile outward goes through here — GET
    /api/autofill/context (to the browser) and the /choose prompt (to a model
    provider) — so which path asks never decides what is disclosed. Returns a
    copy; the caller's dict is not changed."""
    consented = isinstance(consent, dict) and bool(consent.get("enabled"))
    if consented or not isinstance(profile, dict):
        return profile
    return {key: value for key, value in profile.items() if key != "eeo"}


def disclosable_profile(session: Session) -> dict[str, Any]:
    """The autofill profile with the gate applied, for a reader that needs the
    whole profile and no separate consent section (the /choose prompt)."""
    from app.services import autofill_profile

    try:
        consent = get_consent(session).model_dump(mode="json")
    except Exception:  # noqa: BLE001 — unreadable consent withholds, it never crashes a fill
        logger.exception("eeo consent could not be read; withholding EEO answers")
        consent = None
    return withhold_unconsented(autofill_profile.get_profile(session), consent)
