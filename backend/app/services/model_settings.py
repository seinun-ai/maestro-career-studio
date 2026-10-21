import json
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models.setting import Setting
from app.services.llm_providers.registry import PROVIDERS


FAST_MODEL_KEY = "llm.fast_model"
SMART_MODEL_KEY = "llm.smart_model"
CHAT_MODEL_KEY = "llm.chat_model"
EXTRA_MODELS_KEY = "llm.extra_models"
REASONING_MODEL_KEY = "llm.reasoning_model"
# "Use recommended models": no row is off; "auto" uses the first provider (PROVIDERS order) with a key
# and a set; a provider name uses that provider's set while its key is there.
RECOMMENDED_KEY = "llm.recommended_models"
RECOMMENDED_AUTO = "auto"
# The four roles, as the recommended sets name them ("assistant" is the chat model).
ROLES = ("fast", "smart", "assistant", "reasoning")
_RECOMMENDED_FILE = Path(__file__).parent / "data" / "recommended_models.yaml"


@dataclass(frozen=True)
class ModelOption:
    id: str
    label: str
    provider: str
    tier: str


MODEL_OPTIONS = [
    # Benchmarked 2026-08 (Langfuse-traced, real JDs): its extractions miss
    # requirements the other two catch, which quietly inflates base ATS
    # scores. Kept for existing installs; no longer a recommended default.
    ModelOption("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite", "gemini", "fast"),
    # The Gemini-key-only "fast" profile: near flash-lite speed with far
    # better extraction coverage. Promo pricing doubles 2027-01-01.
    ModelOption("gemini-3.7-flash", "Gemini 3.7 Flash", "gemini", "fast"),
    # GPT-5.6 family (released 2026-07-09): 1.05M context, tools + streaming.
    # DEFAULT for every tier (same 2026-08 benchmark): the most complete
    # extraction measured and the cheapest per application; the slowest.
    ModelOption("gpt-5.6-luna", "OpenAI GPT-5.6 Luna", "openai", "smart"),
    # The strong OpenAI model (2026-10 freshness check: $2/$10 per MTok) and the small cheap one. Listed for the
    # Reasoning model (default and picker) and for a key that wants them; never assigned to the other three roles.
    ModelOption("gpt-6.1-sol", "OpenAI GPT-6.1 Sol", "openai", "smart"),
    ModelOption("gpt-6-luna", "OpenAI GPT-6 Luna", "openai", "fast"),
    # Claude 5.5 family: listed so a Claude key has models to pick; never
    # assigned to a role (no auto-pick). Fast Claude tier:
    ModelOption("claude-haiku-5-5", "Claude Haiku 5.5", "anthropic", "fast"),
    # Balanced Claude tier: listed for a Claude key, never a default.
    ModelOption("claude-sonnet-5-5", "Claude Sonnet 5.5", "anthropic", "smart"),
    # Most capable Claude tier: listed for a Claude key, never a default.
    ModelOption("claude-opus-5-5", "Claude Opus 5.5", "anthropic", "smart"),
]

VALID_MODEL_IDS = {option.id for option in MODEL_OPTIONS}


def _get_value(session: Session, key: str, default: str) -> str:
    existing = session.scalar(select(Setting).where(Setting.key == key))
    return existing.value if existing is not None and existing.value else default


def _set_value(session: Session, key: str, value: str) -> str:
    """Write a model-id row. Validation lives in `set_models`, NOT here.

    This used to re-check VALID_MODEL_IDS, so the allowlist was enforced in two
    places. When `set_models` learned to accept free-text ids for a custom
    endpoint, this copy kept rejecting them and a local model was still
    unselectable — the failure only showed up against a real Ollama server.
    One invariant, one place.
    """
    existing = session.scalar(select(Setting).where(Setting.key == key))
    if existing is None:
        session.add(Setting(key=key, value=value))
    else:
        existing.value = value
    session.commit()
    return value


# The role getters below are the ONE place a role's model id is read (every caller, the registry's
# routing included, starts from them): "Use recommended models" changes what they return, it adds no
# second resolver. `own_models` is what they return with it off.


def get_fast_model(session: Session | None = None) -> str:
    if session is None:
        with SessionLocal() as owned:
            return get_fast_model(owned)
    return _recommended(session, "fast") or _get_value(session, FAST_MODEL_KEY, settings.fast_model)


def get_smart_model(session: Session | None = None) -> str:
    if session is None:
        with SessionLocal() as owned:
            return get_smart_model(owned)
    return _recommended(session, "smart") or _get_value(session, SMART_MODEL_KEY, settings.smart_model)


