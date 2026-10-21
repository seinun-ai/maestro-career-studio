"""Autofill profile: preset answers for job-application forms.

A single JSON object (personal details, work authorization, EEO/voluntary
disclosures, preferences, custom Q&A pairs) stored as a file-mirrored text
setting (settings/autofill.json). Consumed by the browser extension to fill
application forms and by the Settings page for editing. The shape is
intentionally loose — the extension treats every field as optional.

`work_auth` is the one namespace with a typed reader (`get_work_auth`), because
its answers are knockout answers. Migration state: SYSTEM.md §13
`autofill-work-auth-shape`.

**Work-permit answers are per country** (owner decision D9): `work_auth_by_country`
maps a MARKET key ("UK", the market setting's own key, not the ISO "GB") to that
country's answers. A profile from before holds one `work_auth`: it is the home
market's, mapped when read and kept as written until the user saves (the veteran
precedent below), or until the home moves, which first pins it to the home it was
read as (`pin_legacy_work_auth`). What a read returns carries both:
`work_auth_by_country`, and `work_auth` as the home market's set, for the editors
and the Companion's pause row that know one set. Which set a form gets is `autofill_country`'s rule. Migration
state: SYSTEM.md §13 `autofill-work-auth-by-country`.
"""

import json
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.schemas.autofill_profile import WorkAuth
from app.services import text_settings

AUTOFILL_KEY = "autofill_profile"
AUTOFILL_FILE = "autofill.json"
WORK_AUTH = "work_auth"
BY_COUNTRY = "work_auth_by_country"

# A profile is "new shape" if it carries ANY typed key. Detecting on one or two
# chosen keys would send a profile holding only `sponsorship_now` down the
# legacy branch, which reads neither typed key — discarding a knockout answer
# the user did supply.
_TYPED_WORK_AUTH_KEYS = frozenset(WorkAuth.model_fields)


# Veteran status was "not a PROTECTED veteran" / "a veteran", and is now one Yes/No question (owner,
# 2026-10-14). The profile is a JSON text setting, so the old values are mapped when it is READ, never
# migrated: the row, its file mirror, a profile synced from a peer that has not updated and an older
# Settings page's save all land in the same text, and every reader gets the new words. What is stored
# stays as written until the user saves, so a peer that has not updated reads its own old values.
#
# `veteran` is a Yes. `not_veteran` is NOT a No: "not a protected veteran" is true of a veteran who is
# not protected, so it reads as unanswered, and the profile says so under `stale_answers` so Settings asks
# the question again. The marker is DURABLE: a save that does not carry the veteran answer (the pause row
# writes the profile back without it) keeps it, and only an explicit `eeo.veteran_status` clears it.
STALE_KEY = "stale_answers"
STALE_VETERAN = "eeo.veteran_status"
_LEGACY_YES = "veteran"
_LEGACY_NOT_PROTECTED = "not_veteran"


def _answered_veteran(data: dict[str, Any]) -> bool:
    eeo = data.get("eeo")
    value = eeo.get("veteran_status") if isinstance(eeo, dict) else None
    return isinstance(value, str) and bool(value.strip())


def _marks_veteran_stale(data: dict[str, Any]) -> bool:
    """Whether `data` says the veteran question must be asked again: the legacy answer, or the marker."""
    eeo = data.get("eeo")
    legacy = isinstance(eeo, dict) and eeo.get("veteran_status") == _LEGACY_NOT_PROTECTED
    listed = data.get(STALE_KEY)
    return legacy or (isinstance(listed, list) and STALE_VETERAN in listed)


def _with_current_words(data: dict[str, Any]) -> dict[str, Any]:
    stale = _marks_veteran_stale(data)
    data = {k: v for k, v in data.items() if k != STALE_KEY}
    eeo = data.get("eeo")
    old = eeo.get("veteran_status") if isinstance(eeo, dict) else None
    if old == _LEGACY_YES:
        return {**data, "eeo": {**eeo, "veteran_status": "yes"}}
    if old == _LEGACY_NOT_PROTECTED:
        data = {**data, "eeo": {k: v for k, v in eeo.items() if k != "veteran_status"}}
    return {**data, STALE_KEY: [STALE_VETERAN]} if stale and not _answered_veteran(data) else data


def work_auth_entries(profile: Any, home: str | None) -> dict[str, dict[str, Any]]:
    """Each market's raw work-permit answers, keyed by market ("UK"): `work_auth_by_country`'s
    entries (an entry that is not an object is no answers), and a legacy top-level `work_auth`
    as the home market's when it has none of its own. Copies: a caller may change them."""
    stored = profile.get(BY_COUNTRY) if isinstance(profile, dict) else None
    entries = {
        str(key).strip().upper(): dict(value)
        for key, value in (stored.items() if isinstance(stored, dict) else ())
        if isinstance(value, dict) and str(key).strip()
    }
    legacy = profile.get(WORK_AUTH) if isinstance(profile, dict) else None
    if home and home not in entries and isinstance(legacy, dict):
        entries[home] = dict(legacy)
    return entries


def _with_work_auth_by_country(data: dict[str, Any], home: str | None) -> dict[str, Any]:
    """The read view: every market's answers under `work_auth_by_country`, and `work_auth` as the
    home market's (absent when it has none)."""
    entries = work_auth_entries(data, home)
    view = {k: v for k, v in data.items() if k not in (WORK_AUTH, BY_COUNTRY)}
    if entries:
        view[BY_COUNTRY] = entries
    if home in entries:
        view[WORK_AUTH] = dict(entries[home])
    return view


