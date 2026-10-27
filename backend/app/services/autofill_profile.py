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
`work_auth_by_country`, and `work_auth` as the home market's set for a client that
knows one set, with `work_auth_market` naming the market that set is for; a save
folds an edited `work_auth` into the market its client names (`_as_stored`). Which
set a form gets is `autofill_country`'s rule. Migration state: SYSTEM.md §13
`autofill-work-auth-by-country`.
"""

import json
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.schemas.autofill_profile import WorkAuth
from app.services import markets, text_settings

AUTOFILL_KEY = "autofill_profile"
AUTOFILL_FILE = "autofill.json"
WORK_AUTH = "work_auth"
BY_COUNTRY = "work_auth_by_country"
# The market the `work_auth` beside it is for: served on a read, never stored.
WORK_AUTH_MARKET = "work_auth_market"

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
    """The read view: every market's answers under `work_auth_by_country`, `work_auth` as the home
    market's (absent when it has none), and `work_auth_market` naming the home whenever the profile
    holds any work-permit answers, so a client that adds or edits the one set says whose it is."""
    entries = work_auth_entries(data, home)
    view = {k: v for k, v in data.items() if k not in (WORK_AUTH, BY_COUNTRY, WORK_AUTH_MARKET)}
    if entries:
        view[BY_COUNTRY] = entries
        if home:
            view[WORK_AUTH_MARKET] = home
    if home in entries:
        view[WORK_AUTH] = dict(entries[home])
    return view


def _sent_entries(sent: Any) -> dict[str, dict[str, Any] | None]:
    """A save's `work_auth_by_country` by market ("uk " is "UK"): an object is that market's answers,
    anything else (null) removes them."""
    if not isinstance(sent, dict):
        return {}
    return {
        str(key).strip().upper(): dict(value) if isinstance(value, dict) else None
        for key, value in sent.items()
        if str(key).strip()
    }


def _one_set_market(profile: dict[str, Any], answered: set[str], home: str | None) -> str | None:
    """The market a save's one `work_auth` set is for, or None when that cannot be told.

    The market the client names (`work_auth_market`, as a read served it), when it is one this store
    knows; a marker that is null (a /context profile for a job with no country), empty or unknown names
    none. A client from before the marker names nothing: its set is the home's, as it always was, but
    only while no other market has answers (`answered`); once one does, the set could be either and
    the stored answers stand. Never a guess."""
    if WORK_AUTH_MARKET in profile:
        mark = profile[WORK_AUTH_MARKET]
        key = mark.strip().upper() if isinstance(mark, str) else ""
        return key if markets.is_supported(key) else None
    return home if home and not (answered - {home}) else None


def _as_stored(profile: dict[str, Any], before: dict[str, Any], home: str | None) -> dict[str, Any]:
    """What a save stores: `work_auth_by_country` alone, and never one market's answers written over
    another's.

    - **The map is merged by market.** A market the save sends replaces that market's answers (sent
      as null, they go); a market it leaves out, or a save with no map at all, keeps its stored
      answers: a client that does not know a country cannot have meant to remove them.
    - **The one set goes to the market it names.** A client that knows one set (the Companion's pause
      row, an older page) edits `work_auth`, the set a read served beside `work_auth_market`. When it
      differs from that market's stored answers (`before`), and the client's own map entry for that
      market is not an edit of its own, it is that market's new answers (`_one_set_market`; no market,
      no fold). So a client served under the old home, saving after a move, writes the old home's
      entry, and a client that knows every country leaves `work_auth` as served, or out."""
    stored = work_auth_entries(before, None)
    sent = _sent_entries(profile.get(BY_COUNTRY))
    entries = dict(stored)
    for market, answers in sent.items():
        if answers is None:
            entries.pop(market, None)
        else:
            entries[market] = answers
    single = profile.get(WORK_AUTH)
    if isinstance(single, dict):
        answered = {m for m, answers in {**stored, **sent}.items() if answers}
        market = _one_set_market(profile, answered, home)
        unedited_in_map = sent.get(market, stored.get(market)) == stored.get(market)
        if market and single != stored.get(market) and unedited_in_map:
            entries[market] = dict(single)
    out = {k: v for k, v in profile.items() if k not in (WORK_AUTH, BY_COUNTRY, WORK_AUTH_MARKET)}
    if entries:
        out[BY_COUNTRY] = entries
    return out


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


# The sections an agent's save writes (`PATCH /api/settings/autofill`, MCP `set_autofill_profile`). `eeo`
# is not one: a diversity answer is the user's own, given in Profile (SYSTEM.md
# {#inv-eeo-standing-consent}); the MCP tool has no field for it, its client refuses it, and so does this.
ANSWER_SECTIONS = ("personal", "eligibility", "preferences")
LIST_SECTIONS = ("education", "languages", "custom")
AGENT_SECTIONS = frozenset({*ANSWER_SECTIONS, *LIST_SECTIONS, BY_COUNTRY})
# The Companion's learn store (SYSTEM.md {#inv-one-label-pattern-table}): an agent's save upserts it.
CUSTOM = "custom"


def _question_key(entry: Any) -> tuple[str, Any, Any] | None:
    """Which saved answer `entry` is, as the Companion tells them apart (`panel/actions/pause.js`
    `customRowAt`/`scopeKey`): its question under `ns.normLabel` (lower case, runs of spaces as one,
    trimmed; `shared/profile-fields.js`), with the company or city it is held for. None when it has
    no question to key on."""
    question = entry.get("question") if isinstance(entry, dict) else None
    words = " ".join(question.lower().split()) if isinstance(question, str) else ""
    return (words, entry.get("only_for"), entry.get("only_for_kind")) if words else None


def _upserted_custom(stored: Any, given: list[Any]) -> list[Any]:
    """The saved answers with `given` laid over them: an entry whose question (and scope) matches a
    stored one replaces it in place, any other is added at the end, and a stored answer `given` does
    not name stays. So an answer the Companion learned after the agent's read is never erased, and
    an agent cannot remove a saved answer (that stays the user's, in Profile)."""
    rows = list(stored) if isinstance(stored, list) else []
    for entry in given:
        key = _question_key(entry)
        at = next((i for i, row in enumerate(rows) if key is not None and _question_key(row) == key), None)
        if at is None:
            rows.append(entry)
        else:
            rows[at] = entry
    return rows


def _merged_answers(stored: Any, given: dict[str, Any]) -> dict[str, Any]:
    """`stored` with `given` laid over it key by key; a None removes that key."""
    merged = dict(stored) if isinstance(stored, dict) else {}
    for key, value in given.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged


def merged_profile(stored: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    """The whole profile an agent's save stores: `stored` (as a read serves it) with the sections
    `changes` names merged in. Answer sections merge key by key, saved answers (`custom`) upsert by
    question (`_upserted_custom`), education and languages replace the stored list, and work permits
    go per country, each market key read as `set_profile` stores it (a None country is passed on as
    None, which `set_profile` takes as removing its answers; a country left out keeps its stored
    answers there). The read view's one-set projection
    is never sent back, so no answer is folded into another country's."""
    profile = {k: v for k, v in stored.items() if k not in (WORK_AUTH, WORK_AUTH_MARKET)}
    stored_permits = stored.get(BY_COUNTRY) if isinstance(stored.get(BY_COUNTRY), dict) else {}
    for section, given in changes.items():
        if section in ANSWER_SECTIONS:
            profile[section] = _merged_answers(profile.get(section), given)
        elif section == CUSTOM:
            profile[CUSTOM] = _upserted_custom(profile.get(CUSTOM), given)
        elif section in LIST_SECTIONS:
            profile[section] = list(given)
        elif section == BY_COUNTRY:
            profile[BY_COUNTRY] = {  # keyed as stored ("uk " is "UK"), so a market's answers are found
                market: None if answers is None else _merged_answers(stored_permits.get(market), answers)
                for market, answers in _sent_entries(given).items()
            }
    return profile


def _refusal(changes: dict[str, Any]) -> str | None:
    """Why an agent's save is refused before anything is read, or None: a section it does not write,
    or one of the wrong shape (the merge would otherwise fail halfway or store a non-answer)."""
    refused = sorted(set(changes) - AGENT_SECTIONS)
    if refused:
        return (
            f"Not written by an agent's save: {', '.join(refused)}. The writable sections are "
            f"{', '.join(sorted(AGENT_SECTIONS))}; diversity (eeo) answers are the user's, in Profile."
        )
    for section, given in changes.items():
        if section in ANSWER_SECTIONS and not isinstance(given, dict):
            return f"{section} takes an object of answers."
        if section in LIST_SECTIONS and not isinstance(given, list):
            return f"{section} takes a list."
        if section == BY_COUNTRY and not (
            isinstance(given, dict) and all(a is None or isinstance(a, dict) for a in given.values())
        ):
            return f"{BY_COUNTRY} takes an object of answers (or null) per market."
    return None


def patch_profile(changes: dict[str, Any], session: Session) -> dict[str, Any]:
    """An agent's save: the profile stored now with `changes` merged in (`merged_profile`), read,
    merged and written as one transaction (`text_settings.one_commit`), so an answer another writer
    saved before this call (a Companion learn, a web edit) is kept, and none can land between the
    read and the write. Returns the profile as a read serves it. ValueError names a refused section
    before anything is read."""
    refusal = _refusal(changes)
    if refusal:
        raise ValueError(refusal)
    with text_settings.one_commit(session):
        saved = set_profile(merged_profile(peek_profile(session), changes), session)
    return saved


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