def get_chat_model(session: Session | None = None) -> str:
    if session is None:
        with SessionLocal() as owned:
            return get_chat_model(owned)
    return _recommended(session, "assistant") or _get_value(session, CHAT_MODEL_KEY, settings.chat_model)


def own_models(session: Session) -> dict[str, str]:
    """Your own pick per role (else the install's default), whatever "recommended" says: what the
    roles answer once it is off, and what a settings save writes back when it sends no role."""
    return {
        "fast": _get_value(session, FAST_MODEL_KEY, settings.fast_model),
        "smart": _get_value(session, SMART_MODEL_KEY, settings.smart_model),
        "assistant": _get_value(session, CHAT_MODEL_KEY, settings.chat_model),
        "reasoning": _get_raw_value(session, REASONING_MODEL_KEY) or default_reasoning_model(session),
    }


@lru_cache(maxsize=1)
def recommended_sets() -> dict[str, dict[str, str]]:
    """provider -> {role: model id} from data/recommended_models.yaml; a provider with no set is
    absent. tests/test_model_settings.py holds every id to the catalog and its provider."""
    raw = yaml.safe_load(_RECOMMENDED_FILE.read_text(encoding="utf-8")) or {}
    return {
        provider: {role: str(roles[role]) for role in ROLES}
        for provider, roles in (raw.get("providers") or {}).items()
        if isinstance(roles, dict) and all(roles.get(role) for role in ROLES)
    }


def _has_key(session: Session, provider: str) -> bool:
    """A stored or environment key (the env key is the fallback, as `llm`'s key getters read it). An
    OpenAI key sent to your own server is that server's, so OpenAI's set never applies to it."""
    if provider == "openai" and using_custom_endpoint(session):
        return False
    return bool(get_api_key(provider, session) or getattr(settings, f"{provider}_api_key", ""))


def get_recommended(session: Session) -> tuple[bool, str | None]:
    """(on, the provider you chose or None for the first with a key)."""
    raw = _get_raw_value(session, RECOMMENDED_KEY)
    if raw is None:
        return False, None
    return True, (None if raw == RECOMMENDED_AUTO else raw)


def recommended_provider(session: Session) -> str | None:
    """The provider whose set the roles answer: the one you chose while its key is there, else the
    first in PROVIDERS with a key and a set; None while recommended is off or no such provider exists."""
    on, chosen = get_recommended(session)
    if not on:
        return None
    sets = recommended_sets()
    keyed = [p for p in PROVIDERS if p in sets and _has_key(session, p)]
    if chosen in keyed:
        return chosen
    return keyed[0] if keyed else None


def _recommended(session: Session, role: str) -> str | None:
    provider = recommended_provider(session)
    return recommended_sets()[provider][role] if provider else None


def set_recommended(session: Session, *, on: bool, provider: str | None = None) -> None:
    """On with a provider (one that has a set) or None for the first with a key; off forgets the
    choice. Your own picks are never touched."""
    if not on:
        _set_raw_value(session, RECOMMENDED_KEY, None)
        return
    if provider is not None and provider not in recommended_sets():
        raise ValueError(f"There are no recommended models for {provider}.")
    _set_raw_value(session, RECOMMENDED_KEY, provider or RECOMMENDED_AUTO)


# The models strong enough to reason over a stuck page, and each provider's one. NOT the catalog's `tier`:
# `gpt-5.6-luna` is tagged "smart" and is the small cheap OpenAI model.
STRONG_MODELS = frozenset({"claude-sonnet-5-5", "claude-opus-5-5", "gpt-6.1-sol"})
STRONG_BY_PROVIDER = {"anthropic": "claude-sonnet-5-5", "openai": "gpt-6.1-sol"}


API_KEY_SETTINGS = {
    "openai": "llm.openai_api_key",
    "gemini": "llm.gemini_api_key",
    "anthropic": "llm.anthropic_api_key",
    "openrouter": "llm.openrouter_api_key",
}
OPENAI_API_KEY_KEY = API_KEY_SETTINGS["openai"]   # kept: imported elsewhere
GEMINI_API_KEY_KEY = API_KEY_SETTINGS["gemini"]
BASE_URL_KEY = "llm.base_url"
# auto | on | off — see llm._json_mode_supported.
JSON_MODE_KEY = "llm.json_mode"


