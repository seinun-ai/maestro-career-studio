import os
import re
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import StrictBool
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.db import begin_write, get_db
from app.schemas.auto_apply import AutoApplySettings
from app.schemas.companion_apply import CompanionApplySettings
from app.schemas.eeo_consent import EeoConsent
from app.schemas.job_preferences import JobPreferences
from app.schemas.job_site_login import (
    PASSWORD_MAX,
    PASSWORD_MIN,
    JobSiteLoginIn,
    JobSiteLoginStatus,
)
from app.schemas.market_settings import MarketSetting
from app.schemas.mcp_workflow import McpWorkflowSettings
from app.schemas.money import MoneySettings, MoneySettingsResponse
from app.schemas.settings import (
    AutofillProfilePayload,
    PromptPayload,
    SettingEnvelope,
    SettingValue,
    SettingValueIn,
    TextSettingPayload,
)
from app.services import (
    auto_apply_settings,
    autofill_profile,
    companion_apply,
    eeo_consent,
    jev,
    job_preferences,
    job_site_login,
    llm_capabilities,
    market_settings,
    markets,
    mcp_workflow,
    model_settings,
    money_settings,
    persona,
    prompts,
    quick_tailor,
)
from app.services.llm import LLMProviderError
from app.services.llm_providers import registry
from app.services.sync import offers as sync_offers
from app.services.sync import pairing as sync_pairing


class JevInfo(BaseModel):
    """GET/PUT /api/settings/jev. Like OpenAIInfo: a `*_configured` flag, never the key."""

    api_key_configured: bool
    base_url: str
    model: str
    engine: Literal["fast", "jev"]


class JevSettingsPayload(BaseModel):
    """A patch, as ModelSettingsPayload: absent = leave alone; null/"" = clear."""

    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    engine: Literal["fast", "jev"] | None = None


class AutofillOptions(BaseModel):
    """GET/PUT /api/settings/autofill-options — how far a fill answers without asking."""

    model_config = ConfigDict(extra="forbid")
    answer_level: Literal["facts", "history", "queued"]


class JevProbeResult(BaseModel):
    ok: bool
    error: str | None = None


class OpenAIInfo(BaseModel):
    """Read model for GET/PUT /api/settings/openai.

    Deliberately carries only `*_configured` booleans, never the key material:
    this API has no authentication, so anything returned here is readable by
    anyone who can reach the port. Do not re-add `openai_api_key` /
    `gemini_api_key` — the write path no longer needs the client to echo them
    back (see `put_openai_info`).
    """

    fast_model: str
    smart_model: str
    chat_model: str
    reasoning_model: str
    api_key_configured: bool
    gemini_api_key_configured: bool
    anthropic_api_key_configured: bool
    openrouter_api_key_configured: bool
    # Where the effective key comes from: a key saved in the app ("settings")
    # BEATS one from .env ("env"). Surfaced because a stale settings-stored
    # key over a blank .env reads as "configured" while every call 401s —
    # the source is the fact that explains it.
    openai_key_source: Literal["settings", "env", "none"]
    gemini_key_source: Literal["settings", "env", "none"]
    anthropic_key_source: Literal["settings", "env", "none"]
    openrouter_key_source: Literal["settings", "env", "none"]
    model_options: list[dict[str, str]]
    # Usable catalog (seeds ∪ llm.extra_models), each with source=seed|extra.
    # base_url is a location (not a secret), so it is echoed. When set,
    # custom_endpoint is true and role pickers accept free-text ids.
    base_url: str | None = None
    custom_endpoint: bool = False
    json_mode: str = "auto"
    # model id -> its last capability probe.
    capabilities: dict[str, dict] = {}


