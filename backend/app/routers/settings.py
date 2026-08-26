from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.db import get_db
from app.schemas.settings import (
    AutoApplyPayload,
    AutofillProfilePayload,
    EeoConsentPayload,
    JobPreferencesPayload,
    MarketPayload,
    McpWorkflowPayload,
    PromptPayload,
    QuickTailorProfilePayload,
    SettingValue,
    TextSettingPayload,
)
from app.services import (
    auto_apply_settings,
    autofill_profile,
    eeo_consent,
    job_preferences,
    llm,
    llm_capabilities,
    market_settings,
    markets,
    mcp_workflow,
    model_settings,
    persona,
    prompts,
    quick_tailor,
)
from app.services.llm import LLMProviderError


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
    api_key_configured: bool
    gemini_api_key_configured: bool
    # Where the effective key comes from: a key saved in the app ("settings")
    # BEATS one from .env ("env"). Surfaced because a stale settings-stored
    # key over a blank .env reads as "configured" while every call 401s —
    # the source is the fact that explains it.
    openai_key_source: Literal["settings", "env", "none"]
    gemini_key_source: Literal["settings", "env", "none"]
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
    fast_model: str
    smart_model: str
    # Optional so pre-existing clients that omit it keep working.
    chat_model: str | None = None
    # Same absent/null/value tri-state as the key fields below.
    base_url: str | None = None
    json_mode: str | None = None
    # Tri-state, resolved via `model_fields_set` in the handler: field ABSENT
    # means "leave the stored key alone", explicit null/"" means "clear it",
    # a string means "set it". Absent must not clear — the settings page PUTs
    # this payload on every model-dropdown change.
    openai_api_key: str | None = None
    gemini_api_key: str | None = None


class PersonaDraft(BaseModel):
    draft: str


router = APIRouter(prefix="/api/settings", tags=["settings"])


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


@router.get("/autofill")
def get_autofill(db: Annotated[Session, Depends(get_db)]):
    return {"key": "autofill_profile", "value": autofill_profile.get_profile(db)}


@router.put("/autofill")
def put_autofill(payload: AutofillProfilePayload, db: Annotated[Session, Depends(get_db)]):
    return {
        "key": "autofill_profile",
        "value": autofill_profile.set_profile(payload.value, db),
    }


@router.get("/quick-tailor")
def get_quick_tailor(db: Annotated[Session, Depends(get_db)]):
    return {"key": "quick_tailor_profile", "value": quick_tailor.get_profile(db)}


@router.put("/quick-tailor")
def put_quick_tailor(payload: QuickTailorProfilePayload, db: Annotated[Session, Depends(get_db)]):
    return {"key": "quick_tailor_profile", "value": quick_tailor.set_profile(payload.value, db)}


@router.get("/mcp-workflow")
def get_mcp_workflow(db: Annotated[Session, Depends(get_db)]):
    return {"key": "mcp_workflow", "value": mcp_workflow.get_settings(db)}


@router.put("/mcp-workflow")
def put_mcp_workflow(payload: McpWorkflowPayload, db: Annotated[Session, Depends(get_db)]):
    return {"key": "mcp_workflow", "value": mcp_workflow.set_settings(payload.value, db)}


@router.get("/job-preferences")
def get_job_preferences(db: Annotated[Session, Depends(get_db)]):
    return {"key": "job_preferences", "value": job_preferences.get_preferences(db)}


@router.put("/job-preferences")
def put_job_preferences(payload: JobPreferencesPayload, db: Annotated[Session, Depends(get_db)]):
    return {"key": "job_preferences", "value": job_preferences.set_preferences(payload.value, db)}


@router.get("/market")
def get_market(db: Annotated[Session, Depends(get_db)]):
    """Selected market plus the vocabulary it drives.

    `supported` and `offers_eeo` ride along so the picker and the EEO section
    are driven by one response — the frontend must never hardcode the market
    list or decide for itself whether to show demographic questions.
    """
    setting = market_settings.get_market(db)
    return {
        "key": "market",
        "value": setting,
        "supported": [
            {"key": k, "label": markets.labels()[k], "currency": markets.currency_for(k),
             "offers_eeo": markets.offers_eeo(k)}
            for k in markets.keys()
        ],
        "currency": markets.currency_for(setting.market),
        "offers_eeo": markets.offers_eeo(setting.market),
    }


@router.put("/market")
def put_market(payload: MarketPayload, db: Annotated[Session, Depends(get_db)]):
    setting = market_settings.set_market(payload.value, db)
    return {
        "key": "market",
        "value": setting,
        "currency": markets.currency_for(setting.market),
        "offers_eeo": markets.offers_eeo(setting.market),
    }