def _get_raw_value(session: Session, key: str) -> str | None:
    existing = session.scalar(select(Setting).where(Setting.key == key))
    return existing.value if existing is not None and existing.value else None


def _set_raw_value(session: Session, key: str, value: str | None) -> str | None:
    existing = session.scalar(select(Setting).where(Setting.key == key))
    if existing is None:
        if value is not None and value != "":
            session.add(Setting(key=key, value=value))
            session.commit()
            return value
    else:
        if value is None or value == "":
            session.delete(existing)
            session.commit()
            return None
        else:
            existing.value = value
            session.commit()
            return value
    return None


def get_api_key(provider: str, session: Session | None = None) -> str | None:
    key = API_KEY_SETTINGS[provider]
    if session is None:
        with SessionLocal() as owned:
            return _get_raw_value(owned, key)
    return _get_raw_value(session, key)


def get_openai_api_key(session: Session | None = None) -> str | None:
    return get_api_key("openai", session)


def get_gemini_api_key(session: Session | None = None) -> str | None:
    return get_api_key("gemini", session)


def set_api_keys(session: Session, keys: dict[str, str | None]) -> None:
    """Patch: only the providers named in `keys` change; None or "" removes that key."""
    for provider, value in keys.items():
        _set_raw_value(session, API_KEY_SETTINGS[provider], (value or "").strip() or None)


def get_base_url(session: Session | None = None) -> str | None:
    if session is None:
        with SessionLocal() as owned:
            return _get_raw_value(owned, BASE_URL_KEY)
    return _get_raw_value(session, BASE_URL_KEY)


def get_json_mode(session: Session | None = None) -> str:
    if session is None:
        with SessionLocal() as owned:
            return _get_raw_value(owned, JSON_MODE_KEY) or "auto"
    return _get_raw_value(session, JSON_MODE_KEY) or "auto"


def set_base_url(session: Session, value: str | None) -> str | None:
    """Store the OpenAI-compatible endpoint, rejecting anything that is not http(s).

    This value decides where the stored API KEY is sent: `llm._client()` builds
    `OpenAI(api_key=..., base_url=...)`, so whoever controls this row controls
    where the user's credentials and resume text go. The endpoint is deliberately
    free-form (any Ollama/vLLM/LiteLLM host), so we cannot allowlist hosts — but
    we can refuse schemes that were never valid, which stops the field being used
    as a general-purpose sink.
    """
    return _set_raw_value(session, BASE_URL_KEY, _checked_http_url(value))


def _checked_http_url(value: str | None) -> str | None:
    cleaned = (value or "").strip() or None
    if cleaned is not None:
        parsed = urlparse(cleaned)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("Enter a full address that starts with http:// or https://.")
    return cleaned


JSON_MODES = ("auto", "on", "off")


def set_json_mode(session: Session, value: str | None) -> str | None:
    normalized = (value or "auto").strip().lower()
    if normalized not in JSON_MODES:
        raise ValueError(f"json_mode must be one of {', '.join(JSON_MODES)}")
    # "auto" is the default, so store nothing rather than a redundant row.
    return _set_raw_value(session, JSON_MODE_KEY, None if normalized == "auto" else normalized)


# Jev (TypeSafe AI) — the optional decision engine for the Companion's fill pass.
# Its own key: an OpenRouter or TypeSafe key is not the OpenAI key above.
JEV_API_KEY_KEY = "llm.jev_api_key"
JEV_BASE_URL_KEY = "llm.jev_base_url"
JEV_MODEL_KEY = "llm.jev_model"
AUTOFILL_ENGINE_KEY = "llm.autofill_engine"

JEV_DEFAULT_BASE_URL = "https://openrouter.ai/api"
# Pinned, not -latest: a model that changes under the user changes their fills.
JEV_DEFAULT_MODEL = "typesafe/jev-1.13"
AUTOFILL_ENGINES = ("fast", "jev")


def _read(session: Session | None, key: str) -> str | None:
    if session is None:
        with SessionLocal() as owned:
            return _get_raw_value(owned, key)
    return _get_raw_value(session, key)


def default_reasoning_model(session: Session | None = None) -> str:
    """The smart model when it is itself a strong model, else the strong one of its SEEDED provider (Anthropic,
    OpenAI), else the smart model (Gemini, OpenRouter, a user-added or unregistered id, a custom endpoint: those
    are the user's own choice and their catalog is not ours)."""
    if session is None:
        with SessionLocal() as owned:
            return default_reasoning_model(owned)
    smart = _get_value(session, SMART_MODEL_KEY, settings.smart_model)  # your own pick, not the set's
    if smart in STRONG_MODELS or using_custom_endpoint(session):
        return smart
    seeded = next((opt.provider for opt in MODEL_OPTIONS if opt.id == smart), None)
    return STRONG_BY_PROVIDER.get(seeded, smart)