class ModelSettingsPayload(BaseModel):
    """Every field is a patch: absent means "leave the stored value alone".

    All of them, not just the keys. The role fields used to be required, which
    forced any caller that wanted to change one thing to echo the other two
    back — so the Settings page re-sent all three models to save an API key,
    and re-sent both keys' worth of state to change a dropdown. Echoing state
    you did not edit is how a stale copy overwrites a fresh one; the client now
    sends only what the user touched.
    """

    fast_model: str | None = None
    smart_model: str | None = None
    chat_model: str | None = None
    # Same tri-state as the keys below: absent leaves it, null or "" goes back to the default (the strong model).
    reasoning_model: str | None = None
    # Same absent/null/value tri-state as the key fields below.
    base_url: str | None = None
    json_mode: str | None = None
    # Tri-state, resolved via `model_fields_set` in the handler: field ABSENT
    # means "leave the stored key alone", explicit null/"" means "clear it",
    # a string means "set it". Absent must not clear — the settings page PUTs
    # this payload on every model-dropdown change.
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    anthropic_api_key: str | None = None
    openrouter_api_key: str | None = None


RoleModels = dict[Literal["fast", "smart", "assistant", "reasoning"], str]
ProviderName = Literal["openai", "gemini", "anthropic", "openrouter"]


class RecommendedModelsInfo(BaseModel):
    """GET/PUT /api/settings/models/recommended: whether the four roles use the recommended set."""

    on: bool
    # The provider you chose; null is the first provider (the screen's order) with a key and a set.
    provider: ProviderName | None
    # Whose set the roles answer now; null while off, or when no provider with a set has a key.
    active_provider: ProviderName | None
    # That set (the roles' models now); null when `active_provider` is.
    models: RoleModels | None
    # Your own picks: what the roles answer once it is off.
    own: RoleModels
    # Every provider's set (from services/data/recommended_models.yaml); one with none is absent.
    sets: dict[str, RoleModels]


class RecommendedModelsPayload(BaseModel):
    """`provider` absent keeps the choice; null is the first provider with a key."""

    model_config = ConfigDict(extra="forbid")
    on: StrictBool
    provider: ProviderName | None = None


class PersonaDraft(BaseModel):
    draft: str


router = APIRouter(prefix="/api/settings", tags=["settings"])


def _second_copy_home():
    if app_settings.sync_remote_url:
        raise HTTPException(409, detail=sync_pairing.HOME_ONLY)
    if not sync_pairing.LOCK.acquire(blocking=False):
        raise HTTPException(409, detail="A sync is already running.")
    try:
        yield
    finally:
        sync_pairing.LOCK.release()


@router.get("/second-copy", dependencies=[Depends(_second_copy_home)])
def get_second_copy(db: Annotated[Session, Depends(get_db)]):
    return sync_pairing.window_status(db)


@router.post("/second-copy", dependencies=[Depends(_second_copy_home)])
def allow_second_copy(db: Annotated[Session, Depends(get_db)]):
    try:
        return sync_pairing.open_window(db)
    except sync_pairing.Refused as refusal:
        raise HTTPException(refusal.status_code, detail=refusal.detail) from None


@router.delete("/second-copy", dependencies=[Depends(_second_copy_home)])
def stop_second_copy(db: Annotated[Session, Depends(get_db)]):
    return sync_pairing.close_window(db)


_SETUP_PROMPT = Path(__file__).resolve().parent.parent / "automations" / "bot-setup.md"
_LAPTOP_LATER = "<your laptop's address — I'll give it to you>"


@lru_cache(maxsize=1)
def _bot_setup_text() -> str:
    return _SETUP_PROMPT.read_text(encoding="utf-8")


def _bare_host(value: str) -> str:
    """Host only: drop a scheme, userinfo, a path, a query and a fragment. Keep a numeric port."""
    text = value.strip()
    if not text:
        return ""
    # A bare host:port has no scheme. urlsplit would treat the host as the scheme.
    parsed = urlsplit(text if "://" in text else "//" + text)
    netloc = parsed.netloc
    if "@" in netloc:
        netloc = netloc.rsplit("@", 1)[1]
    return netloc.strip()


def _laptop_url(value: str) -> str:
    host = _bare_host(value)
    if not host:
        return _LAPTOP_LATER
    return "https://" + host


_RELEASE = re.compile(r"v?(\d+\.\d+\.\d+)")


