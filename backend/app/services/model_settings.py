import json
from dataclasses import asdict, dataclass
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models.setting import Setting


FAST_MODEL_KEY = "llm.fast_model"
SMART_MODEL_KEY = "llm.smart_model"
CHAT_MODEL_KEY = "llm.chat_model"
EXTRA_MODELS_KEY = "llm.extra_models"


@dataclass(frozen=True)
class ModelOption:
    id: str
    label: str
    provider: str
    tier: str


MODEL_OPTIONS = [
    # Released 2026-07: current lightweight Gemini tier (user's preferred fast
    # model). Live-verified against a real JD extraction on 2026-07-22.
    ModelOption("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite", "gemini", "fast"),
    ModelOption("gemini-3.7-flash", "Gemini 3.7 Flash", "gemini", "fast"),
    # GPT-5.6 family (released 2026-07-09): 1.05M context, tools + streaming.
    ModelOption("gpt-5.6-luna", "OpenAI GPT-5.6 Luna", "openai", "smart"),
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


def get_fast_model(session: Session | None = None) -> str:
    if session is None:
        with SessionLocal() as owned:
            return _get_value(owned, FAST_MODEL_KEY, settings.fast_model)
    return _get_value(session, FAST_MODEL_KEY, settings.fast_model)


def get_smart_model(session: Session | None = None) -> str:
    if session is None:
        with SessionLocal() as owned:
            return _get_value(owned, SMART_MODEL_KEY, settings.smart_model)
    return _get_value(session, SMART_MODEL_KEY, settings.smart_model)


def get_chat_model(session: Session | None = None) -> str:
    if session is None:
        with SessionLocal() as owned:
            return _get_value(owned, CHAT_MODEL_KEY, settings.chat_model)
    return _get_value(session, CHAT_MODEL_KEY, settings.chat_model)


OPENAI_API_KEY_KEY = "llm.openai_api_key"
GEMINI_API_KEY_KEY = "llm.gemini_api_key"
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


def get_openai_api_key(session: Session | None = None) -> str | None:
    if session is None:
        with SessionLocal() as owned:
            return _get_raw_value(owned, OPENAI_API_KEY_KEY)
    return _get_raw_value(session, OPENAI_API_KEY_KEY)


def get_gemini_api_key(session: Session | None = None) -> str | None:
    if session is None:
        with SessionLocal() as owned:
            return _get_raw_value(owned, GEMINI_API_KEY_KEY)
    return _get_raw_value(session, GEMINI_API_KEY_KEY)


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
    cleaned = (value or "").strip() or None
    if cleaned is not None:
        parsed = urlparse(cleaned)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(
                "base_url must be an absolute http:// or https:// URL, "
                "e.g. http://host.docker.internal:11434/v1"
            )
    return _set_raw_value(session, BASE_URL_KEY, cleaned)


JSON_MODES = ("auto", "on", "off")


def set_json_mode(session: Session, value: str | None) -> str | None:
    normalized = (value or "auto").strip().lower()
    if normalized not in JSON_MODES:
        raise ValueError(f"json_mode must be one of {', '.join(JSON_MODES)}")
    # "auto" is the default, so store nothing rather than a redundant row.
    return _set_raw_value(session, JSON_MODE_KEY, None if normalized == "auto" else normalized)


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
        if not model_id or provider not in {"openai", "gemini"}:
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

    Gemini ids carry the prefix; everything else takes the OpenAI-compatible
    path, which is also where a custom endpoint's models go.
    """
    return "gemini" if model_id.removeprefix("models/").startswith("gemini-") else "openai"


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
    for role, model_id in (
        ("fast", get_fast_model(session)),
        ("smart", get_smart_model(session)),
        ("smart", get_chat_model(session)),
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
    if cleaned_provider not in {"openai", "gemini"}:
        raise ValueError("provider must be openai or gemini")
    if cleaned_id in VALID_MODEL_IDS:
        raise ValueError(f"Model {cleaned_id} is already a built-in seed")
    extras = get_extra_models(session)
    if any(opt.id == cleaned_id for opt in extras):
        raise ValueError(f"Model {cleaned_id} is already in the catalog")
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
    in_use = {
        get_fast_model(session),
        get_smart_model(session),
        get_chat_model(session),
    }
    if cleaned_id in in_use:
        raise ValueError(
            f"Model {cleaned_id} is in use by Fast, Smart, or Chat — "
            "change that role first"
        )
    _save_extra_models(session, [opt for opt in extras if opt.id != cleaned_id])


def set_models(
    fast_model: str,
    smart_model: str,
    session: Session,
    chat_model: str | None = None,
    openai_api_key: str | None = None,
    gemini_api_key: str | None = None,
) -> tuple[str, str, str | None, str | None]:
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
                "chat needs a model that passes the streaming tool-call test — run Test"
            )
        _set_value(session, CHAT_MODEL_KEY, chat_model)
    fast = _set_value(session, FAST_MODEL_KEY, fast_model)
    smart = _set_value(session, SMART_MODEL_KEY, smart_model)
    openai_key = _set_raw_value(session, OPENAI_API_KEY_KEY, openai_api_key)
    gemini_key = _set_raw_value(session, GEMINI_API_KEY_KEY, gemini_api_key)
    return fast, smart, openai_key, gemini_key