def get_reasoning_model(session: Session | None = None) -> str:
    """The model the Companion's reasoning step calls (any catalog model; unset: the strong one)."""
    if session is None:
        with SessionLocal() as owned:
            return get_reasoning_model(owned)
    return _recommended(session, "reasoning") or own_models(session)["reasoning"]


def validate_reasoning_model(session: Session, value: str | None) -> None:
    value = (value or "").strip()
    if value and not using_custom_endpoint(session) and value not in usable_ids(session):
        raise ValueError(f"Unsupported model: {value}")


def set_reasoning_model(session: Session, value: str | None) -> None:
    """None or "" goes back to the default (no row)."""
    cleaned = (value or "").strip() or None
    validate_reasoning_model(session, cleaned)
    _set_raw_value(session, REASONING_MODEL_KEY, cleaned)


def get_jev_api_key(session: Session | None = None) -> str | None:
    return _read(session, JEV_API_KEY_KEY)


def get_jev_base_url(session: Session | None = None) -> str:
    return _read(session, JEV_BASE_URL_KEY) or JEV_DEFAULT_BASE_URL


def get_jev_model(session: Session | None = None) -> str:
    return _read(session, JEV_MODEL_KEY) or JEV_DEFAULT_MODEL


def get_autofill_engine(session: Session | None = None) -> str:
    """`jev` only while a key exists: a keyless Jev engine would fail every fill."""
    if _read(session, AUTOFILL_ENGINE_KEY) == "jev" and get_jev_api_key(session):
        return "jev"
    return "fast"


def set_jev_api_key(session: Session, value: str | None) -> str | None:
    return _set_raw_value(session, JEV_API_KEY_KEY, (value or "").strip() or None)


def set_jev_base_url(session: Session, value: str | None) -> str | None:
    """Same scheme rule as `set_base_url`, for the same reason: it decides where the key goes.

    A different HOST is a different company (OpenRouter ↔ TypeSafe), and a key
    for one is not a key for the other: keeping it would send it to the new host
    on the next fill. So a host change forgets the key, and with it Jev as the
    engine — the user adds the new provider's key."""
    cleaned = _checked_http_url(value)
    new_host = urlparse(cleaned or JEV_DEFAULT_BASE_URL).netloc.lower()
    if new_host != urlparse(get_jev_base_url(session)).netloc.lower():
        _set_raw_value(session, JEV_API_KEY_KEY, None)
        _set_raw_value(session, AUTOFILL_ENGINE_KEY, None)
    return _set_raw_value(session, JEV_BASE_URL_KEY, cleaned)


def set_jev_model(session: Session, value: str | None) -> str | None:
    return _set_raw_value(session, JEV_MODEL_KEY, (value or "").strip() or None)


def set_autofill_engine(session: Session, value: str) -> str:
    if value not in AUTOFILL_ENGINES:
        raise ValueError(f"engine must be one of {', '.join(AUTOFILL_ENGINES)}")
    if value == "jev" and not get_jev_api_key(session):
        raise ValueError("Add a Jev API key before switching form filling to Jev.")
    # "fast" is the default, so store nothing rather than a redundant row.
    _set_raw_value(session, AUTOFILL_ENGINE_KEY, None if value == "fast" else value)
    return value


AUTOFILL_LOW_STAKES_KEY = "autofill.low_stakes"  # the retired on/off switch; only ever cleared now
ANSWER_LEVEL_KEY = "autofill.answer_level"
AnswerLevel = Literal["facts", "history", "queued"]
ANSWER_LEVELS: tuple[str, ...] = ("facts", "history", "queued")
DEFAULT_ANSWER_LEVEL: AnswerLevel = "history"


def get_answer_level(session: Session | None = None) -> AnswerLevel:
    """How far a fill answers without asking (docs/plans/2026-10-10-companion-queued-run-design.md
    Part 3). Read by the server on every /map, /pick and /step; never taken from the client.
    facts: saved answers and career history only. history (default): plus the low-stakes kinds
    and history-backed "N years of a skill" Yes. queued: plus every requirement question on a
    job the user queued. The protected list sits outside every level."""
    value = _read(session, ANSWER_LEVEL_KEY)
    return value if value in ANSWER_LEVELS else DEFAULT_ANSWER_LEVEL