def _checkout() -> str:
    """Which version the bot checks out: this laptop's release, or the newest one.

    APP_VERSION is the same string GET /api/version reports. A local build has
    "dev" (or "dev-<sha>"), which is no tag, so the bot takes the newest release.
    """
    match = _RELEASE.fullmatch(os.environ.get("APP_VERSION", "dev").strip())
    if match:
        return f"check out tag v{match.group(1)}, the version my laptop runs"
    return "check out the newest release tag (my laptop runs a local build)"


def _refuse_always_on_copy():
    """The setup prompt is static. It does not take the sync lock."""
    if app_settings.sync_remote_url:
        raise HTTPException(409, detail=sync_pairing.HOME_ONLY)


@router.get("/second-copy/setup-prompt", dependencies=[Depends(_refuse_always_on_copy)])
def get_second_copy_setup_prompt():
    text = _bot_setup_text().replace("{laptop_url}", _laptop_url(app_settings.sync_public_host))
    return {"prompt": text.replace("{checkout}", _checkout())}


class _JobSiteLoginRoute(APIRoute):
    """Keep rejected credentials out of every login validation response."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            try:
                return await original(request)
            except RequestValidationError:
                raise HTTPException(422, detail="The job-site login is invalid.") from None

        return handler


job_site_login_router = APIRouter(route_class=_JobSiteLoginRoute)


def _prompt_or_404(action):
    try:
        return action()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/persona", response_model=SettingValue)
def get_persona(db: Annotated[Session, Depends(get_db)]):
    return SettingValue(key="persona", value=persona.get_persona(db))


@router.put("/persona", response_model=SettingValue)
def put_persona(payload: TextSettingPayload, db: Annotated[Session, Depends(get_db)]):
    return SettingValue(key="persona", value=persona.set_persona(payload.value, db))


@router.post("/persona/draft", response_model=PersonaDraft)
def draft_persona(db: Annotated[Session, Depends(get_db)]):
    try:
        return PersonaDraft(draft=persona.draft_persona(db))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/autofill", response_model=SettingEnvelope[dict[str, Any]])
def get_autofill(db: Annotated[Session, Depends(get_db)]):
    return {"key": "autofill_profile", "value": autofill_profile.get_profile(db)}


@router.put("/autofill", response_model=SettingEnvelope[dict[str, Any]])
def put_autofill(payload: AutofillProfilePayload, db: Annotated[Session, Depends(get_db)]):
    return {
        "key": "autofill_profile",
        "value": autofill_profile.set_profile(payload.value, db),
    }


@router.get("/quick-tailor", response_model=SettingEnvelope[dict[str, Any]])
def get_quick_tailor(db: Annotated[Session, Depends(get_db)]):
    return {"key": "quick_tailor_profile", "value": quick_tailor.get_profile(db)}


@router.put("/quick-tailor", response_model=SettingEnvelope[dict[str, Any]])
def put_quick_tailor(
    payload: SettingValueIn[dict[str, Any]], db: Annotated[Session, Depends(get_db)]
):
    return {"key": "quick_tailor_profile", "value": quick_tailor.set_profile(payload.value, db)}


@router.get("/mcp-workflow", response_model=SettingEnvelope[McpWorkflowSettings])
def get_mcp_workflow(db: Annotated[Session, Depends(get_db)]):
    return {"key": "mcp_workflow", "value": mcp_workflow.get_settings(db)}


@router.put("/mcp-workflow", response_model=SettingEnvelope[McpWorkflowSettings])
def put_mcp_workflow(
    payload: SettingValueIn[McpWorkflowSettings], db: Annotated[Session, Depends(get_db)]
):
    return {"key": "mcp_workflow", "value": mcp_workflow.set_settings(payload.value, db)}


@router.get("/companion-apply", response_model=SettingEnvelope[CompanionApplySettings])
def get_companion_apply(db: Annotated[Session, Depends(get_db)]):
    return {"key": "companion_apply", "value": companion_apply.get_settings(db)}


@router.put("/companion-apply", response_model=SettingEnvelope[CompanionApplySettings])
def put_companion_apply(
    payload: SettingValueIn[CompanionApplySettings], db: Annotated[Session, Depends(get_db)]
):
    return {"key": "companion_apply", "value": companion_apply.set_settings(payload.value, db)}


@router.get("/job-preferences", response_model=SettingEnvelope[JobPreferences])
def get_job_preferences(db: Annotated[Session, Depends(get_db)]):
    return {"key": "job_preferences", "value": job_preferences.get_preferences(db)}


@router.put("/job-preferences", response_model=SettingEnvelope[JobPreferences])
def put_job_preferences(
    payload: SettingValueIn[JobPreferences], db: Annotated[Session, Depends(get_db)]
):
    return {"key": "job_preferences", "value": job_preferences.set_preferences(payload.value, db)}


def _market_body(setting: MarketSetting) -> dict[str, Any]:
    """`{key, value}` like every settings blob, with `home` and `apply_in` beside it and the
    home market's currency and EEO posture, so one response drives the picker."""
    return {
        "key": "market",
        "value": setting,
        "home": setting.home,
        "apply_in": setting.apply_in,
        "currency": markets.currency_for(setting.home),
        "offers_eeo": markets.offers_eeo(setting.home),
    }