@router.get("/auto-apply")
def get_auto_apply(db: Annotated[Session, Depends(get_db)]):
    return {"key": "auto_apply", "value": auto_apply_settings.get_settings(db)}


@router.put("/auto-apply")
def put_auto_apply(payload: AutoApplyPayload, db: Annotated[Session, Depends(get_db)]):
    return {"key": "auto_apply", "value": auto_apply_settings.set_settings(payload.value, db)}


@router.get("/eeo-consent")
def get_eeo_consent(db: Annotated[Session, Depends(get_db)]):
    return {"key": "eeo_consent", "value": eeo_consent.get_consent(db)}


@router.put("/eeo-consent")
def put_eeo_consent(payload: EeoConsentPayload, db: Annotated[Session, Depends(get_db)]):
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


@router.get("/openai", response_model=OpenAIInfo)
def get_openai_info(db: Annotated[Session, Depends(get_db)]):
    db_openai = model_settings.get_openai_api_key(db)
    db_gemini = model_settings.get_gemini_api_key(db)
    return OpenAIInfo(
        fast_model=model_settings.get_fast_model(db),
        smart_model=model_settings.get_smart_model(db),
        chat_model=model_settings.get_chat_model(db),
        api_key_configured=bool(db_openai or app_settings.openai_api_key),
        gemini_api_key_configured=bool(db_gemini or app_settings.gemini_api_key),
        openai_key_source=(
            "settings" if db_openai
            else "env" if app_settings.openai_api_key else "none"
        ),
        gemini_key_source=(
            "settings" if db_gemini
            else "env" if app_settings.gemini_api_key else "none"
        ),
        model_options=model_settings.usable_option_dicts(db),
        base_url=model_settings.get_base_url(db) or app_settings.openai_base_url or None,
        custom_endpoint=model_settings.using_custom_endpoint(db),
        json_mode=model_settings.get_json_mode(db),
        capabilities=_capability_map(db),
    )


def _capability_map(db: Session) -> dict[str, dict]:
    """Probes for the three configured models only — not every model ever tried."""
    out: dict[str, dict] = {}
    for model in {
        model_settings.get_fast_model(db),
        model_settings.get_smart_model(db),
        model_settings.get_chat_model(db),
    }:
        report = llm_capabilities.load(db, model)
        if report is not None:
            out[model] = asdict(report)
    return out


@router.put("/openai", response_model=OpenAIInfo)
def put_openai_info(payload: ModelSettingsPayload, db: Annotated[Session, Depends(get_db)]):
    # A key field the client did not send must survive this write. `set_models`
    # passes its key args to `_set_raw_value`, which DELETES the row on
    # None/"" — so we re-supply the stored value for any omitted field rather
    # than letting a model-only update wipe the key.
    sent = payload.model_fields_set
    openai_key = (
        payload.openai_api_key
        if "openai_api_key" in sent
        else model_settings.get_openai_api_key(db)
    )
    gemini_key = (
        payload.gemini_api_key
        if "gemini_api_key" in sent
        else model_settings.get_gemini_api_key(db)
    )
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
    try:
        model_settings.set_models(
            payload.fast_model,
            payload.smart_model,
            db,
            chat_model=payload.chat_model,
            openai_api_key=openai_key,
            gemini_api_key=gemini_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return get_openai_info(db)


class ProbePayload(BaseModel):
    model: str


class SyncPayload(BaseModel):
    provider: Literal["openai", "gemini"]


class ExtraModelPayload(BaseModel):
    id: str
    provider: Literal["openai", "gemini"]
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
    """List chat-like models from OpenAI or Gemini for discovery (+ adds to catalog)."""
    try:
        if payload.provider == "openai":
            discovered = llm.list_openai_models()
        else:
            discovered = llm.list_gemini_models()
    except LLMProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    in_catalog = model_settings.usable_ids(db)
    return {
        "models": [
            {**row, "in_catalog": row["id"] in in_catalog}
            for row in discovered
        ]
    }


@router.post("/openai/models", response_model=OpenAIInfo)
def add_catalog_model(payload: ExtraModelPayload, db: Annotated[Session, Depends(get_db)]):
    try:
        model_settings.add_extra_model(
            db, payload.id, payload.provider, label=payload.label
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return get_openai_info(db)


@router.delete("/openai/models/{model_id:path}", response_model=OpenAIInfo)
def remove_catalog_model(model_id: str, db: Annotated[Session, Depends(get_db)]):
    try:
        model_settings.remove_extra_model(db, model_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return get_openai_info(db)
