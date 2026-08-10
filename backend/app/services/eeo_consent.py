"""EEO standing-consent storage: Setting row + file mirror.

A hand-edited file that fails validation reads as defaults. Values here are
consent metadata only — never EEO answers.
"""

import json
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.schemas.eeo_consent import CURRENT_POLICY_VERSION, EeoConsent
from app.services import text_settings

EEO_CONSENT_KEY = "eeo_consent"
EEO_CONSENT_FILE = "eeo_consent.json"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_consent(raw: str) -> EeoConsent:
    if not raw.strip():
        return EeoConsent()
    try:
        return EeoConsent.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError):
        return EeoConsent()


def get_consent(session: Session | None = None) -> EeoConsent:
    return _parse_consent(
        text_settings.get_text(EEO_CONSENT_KEY, EEO_CONSENT_FILE, session)
    )


def peek_consent(session: Session | None = None) -> EeoConsent:
    return _parse_consent(
        text_settings.peek_text(EEO_CONSENT_KEY, EEO_CONSENT_FILE, session)
    )


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
    text_settings.set_text(
        EEO_CONSENT_KEY,
        EEO_CONSENT_FILE,
        consent.model_dump_json(indent=2),
        session,
    )
    return consent