@router.get("/market")
def get_market(db: Annotated[Session, Depends(get_db)]):
    """Where the user lives and applies, plus the vocabulary it drives.

    `markets` and each one's `offers_eeo` ride along so the picker and the EEO section are
    driven by one response: the frontend must never hardcode the market list or decide for
    itself whether to show demographic questions.
    """
    return {
        **_market_body(market_settings.get_market(db)),
        "markets": [
            {
                "key": k,
                "label": markets.labels()[k],
                "country_code": markets.country_code(k),
                "currency": markets.currency_for(k),
                "date_format": markets.get(k)["date_format"],
                "offers_eeo": markets.offers_eeo(k),
            }
            for k in markets.keys()
        ],
    }


@router.put("/market")
def put_market(payload: SettingValueIn[MarketSetting], db: Annotated[Session, Depends(get_db)]):
    """Takes `{home, apply_in}` or the old `{market}` (read as home = apply_in = market)."""
    return _market_body(market_settings.set_market(payload.value, db))


@router.get("/money", response_model=MoneySettingsResponse)
def get_money(db: Annotated[Session, Depends(get_db)]):
    """How pay reads, plus the currency it resolves to (yours, else where you live)."""
    value = money_settings.get_settings(db)
    return {"key": "money", "value": value, "home_currency": money_settings.home_currency(db)}


@router.put("/money", response_model=MoneySettingsResponse)
def put_money(payload: SettingValueIn[MoneySettings], db: Annotated[Session, Depends(get_db)]):
    value = money_settings.set_settings(payload.value, db)
    return {"key": "money", "value": value, "home_currency": money_settings.home_currency(db)}


def _lock_auto_apply_settings(db: Session) -> AutoApplySettings:
    auto_apply_settings.get_settings(db)  # seed before taking the SQLite write lock
    begin_write(db)
    db.expire_all()
    return auto_apply_settings.get_settings(db)


@router.get("/auto-apply", response_model=SettingEnvelope[AutoApplySettings])
def get_auto_apply(db: Annotated[Session, Depends(get_db)]):
    return {"key": "auto_apply", "value": auto_apply_settings.get_settings(db)}


@router.put("/auto-apply", response_model=SettingEnvelope[AutoApplySettings])
def put_auto_apply(
    payload: SettingValueIn[AutoApplySettings], db: Annotated[Session, Depends(get_db)]
):
    stored = _lock_auto_apply_settings(db)
    value = payload.value.model_copy(update={"full_automation": stored.full_automation})
    return {"key": "auto_apply", "value": auto_apply_settings.set_settings(value, db)}