def set_answer_level(session: Session, level: AnswerLevel) -> None:
    if level not in ANSWER_LEVELS:
        raise ValueError(f"unknown answer level {level!r}")
    _set_raw_value(session, ANSWER_LEVEL_KEY, level)
    # The old switch is derived from the level now; drop its row so nothing reads a stale one.
    _set_raw_value(session, AUTOFILL_LOW_STAKES_KEY, None)


def get_autofill_low_stakes(session: Session | None = None) -> bool:
    """Low-stakes answers are on at every level but "facts" (derived from the answer level)."""
    return get_answer_level(session) != "facts"


def using_custom_endpoint(session: Session | None = None) -> bool:
    """True when the OpenAI-compatible client points somewhere we do not curate.

    `MODEL_OPTIONS` is a curated list of hosted models we have verified. It
    cannot enumerate what an arbitrary Ollama or vLLM host serves, so a custom
    endpoint switches model ids to free text.
    """
    return bool(get_base_url(session) or settings.openai_base_url)


def _parse_extra_models(raw: str | None) -> list[ModelOption]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[ModelOption] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "").strip()
        provider = str(item.get("provider") or "").strip()
        if not model_id or provider not in API_KEY_SETTINGS:
            continue
        label = str(item.get("label") or model_id).strip() or model_id
        tier = str(item.get("tier") or "extra").strip() or "extra"
        out.append(ModelOption(model_id, label, provider, tier))
    return out


def get_extra_models(session: Session) -> list[ModelOption]:
    return _parse_extra_models(_get_raw_value(session, EXTRA_MODELS_KEY))


def _save_extra_models(session: Session, extras: list[ModelOption]) -> None:
    if not extras:
        _set_raw_value(session, EXTRA_MODELS_KEY, None)
        return
    payload = [
        {"id": opt.id, "label": opt.label, "provider": opt.provider, "tier": opt.tier}
        for opt in extras
    ]
    _set_raw_value(session, EXTRA_MODELS_KEY, json.dumps(payload))


def _provider_for(model_id: str) -> str:
    """Best-effort provider for an id nobody registered.

    A display label only; routing is `registry.resolve`'s. Claude and Gemini ids
    carry their prefix; everything else is the OpenAI-compatible path, which is
    also where a custom endpoint's models go.
    """
    name = model_id.removeprefix("models/")
    if name.startswith("claude-"):
        return "anthropic"
    return "gemini" if name.startswith("gemini-") else "openai"


def catalog_provider(model_id: str, session: Session | None = None) -> str | None:
    """Provider tag of a seeded or user-added model; None when nobody registered the id."""
    for opt in MODEL_OPTIONS:
        if opt.id == model_id:
            return opt.provider
    if session is None:
        with SessionLocal() as owned:
            extras = get_extra_models(owned)
    else:
        extras = get_extra_models(session)
    return next((opt.provider for opt in extras if opt.id == model_id), None)


def configured_options(session: Session) -> list[ModelOption]:
    """Whatever the three roles currently point at, as catalog entries.

    THE CATALOG MUST ADMIT WHAT THE INSTALL IS ALREADY USING. `MODEL_OPTIONS`
    is a curated list that shrinks as models age out, and an id it drops does
    not disappear from installs configured with it — `.env.example` shipped
    FAST_MODEL=gpt-4o-mini until the seed trim. Leaving those ids out made
    `set_models` reject a value the user was not even changing, so saving an
    API key (the first thing a new install does) failed with no in-app way
    back. Self-healing on read rather than a migration: nothing is written,
    and the entry disappears the moment the role points elsewhere.
    """
    out: list[ModelOption] = []
    own = own_models(session)
    # Your own picks, which a save validates even while the recommended set answers (its ids are seeds).
    for role, model_id in (
        ("fast", own["fast"]),
        ("smart", own["smart"]),
        ("smart", own["assistant"]),
    ):
        cleaned = (model_id or "").strip()
        if cleaned and cleaned not in {opt.id for opt in out}:
            out.append(ModelOption(cleaned, cleaned, _provider_for(cleaned), role))
    return out


