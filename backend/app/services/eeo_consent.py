"""EEO standing-consent storage.

Values here are consent metadata only — never EEO answers.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.eeo_consent import (
    CONSENT_FORMS_MIN_POLICY_VERSION,
    CURRENT_POLICY_VERSION,
    EeoConsent,
    policy_at_least,
)
from app.services.json_settings import JsonSetting

logger = logging.getLogger(__name__)


def _lapse_stale_agreement(payload: Any) -> Any:
    """Serve an agreement given under an older policy as NOT granted.

    The stored record keeps what the user said (so the lapse stays visible
    until they answer again); the settings GET and the fill context the
    extension reads both serve `consent_forms` false. (The MCP client drops
    `consent_forms` from that context altogether.) Only `consent_forms` has a
    policy floor; `enabled` is left alone."""
    if not isinstance(payload, dict):
        return payload
    lapsed = payload.get("consent_forms") is True and not policy_at_least(
        payload.get("policy_version"), CONSENT_FORMS_MIN_POLICY_VERSION
    )
    served = {**payload, "consent_forms_lapsed": lapsed}
    if lapsed:
        served["consent_forms"] = False
    return served


class _EeoConsentSetting(JsonSetting[EeoConsent]):
    def migrate(self, payload: Any) -> Any:
        return _lapse_stale_agreement(payload)


EEO_CONSENT = _EeoConsentSetting("eeo_consent", "eeo_consent.json", EeoConsent)
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
    """Persist standing consent. The server owns the audit stamp.

    `acknowledged_at` and `policy_version` decide whether `consent_forms` is
    granted, so neither comes from the client: a permission turning ON stamps
    the server's time and the current policy; anything else keeps the stored
    stamp. `consent_forms` turns on only on its own yes — a null stamp, no
    diversity change riding with it, and `agreed_policy` naming the current
    policy. Anything short of that is HELD at the served value, never refused,
    and turning a permission off always goes through. The value returned is
    the one a reader will see.
    """
    stored = EEO_CONSENT.get(session)  # as served: a lapsed agreement reads off
    consent_forms = consent.consent_forms and (
        stored.consent_forms
        or (
            consent.acknowledged_at is None
            and consent.enabled == stored.enabled
            and consent.agreed_policy == CURRENT_POLICY_VERSION
        )
    )
    turned_on = (consent.enabled and not stored.enabled) or (
        consent_forms and not stored.consent_forms
    )
    record = EeoConsent(
        enabled=consent.enabled,
        consent_forms=consent_forms,
        acknowledged_at=_now_iso() if turned_on else stored.acknowledged_at,
        policy_version=CURRENT_POLICY_VERSION if turned_on else stored.policy_version,
    )
    EEO_CONSENT.set(record, session)
    if session is not None and not record.enabled:
        # inv-filled-answers-local: withdrawn consent clears stored EEO answers. Imported here
        # because the receipt service imports this module for its gate.
        from app.services import filled_answers

        filled_answers.clear_eeo_answers(session)
    return EeoConsent.model_validate(_lapse_stale_agreement(record.model_dump()))


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
