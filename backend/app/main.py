import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import settings as app_settings
from app.origin_guard import OriginGuardMiddleware

from app.routers import (
    role_categories,
    applications,
    ats,
    autofill,
    base_resumes,
    career_kb,
    chat,
    explore,
    exports,
    jobs,
    proposals,
    qa,
    referrals,
    resume_lint,
    resume_versions,
    setup,
    settings,
    tailoring_sessions,
    templates,
    version,
)
from app.services import seeding, tracing
from app.services.llm import LLMProviderError

logger = logging.getLogger(__name__)


def _ensure_app_log_handler(
    app_logger: logging.Logger, root_logger: logging.Logger
) -> bool:
    """Give `app.*` loggers a real handler when nobody else has.

    Uvicorn configures only its own loggers, so without this every app record
    below WARNING fell to Python's lastResort handler and was dropped — which
    kept _log_llm_config()'s one useful line ("api key from settings|env")
    invisible exactly when a stale settings-stored key was silently overriding
    a blank .env. Scoped to the `app` hierarchy on purpose: raising the ROOT
    level to INFO would also turn on per-request noise from libraries (httpx
    logs every request at INFO). A no-op when either logger already has
    handlers (pytest, a custom --log-config), so it cannot double-log.
    """
    if app_logger.handlers or root_logger.handlers:
        return False
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(levelname)s:     %(name)s - %(message)s")
    )
    app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)
    return True


_ensure_app_log_handler(logging.getLogger("app"), logging.getLogger())


def _log_llm_config() -> None:
    """State the effective LLM config once, at startup.

    Misconfiguration here used to be silent until the first tailor, and then
    surfaced as `APIConnectionError: Connection error.` — which points at the
    network, or at the user's key, and never at the truth. Saying it out loud
    turns that into a fact you can read before anything fails.
    """
    from app import config
    from app.services import llm, model_settings

    key_source = (
        "settings" if model_settings.get_openai_api_key() else
        "env" if app_settings.openai_api_key else "NONE"
    )
    endpoint = llm.get_base_url() or "https://api.openai.com/v1 (default)"
    if key_source == "NONE" and not llm.get_base_url():
        logger.warning(
            "No OpenAI API key configured — every LLM feature will fail. Add one "
            "under Settings → Models in the web app, or set OPENAI_API_KEY in "
            ".env and restart."
        )
    else:
        logger.info("LLM endpoint %s, api key from %s", endpoint, key_source)
    if app_settings.llm_log_content:
        # Loud on purpose. This writes resumes, job descriptions, work-auth
        # answers and generated screening answers to disk in cleartext, and the
        # person who turned it on to debug one prompt is exactly the person who
        # will forget it is on.
        logger.warning(
            "LLM_LOG_CONTENT is on: every prompt and response is being written "
            "in full to %s/llm_calls, including resume and job-description "
            "text. This is a debugging mode — turn it off when you are done, "
            "and delete the files.",
            app_settings.logs_dir,
        )
    if config.SCRUBBED_ENV:
        # `VAR: ${VAR:-}` in docker-compose injects empty strings, which SDKs
        # that read os.environ directly treat as configured. See scrub_empty_env.
        logger.debug("Ignored empty env vars: %s", ", ".join(sorted(config.SCRUBBED_ENV)))


@asynccontextmanager
async def lifespan(app: FastAPI):
    seeding.run_startup()
    _log_llm_config()
    yield
    tracing.shutdown()


app = FastAPI(title="Maestro CS API", lifespan=lifespan)

_extension_origins = [
    f"chrome-extension://{ext_id}" for ext_id in app_settings.maestro_cs_extension_ids
]
if not _extension_origins:
    logger.warning(
        "MAESTRO_CS_EXTENSION_IDS is set to an empty value, so no browser "
        "extension can call this API (CORS will reject it). Unsetting it "
        "restores the default, which is the pinned id of the extension in this "
        "repo. The web UI is unaffected."
    )

# ONE definition, two readers: CORSMiddleware decides what may be READ, and
# OriginGuardMiddleware below decides what may RUN. Letting those lists drift
# apart would mean an origin the guard admits but CORS will not answer, or
# worse, the reverse.
ALLOWED_ORIGINS = [
    *app_settings.allowed_web_origins,
    *_extension_origins,
]

app.add_middleware(
    CORSMiddleware,
    # The browser extension (extension/) calls the API directly from its
    # chrome-extension:// origin. Listed by EXACT id: the previous
    # `allow_origin_regex=r"chrome-extension://.*"` trusted every extension the
    # user had installed, and any one of them could read the whole zero-auth API.
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Added AFTER CORS and BEFORE TrustedHost, which puts it in the middle of the
# stack: Host → Origin → CORS. CORS alone leaves a cross-origin POST's side
# effect intact and withholds only the reply, which against a zero-auth API is
# the whole attack. See app/origin_guard.py.
app.add_middleware(OriginGuardMiddleware, allowed_origins=ALLOWED_ORIGINS)

# Added LAST, so it wraps everything and runs FIRST: a forged Host is rejected
# before any handler, and the 400 deliberately carries no CORS headers.
# This is the DNS-rebinding defence — see config.allowed_hosts for why CORS
# alone cannot provide it. Starlette's add_middleware PREPENDS, so the order
# these three calls appear in is the reverse of the order they run in; the
# order is pinned by test_the_host_check_outranks_the_origin_check.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=app_settings.allowed_hosts)


@app.exception_handler(LLMProviderError)
async def llm_provider_error_handler(request: Request, exc: LLMProviderError):
    """Upstream model provider failed → 502 with the provider's own message.

    Every LLM-backed endpoint needs this and only career_kb had it, so an outage
    or an exhausted quota surfaced everywhere else as a bare 500 whose body
    carries no `detail` for the UI to show. Handled centrally rather than
    per-router: the provider boundary is one place, the routers are a dozen.
    Routers that catch RuntimeError themselves still win — they run first, and
    their local wording (e.g. the offending filename) is more useful than this.
    """
    logger.warning("LLM provider failure on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=502, content={"detail": str(exc)})


app.include_router(role_categories.router)
app.include_router(jobs.router)
app.include_router(ats.router)
app.include_router(tailoring_sessions.router)
app.include_router(applications.router)
app.include_router(qa.router)
app.include_router(proposals.router)
app.include_router(referrals.router)
app.include_router(explore.router)
app.include_router(setup.router)
app.include_router(settings.router)
app.include_router(autofill.router)
app.include_router(base_resumes.router)
app.include_router(career_kb.router)
app.include_router(templates.router)
app.include_router(resume_versions.router)
app.include_router(resume_lint.router)
app.include_router(chat.router)
app.include_router(exports.router)
app.include_router(version.router)


@app.get("/health")
def healthcheck():
    return {"status": "ok"}


@app.get("/api/health", include_in_schema=False)
def healthcheck_api():
    """Alias. Every other route lives under /api/*, so this is the path both
    people and agents guess first — and the only one of the two the frontend
    dev proxy (which forwards /api/* alone) can reach."""
    return healthcheck()