def get_usable_options(session: Session) -> list[ModelOption]:
    """Seeds, user-added extras, and the ids the roles point at right now.

    Seed wins on id collision, then extras, then configured — so a curated
    label is never overwritten by the bare-id fallback.
    """
    by_id = {opt.id: opt for opt in MODEL_OPTIONS}
    for extra in get_extra_models(session):
        by_id.setdefault(extra.id, extra)
    for configured in configured_options(session):
        by_id.setdefault(configured.id, configured)
    # Stable order: seeds first (MODEL_OPTIONS order), then the rest alphabetically.
    seed_ids = {opt.id for opt in MODEL_OPTIONS}
    rest = sorted(
        (opt for opt in by_id.values() if opt.id not in seed_ids),
        key=lambda opt: opt.id,
    )
    return [*MODEL_OPTIONS, *rest]


def usable_option_dicts(session: Session) -> list[dict[str, str]]:
    extra_ids = {opt.id for opt in get_extra_models(session)}
    out: list[dict[str, str]] = []
    for opt in get_usable_options(session):
        row = asdict(opt)
        if opt.id in VALID_MODEL_IDS:
            row["source"] = "seed"
        elif opt.id in extra_ids:
            row["source"] = "extra"
        else:
            # Not seeded and not added on purpose — it is here only because a
            # role still names it. Labelled so the UI can say so.
            row["source"] = "configured"
        out.append(row)
    return out


def usable_ids(session: Session) -> set[str]:
    return {opt.id for opt in get_usable_options(session)}


def add_extra_model(
    session: Session,
    model_id: str,
    provider: str,
    label: str | None = None,
) -> ModelOption:
    cleaned_id = (model_id or "").strip()
    cleaned_provider = (provider or "").strip()
    if not cleaned_id:
        raise ValueError("Model id must not be empty")
    if cleaned_provider not in API_KEY_SETTINGS:
        raise ValueError(f"provider must be one of {', '.join(API_KEY_SETTINGS)}")
    if cleaned_id in VALID_MODEL_IDS:
        raise ValueError(f"Model {cleaned_id} is already a built-in seed")
    extras = get_extra_models(session)
    if any(opt.id == cleaned_id for opt in extras):
        raise ValueError("That model is already in your list.")
    option = ModelOption(
        cleaned_id,
        (label or cleaned_id).strip() or cleaned_id,
        cleaned_provider,
        "extra",
    )
    extras.append(option)
    _save_extra_models(session, extras)
    return option


def remove_extra_model(session: Session, model_id: str) -> None:
    cleaned_id = (model_id or "").strip()
    if cleaned_id in VALID_MODEL_IDS:
        raise ValueError("Built-in seed models cannot be removed")
    extras = get_extra_models(session)
    if not any(opt.id == cleaned_id for opt in extras):
        raise KeyError(f"Model not in catalog: {cleaned_id}")
    own = own_models(session)  # your picks hold their models even while the recommended set answers
    in_use = {own["fast"], own["smart"], own["assistant"]}
    if cleaned_id in in_use:
        raise ValueError(
            f"The model {cleaned_id} is your Fast, Smart or Assistant model. Pick "
            "another model for that first."
        )
    _save_extra_models(session, [opt for opt in extras if opt.id != cleaned_id])


def validate_models(
    fast_model: str,
    smart_model: str,
    session: Session,
    chat_model: str | None = None,
) -> None:
    """Raise ValueError for a role value `set_models` would refuse. Writes nothing, so a
    caller can validate BEFORE saving anything else (a rejected PUT stores no key)."""
    custom = using_custom_endpoint(session)
    allowed = usable_ids(session)
    for model in (fast_model, smart_model):
        if not custom and model not in allowed:
            raise ValueError(f"Unsupported model: {model}")
        if custom and not model.strip():
            raise ValueError("Model id must not be empty")
    if chat_model is not None:
        if not custom and chat_model not in allowed:
            raise ValueError(f"Unsupported model: {chat_model}")
        if custom and not chat_model.strip():
            raise ValueError("Model id must not be empty")
        from app.services import llm_capabilities

        report = llm_capabilities.load(session, chat_model)
        if report is not None and not report.supports("tools"):
            raise ValueError(
                "The Assistant model has to pass the tool test. Press Test next to it first."
            )


def set_models(
    fast_model: str,
    smart_model: str,
    session: Session,
    chat_model: str | None = None,
) -> tuple[str, str]:
    validate_models(fast_model, smart_model, session, chat_model)
    if chat_model is not None:
        _set_value(session, CHAT_MODEL_KEY, chat_model)
    fast = _set_value(session, FAST_MODEL_KEY, fast_model)
    smart = _set_value(session, SMART_MODEL_KEY, smart_model)
    return fast, smart
