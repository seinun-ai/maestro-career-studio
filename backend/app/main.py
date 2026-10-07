import logging
import posixpath
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import settings as app_settings
from app.origin_guard import OriginGuardMiddleware

from app.routers import (
    role_categories,
    agent_runs,
    applications,
    ats,
    automations,
    autofill,
    base_resumes,
    career_kb,
    chat,
    countries,
    explore,
    exports,
    filled_answers,
    jobs,
    proposals,
    qa,
    referrals,
    resume_lint,
    resume_versions,
    setup,
    settings,
    sync,
    tailoring_sessions,
    templates,
    version,
)
from app.services import automations as automation_prompts
from app.services import http_client, memory, seeding, tracing
from app.services.llm import LLMProviderError
from app.services.sync.hooks import NotOwnedHere

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
            "in Settings › AI & models in the web app, or set OPENAI_API_KEY in "
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
    from app.services.sync import status

    http_client.repair_proxy_env()  # before the first LLM call or model download
    seeding.run_startup()
    status.ensure_machine_id()
    _log_llm_config()
    automation_prompts.load_cards()  # a malformed skill file fails startup, not a page
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

# Added AFTER CORS and BEFORE the host middleware, which puts it in the middle
# of the stack: Host → Origin → CORS. CORS alone leaves a cross-origin POST's side
# effect intact and withholds only the reply, which against a zero-auth API is
# the whole attack. See app/origin_guard.py.
app.add_middleware(OriginGuardMiddleware, allowed_origins=ALLOWED_ORIGINS)

_HOST_MARKS = (" ", "/", "@", "\\")
_PATH_MARKS = ("..", "//", "\\", "%")


def _hostname(value: str) -> str:
    """One hostname, with a numeric port removed. Empty when it is not that."""
    text = value.strip()
    if not text or any(mark in text for mark in _HOST_MARKS):
        return ""
    host, separator, port = text.partition(":")
    if not separator:
        return text
    if host and port.isdigit():
        return host
    return ""


def _presented_host(scope: Scope) -> str:
    values = Headers(scope=scope).getlist("host")
    if len(values) != 1:
        return ""
    return _hostname(values[0])


def _under_sync(path: str) -> bool:
    """True only for a path that is, and stays, under /api/sync/, other than the always-on
    copy's own loopback-only /api/sync/round."""
    if not path.startswith("/api/sync/"):
        return False
    if any(mark in path for mark in _PATH_MARKS):
        return False
    normal = posixpath.normpath(path)
    return normal.startswith("/api/sync/") and normal != "/api/sync/round"


def _admits_public_host(scope: Scope) -> bool:
    """settings.sync_public_host, read now, and only on a sync path."""
    if scope["type"] not in ("http", "websocket"):
        return False
    configured = _hostname(app_settings.sync_public_host).casefold()
    if not configured:
        return False
    if _presented_host(scope).casefold() != configured:
        return False
    return _under_sync(scope.get("path") or "")


class SyncPublicHostMiddleware:
    """TrustedHostMiddleware, plus one hostname on /api/sync/ only.

    The extra hostname is not added to allowed_hosts. It is read from settings
    on each request, because allowed_hosts itself was captured at import.
    """

    def __init__(self, app: ASGIApp, allowed_hosts: list[str]) -> None:
        self.app = app
        self.trusted = TrustedHostMiddleware(app, allowed_hosts=allowed_hosts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if _admits_public_host(scope):
            await self.app(scope, receive, send)
            return
        await self.trusted(scope, receive, send)


# Added LAST, so it wraps everything and runs FIRST: a forged Host is rejected
# before any handler, and the 400 deliberately carries no CORS headers.
# This is the DNS-rebinding defence — see config.allowed_hosts for why CORS
# alone cannot provide it. sync_public_host is a second door for /api/sync/
# only, and the wrapper reads it per request rather than widening allowed_hosts.
# Starlette's add_middleware PREPENDS, so the order these three calls appear in
# is the reverse of the order they run in; the order is pinned by
# test_the_host_check_outranks_the_origin_check.
app.add_middleware(SyncPublicHostMiddleware, allowed_hosts=app_settings.allowed_hosts)


@app.exception_handler(NotOwnedHere)
async def not_owned_here_handler(request: Request, exc: NotOwnedHere):
    return JSONResponse(status_code=409, content={"detail": str(exc), "owner": exc.owner})


@app.exception_handler(LLMProviderError)
async def llm_provider_error_handler(request: Request, exc: LLMProviderError):
    """Upstream model provider failed → 502 whose `detail` is the error's user
    sentence (`str(exc)`: "The AI model didn't answer (…)", or the no-key
    sentence). What the provider actually said is `exc.provider_detail`, and it
    goes to the log, never to the UI.

    Every LLM-backed endpoint needs this and only career_kb had it, so an outage
    or an exhausted quota surfaced everywhere else as a bare 500 whose body
    carries no `detail` for the UI to show. Handled centrally rather than
    per-router: the provider boundary is one place, the routers are a dozen.
    Routers that catch RuntimeError themselves still win — they run first.
    """
    logger.warning("LLM provider failure on %s %s: %s", request.method, request.url.path,
                   getattr(exc, "provider_detail", None) or exc)
    return JSONResponse(status_code=502, content={"detail": str(exc)})


app.include_router(role_categories.router)
app.include_router(countries.router)
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
app.include_router(automations.router)
app.include_router(filled_answers.router)
app.include_router(agent_runs.router)
app.include_router(sync.router)
app.include_router(sync.setup_router)


@app.get("/health")
def healthcheck():
    return {"status": "ok"}


@app.get("/health/memory")
def health_memory():
    return memory.readout()


@app.get("/api/health", include_in_schema=False)
def healthcheck_api():
    """Alias. Every other route lives under /api/*, so this is the path both
    people and agents guess first — and the only one of the two the frontend
    dev proxy (which forwards /api/* alone) can reach."""
    return healthcheck()