@router.put("/full-automation", response_model=SettingEnvelope[AutoApplySettings])
def put_full_automation(
    payload: SettingValueIn[StrictBool], db: Annotated[Session, Depends(get_db)]
):
    current = _lock_auto_apply_settings(db)
    value = current.model_copy(update={"full_automation": payload.value})
    if payload.value:
        return {"key": "auto_apply", "value": auto_apply_settings.set_settings(value, db)}
    with sync_offers.withdrawing(db):  # off takes back every offer in the commit that saves it
        return {"key": "auto_apply", "value": auto_apply_settings.set_settings(value, db)}


@job_site_login_router.get("/job-site-login", response_model=JobSiteLoginStatus)
def get_job_site_login():
    return job_site_login.status()


@job_site_login_router.put("/job-site-login", response_model=JobSiteLoginStatus)
def put_job_site_login(payload: JobSiteLoginIn):
    if payload.password is not None and not PASSWORD_MIN <= len(payload.password) <= PASSWORD_MAX:
        raise HTTPException(
            422, detail=f"The password needs {PASSWORD_MIN} to {PASSWORD_MAX} characters."
        )
    job_site_login.write(payload.email, payload.password)
    return job_site_login.status()


@job_site_login_router.delete("/job-site-login", status_code=204)
def delete_job_site_login():
    job_site_login.clear()


router.include_router(job_site_login_router)


@router.get("/eeo-consent", response_model=SettingEnvelope[EeoConsent])
def get_eeo_consent(db: Annotated[Session, Depends(get_db)]):
    return {"key": "eeo_consent", "value": eeo_consent.get_consent(db)}


@router.put("/eeo-consent", response_model=SettingEnvelope[EeoConsent])
def put_eeo_consent(payload: SettingValueIn[EeoConsent], db: Annotated[Session, Depends(get_db)]):
    return {"key": "eeo_consent", "value": eeo_consent.set_consent(payload.value, db)}


@router.get("/prompts", response_model=list[SettingValue])
def list_prompts(db: Annotated[Session, Depends(get_db)]):
    return [
        SettingValue(key=key, value=prompts.get_prompt(key, db))
        for key in sorted(prompts.VALID_PROMPTS)
    ]


@router.put("/prompts/{key}", response_model=SettingValue)
def put_prompt(key: str, payload: PromptPayload, db: Annotated[Session, Depends(get_db)]):
    value = _prompt_or_404(lambda: prompts.set_prompt(key, payload.value, db))
    return SettingValue(key=key, value=value)


@router.post("/prompts/{key}/reset", response_model=SettingValue)
def reset_prompt(key: str, db: Annotated[Session, Depends(get_db)]):
    value = _prompt_or_404(lambda: prompts.reset_prompt(key, db))
    return SettingValue(key=key, value=value)


def _key_state(db: Session, provider: str, env_value: str) -> tuple[bool, str]:
    stored = model_settings.get_api_key(provider, db)
    return bool(stored or env_value), ("settings" if stored else "env" if env_value else "none")


@router.get("/openai", response_model=OpenAIInfo)
def get_openai_info(db: Annotated[Session, Depends(get_db)]):
    openai_ok, openai_src = _key_state(db, "openai", app_settings.openai_api_key)
    gemini_ok, gemini_src = _key_state(db, "gemini", app_settings.gemini_api_key)
    anthropic_ok, anthropic_src = _key_state(db, "anthropic", app_settings.anthropic_api_key)
    openrouter_ok, openrouter_src = _key_state(db, "openrouter", app_settings.openrouter_api_key)
    return OpenAIInfo(
        fast_model=model_settings.get_fast_model(db),
        smart_model=model_settings.get_smart_model(db),
        chat_model=model_settings.get_chat_model(db),
        reasoning_model=model_settings.get_reasoning_model(db),
        api_key_configured=openai_ok,
        gemini_api_key_configured=gemini_ok,
        anthropic_api_key_configured=anthropic_ok,
        openrouter_api_key_configured=openrouter_ok,
        openai_key_source=openai_src,
        gemini_key_source=gemini_src,
        anthropic_key_source=anthropic_src,
        openrouter_key_source=openrouter_src,
        model_options=model_settings.usable_option_dicts(db),
        base_url=model_settings.get_base_url(db) or app_settings.openai_base_url or None,
        custom_endpoint=model_settings.using_custom_endpoint(db),
        json_mode=model_settings.get_json_mode(db),
        capabilities=_capability_map(db),
    )


