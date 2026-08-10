"""Autofill profile: preset answers for job-application forms.

A single JSON object (personal details, work authorization, EEO/voluntary
disclosures, preferences, custom Q&A pairs) stored as a file-mirrored text
setting (settings/autofill.json). Consumed by the browser extension to fill
application forms and by the Settings page for editing. The shape is
intentionally loose — the extension treats every field as optional.

`work_auth` is the one namespace with a typed reader (`get_work_auth`), because
its answers are knockout answers. Migration state: SYSTEM.md §13
`autofill-work-auth-shape`.
"""

import json
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.schemas.autofill_profile import WorkAuth
from app.services import text_settings

AUTOFILL_KEY = "autofill_profile"
AUTOFILL_FILE = "autofill.json"

# A profile is "new shape" if it carries ANY typed key. Detecting on one or two
# chosen keys would send a profile holding only `sponsorship_now` down the
# legacy branch, which reads neither typed key — discarding a knockout answer
# the user did supply.
_TYPED_WORK_AUTH_KEYS = frozenset(WorkAuth.model_fields)


def _parse_profile(raw: str) -> dict[str, Any]:
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def get_profile(session: Session | None = None) -> dict[str, Any]:
    return _parse_profile(text_settings.get_text(AUTOFILL_KEY, AUTOFILL_FILE, session))


def peek_profile(session: Session | None = None) -> dict[str, Any]:
    return _parse_profile(text_settings.peek_text(AUTOFILL_KEY, AUTOFILL_FILE, session))


def set_profile(profile: dict[str, Any], session: Session | None = None) -> dict[str, Any]:
    text_settings.set_text(
        AUTOFILL_KEY, AUTOFILL_FILE, json.dumps(profile, indent=2, sort_keys=True), session
    )
    return profile


def _usable_answers_only(values: dict[str, Any]) -> WorkAuth:
    """Validate field by field so one unusable answer cannot blank the others.

    settings/autofill.json is hand-editable and `PUT /api/settings/autofill`
    takes an untyped dict, so any JSON can reach here — a blank select (""), a
    near-miss status ("OPT"), a year written as a number. A value this schema
    cannot interpret IS an unknown answer, so dropping it to None lands on the
    same "ask the user" outcome a missing key already gets. Raising instead
    would take down every caller over one bad key; coercing would answer a
    knockout question the profile never actually answered.
    """
    usable: dict[str, Any] = {}
    for name in WorkAuth.model_fields:
        value = values.get(name)
        try:
            WorkAuth.model_validate({name: value})
        except ValidationError:
            continue
        usable[name] = value
    # Every surviving value validated on its own and no field constrains
    # another, so this cannot raise.
    return WorkAuth.model_validate(usable)


def _work_auth_from_profile(profile: dict[str, Any]) -> WorkAuth:
    """Read work authorization, tolerating the pre-2026-07 two-boolean shape.

    Dual-read, not a rewrite-on-load: the extension ships independently and an
    older panel may still POST the legacy shape. Cutting the legacy branch
    follows the `autofill-education-shape` precedent in SYSTEM.md §13 — frontend
    first, extension one release later.
    """
    raw = profile.get("work_auth")
    if not isinstance(raw, dict):
        # Loose JSON: `work_auth` may be absent, null, or hand-edited to a
        # string. No answers, rather than an AttributeError mid-fill.
        return WorkAuth()
    if _TYPED_WORK_AUTH_KEYS & raw.keys():
        return _usable_answers_only(raw)
    return _usable_answers_only(
        {
            "authorized_now": raw.get("authorized_to_work"),
            # The legacy flag was never time-scoped. Map it to the FUTURE half,
            # which is the question employers gate on, and leave `now` unknown
            # rather than inventing it.
            "sponsorship_future": raw.get("requires_sponsorship"),
        }
    )


def get_work_auth(session: Session | None = None) -> WorkAuth:
    return _work_auth_from_profile(get_profile(session))


def peek_work_auth(session: Session | None = None) -> WorkAuth:
    return _work_auth_from_profile(peek_profile(session))


def _personal_str(personal: dict[str, Any], key: str) -> str | None:
    value = personal.get(key)
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def canonical_identity_from_profile(profile: dict[str, Any] | None) -> dict[str, str | None]:
    """Map stored autofill personal fields to the MCP identity block.

    Sourced only from ``personal.first_name`` / ``last_name`` / ``preferred_name``
    (the Settings autofill keys). Never invents values from resume or ATS parses.
    """
    personal = profile.get("personal") if isinstance(profile, dict) else None
    if not isinstance(personal, dict):
        personal = {}
    return {
        "legal_first": _personal_str(personal, "first_name"),
        "legal_last": _personal_str(personal, "last_name"),
        "preferred": _personal_str(personal, "preferred_name"),
    }
