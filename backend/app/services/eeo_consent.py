"""EEO standing-consent storage.

Values here are consent metadata only — never EEO answers.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.schemas.eeo_consent import CURRENT_POLICY_VERSION, EeoConsent
from app.services.json_settings import JsonSetting

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