def _capability_map(db: Session) -> dict[str, dict]:
    """Probes for the four configured models only (fast, smart, chat, Reasoning) — not every model ever tried."""
    out: dict[str, dict] = {}
    for model in {
        model_settings.get_fast_model(db),
        model_settings.get_smart_model(db),
        model_settings.get_chat_model(db),
        model_settings.get_reasoning_model(db),
    }:
        report = llm_capabilities.load(db, model)
        if report is not None:
            out[model] = asdict(report)
    return out


@router.put("/openai", response_model=OpenAIInfo)
def put_openai_info(payload: ModelSettingsPayload, db: Annotated[Session, Depends(get_db)]):
    # A field the client did not send must survive this write: keys are patched
    # only for the providers named in `model_fields_set` (`set_api_keys`), and the
    # role fields resolve the same way, which is what makes a key-only or
    # one-dropdown PUT legal.
    sent = payload.model_fields_set
    # Your own picks, not the roles' current answer: while "Use recommended models" is on that is the
    # set's, and writing it back would overwrite the picks turning it off restores.
    own = model_settings.own_models(db)
    fast_model = payload.fast_model or own["fast"]
    smart_model = payload.smart_model or own["smart"]
    # chat_model keeps its own tri-state: `set_models` treats None as "not
    # supplied" and skips the streaming-tool-call gate, so an absent field must
    # arrive as None rather than as the stored value re-validated.
    chat_model = payload.chat_model if "chat_model" in sent else None
    # The endpoint must land BEFORE set_models: it decides whether model ids are
    # validated against the curated allowlist or accepted as free text, so
    # writing it after would reject the very local model ids it enables.
    if "base_url" in sent:
        try:
            model_settings.set_base_url(db, payload.base_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if "json_mode" in sent:
        try:
            model_settings.set_json_mode(db, payload.json_mode)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Validate the roles BEFORE saving keys: a PUT that answers 400 saves no key.
    # Keys land before `set_models`; a model change and a key in one PUT both land.
    try:
        model_settings.validate_models(fast_model, smart_model, db, chat_model=chat_model)
        if "reasoning_model" in sent:
            model_settings.validate_reasoning_model(db, payload.reasoning_model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    sent_keys = {
        provider: getattr(payload, f"{provider}_api_key")
        for provider in model_settings.API_KEY_SETTINGS
        if f"{provider}_api_key" in sent
    }
    if sent_keys:
        model_settings.set_api_keys(db, sent_keys)
    try:
        model_settings.set_models(fast_model, smart_model, db, chat_model=chat_model)
        if "reasoning_model" in sent:
            model_settings.set_reasoning_model(db, payload.reasoning_model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return get_openai_info(db)


def _recommended_info(db: Session) -> RecommendedModelsInfo:
    on, provider = model_settings.get_recommended(db)
    active = model_settings.recommended_provider(db)
    sets = model_settings.recommended_sets()
    return RecommendedModelsInfo(
        on=on,
        provider=provider,
        active_provider=active,
        models=sets[active] if active else None,
        own=model_settings.own_models(db),
        sets=sets,
    )


@router.get("/models/recommended", response_model=RecommendedModelsInfo)
def get_recommended_models(db: Annotated[Session, Depends(get_db)]):
    return _recommended_info(db)


@router.put("/models/recommended", response_model=RecommendedModelsInfo)
def put_recommended_models(payload: RecommendedModelsPayload, db: Annotated[Session, Depends(get_db)]):
    """Turn the recommended set on (for `provider`, or the first provider with a key) or off. Your
    own picks are never written: off, the roles answer them again."""
    if payload.on and "provider" not in payload.model_fields_set:
        provider = model_settings.get_recommended(db)[1]
    else:
        provider = payload.provider
    try:
        model_settings.set_recommended(db, on=payload.on, provider=provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _recommended_info(db)


class ProbePayload(BaseModel):
    model: str


class SyncPayload(BaseModel):
    provider: Literal["openai", "gemini", "anthropic", "openrouter"]


class ExtraModelPayload(BaseModel):
    id: str
    provider: Literal["openai", "gemini", "anthropic", "openrouter"]
    label: str | None = None


@router.post("/openai/probe")
def probe_model(payload: ProbePayload, db: Annotated[Session, Depends(get_db)]):
    """Measure what a model can do, so surfaces fail at configure time not mid-run.

    Never 502s on a dead endpoint: an unreachable model is a report of three
    Nos with the errors attached, which is exactly what the UI needs to show.
    """
    return asdict(llm_capabilities.probe_and_save(db, payload.model))


@router.post("/openai/sync")
def sync_provider_models(payload: SyncPayload, db: Annotated[Session, Depends(get_db)]):
    """List chat-like models from the chosen provider (OpenAI, Gemini, Claude or OpenRouter)
    for discovery; nothing is added to the catalog until the user clicks +."""
    try:
        discovered = registry.get(payload.provider).list_models()
    except LLMProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    in_catalog = model_settings.usable_ids(db)
    return {"models": [{**row, "in_catalog": row["id"] in in_catalog} for row in discovered]}


@router.post("/openai/models", response_model=OpenAIInfo)
def add_catalog_model(payload: ExtraModelPayload, db: Annotated[Session, Depends(get_db)]):
    try:
        model_settings.add_extra_model(db, payload.id, payload.provider, label=payload.label)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return get_openai_info(db)


@router.get("/jev", response_model=JevInfo)
def get_jev_info(db: Annotated[Session, Depends(get_db)]):
    return JevInfo(
        api_key_configured=bool(model_settings.get_jev_api_key(db)),
        base_url=model_settings.get_jev_base_url(db),
        model=model_settings.get_jev_model(db),
        engine=model_settings.get_autofill_engine(db),
    )


@router.put("/jev", response_model=JevInfo)
def put_jev_info(payload: JevSettingsPayload, db: Annotated[Session, Depends(get_db)]):
    sent = payload.model_fields_set
    try:
        # Endpoint, then key, then engine: a host change forgets the stored key,
        # so a key sent WITH the switch lands after it; the engine check reads it.
        if "base_url" in sent:
            model_settings.set_jev_base_url(db, payload.base_url)
        if "api_key" in sent:
            model_settings.set_jev_api_key(db, payload.api_key)
        if "model" in sent:
            model_settings.set_jev_model(db, payload.model)
        if "engine" in sent and payload.engine is not None:
            model_settings.set_autofill_engine(db, payload.engine)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return get_jev_info(db)


@router.get("/autofill-options", response_model=AutofillOptions)
def get_autofill_options(db: Annotated[Session, Depends(get_db)]):
    return AutofillOptions(answer_level=model_settings.get_answer_level(db))


@router.put("/autofill-options", response_model=AutofillOptions)
def put_autofill_options(payload: AutofillOptions, db: Annotated[Session, Depends(get_db)]):
    model_settings.set_answer_level(db, payload.answer_level)
    return get_autofill_options(db)


@router.post("/jev/probe", response_model=JevProbeResult)
def probe_jev(db: Annotated[Session, Depends(get_db)]):
    """Never 502s: a refused key is a result the Settings card shows, like /openai/probe."""
    try:
        jev.probe(db)
    except LLMProviderError as exc:
        return JevProbeResult(ok=False, error=str(exc))
    return JevProbeResult(ok=True)


@router.delete("/openai/models/{model_id:path}", response_model=OpenAIInfo)
def remove_catalog_model(model_id: str, db: Annotated[Session, Depends(get_db)]):
    try:
        model_settings.remove_extra_model(db, model_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return get_openai_info(db)