def _as_stored(profile: dict[str, Any], before: dict[str, Any], home: str | None) -> dict[str, Any]:
    """What a save stores: `work_auth_by_country` alone. A client that knows one set (the Settings
    editor, the Companion's pause row, a peer that has not updated) edits `work_auth`, the home set it
    was served: when that differs from what the store would serve now (`before`), or the client sent
    no home entry, it is the home market's new answers. Otherwise the per-country map stands, so a
    client that knows every country leaves `work_auth` as served, or out."""
    entries = work_auth_entries({BY_COUNTRY: profile.get(BY_COUNTRY)}, None)
    single = profile.get(WORK_AUTH)
    if home and isinstance(single, dict) and (single != before.get(WORK_AUTH) or home not in entries):
        entries[home] = dict(single)
    stored = {k: v for k, v in profile.items() if k not in (WORK_AUTH, BY_COUNTRY)}
    if entries:
        stored[BY_COUNTRY] = entries
    return stored


def _home(session: Session | None) -> str:
    """Where the user lives: the market whose answers a legacy `work_auth` holds. Non-mutating."""
    from app.services import market_settings

    return market_settings.peek_market(session).home


def _parse_profile(raw: str, home: str | None = None) -> dict[str, Any]:
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return _with_work_auth_by_country(_with_current_words(data), home) if isinstance(data, dict) else {}


def _parse_stored(raw: str) -> dict[str, Any]:
    """The stored text as it is, old words and all (`_parse_profile` maps them)."""
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def pin_legacy_work_auth(market: str, session: Session | None = None) -> None:
    """Before "You live in" moves away from `market` (`market_settings.set_market`): a stored top-level
    `work_auth`, the one set from before per-country answers, is read as the home market's, and nothing in
    it says which country it was for, so the next home must not inherit it. It is pinned to `market`, the
    home it has been read as: into that market's entry when it has none; when it has one, the old set was
    read for no country and goes. Everything else stays as written (old words are mapped when read). No
    legacy set, no write. A profile row: the flush guard refuses this where the move is refused too."""
    stored = _parse_stored(text_settings.peek_text(AUTOFILL_KEY, AUTOFILL_FILE, session))
    legacy = stored.get(WORK_AUTH)
    if not isinstance(legacy, dict):
        return
    key = market.strip().upper()
    by_country = stored.get(BY_COUNTRY) if isinstance(stored.get(BY_COUNTRY), dict) else {}
    pinned = {k: v for k, v in stored.items() if k != WORK_AUTH}
    if key not in work_auth_entries({BY_COUNTRY: by_country}, None):
        pinned[BY_COUNTRY] = {**by_country, key: dict(legacy)}
    text_settings.set_text(AUTOFILL_KEY, AUTOFILL_FILE, json.dumps(pinned, indent=2, sort_keys=True), session)


def get_profile(session: Session | None = None) -> dict[str, Any]:
    return _parse_profile(text_settings.get_text(AUTOFILL_KEY, AUTOFILL_FILE, session), _home(session))


def peek_profile(session: Session | None = None) -> dict[str, Any]:
    return _parse_profile(text_settings.peek_text(AUTOFILL_KEY, AUTOFILL_FILE, session), _home(session))


def set_profile(profile: dict[str, Any], session: Session | None = None) -> dict[str, Any]:
    """Store `profile` and return it as a read serves it (`work_auth` = the home set)."""
    raw = text_settings.peek_text(AUTOFILL_KEY, AUTOFILL_FILE, session)
    home = _home(session)
    # The hint outlasts any save that does not answer the question: whatever is stored, or the client's
    # own marker, keeps it; an explicit veteran answer clears it.
    stale = _marks_veteran_stale(profile) or _marks_veteran_stale(_parse_stored(raw))
    profile = _as_stored({k: v for k, v in profile.items() if k != STALE_KEY}, _parse_profile(raw, home), home)
    if stale and not _answered_veteran(profile):
        profile = {**profile, STALE_KEY: [STALE_VETERAN]}
    text_settings.set_text(
        AUTOFILL_KEY, AUTOFILL_FILE, json.dumps(profile, indent=2, sort_keys=True), session
    )
    return _with_work_auth_by_country(profile, home)


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


def work_auth_from_profile(profile: dict[str, Any]) -> WorkAuth:
    """Read `profile["work_auth"]` (one country's set), tolerating the pre-2026-07 two-boolean shape.

    Dual-read, not a rewrite-on-load: the extension ships independently and an
    older panel may still POST the legacy shape. Cutting the legacy branch
    follows the `autofill-education-shape` precedent in SYSTEM.md §13 — frontend
    first, extension one release later.
    """
    return typed_work_auth(profile.get(WORK_AUTH))


def typed_work_auth(raw: Any) -> WorkAuth:
    """One country's raw answers as `WorkAuth`: the typed keys, else the legacy pair."""
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


def get_work_auth(session: Session | None = None, market: str | None = None) -> WorkAuth:
    """One market's answers ("UK"); `market` None is the home market's, the profile's own set (the
    job-search brief). A FORM's answer is `autofill_country.work_auth_for`, where no country is
    no answer."""
    return _work_auth_of(get_profile(session), market)


def peek_work_auth(session: Session | None = None, market: str | None = None) -> WorkAuth:
    return _work_auth_of(peek_profile(session), market)


def _work_auth_of(view: dict[str, Any], market: str | None) -> WorkAuth:
    if market is None:
        return work_auth_from_profile(view)
    return typed_work_auth((view.get(BY_COUNTRY) or {}).get(market.strip().upper()))


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
