import logging
import posixpath
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import settings as app_settings
from app.origin_guard import OriginGuardMiddleware
from app.services.sync.seal import HEADER as SEAL_HEADER

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


def _public_host_set() -> bool:
    """settings.sync_public_host, read now, names one host."""
    return bool(_hostname(app_settings.sync_public_host))


def _on_public_host(scope: Scope) -> bool:
    """That name matches the one presented Host. WebSocket and non-sync paths only."""
    if scope["type"] not in ("http", "websocket"):
        return False
    configured = _hostname(app_settings.sync_public_host).casefold()
    if not configured:
        return False
    return _presented_host(scope).casefold() == configured


def _public_sync_http(scope: Scope) -> bool:
    """A sync-shaped http path while the public host is configured.

    The Host header is not consulted. A published listener forwards the client's.
    """
    if scope.get("type") != "http" or not _public_host_set():
        return False
    return _sync_shaped(scope.get("path") or "")


def _sync_shaped(path: str) -> bool:
    return path == "/api/sync" or path.startswith("/api/sync/")


def _admits_public_host(scope: Scope) -> bool:
    """The published name, and only on a path that stays under /api/sync/."""
    if not _on_public_host(scope):
        return False
    return _under_sync(scope.get("path") or "")


_SEAL_NAME = SEAL_HEADER.lower().encode("ascii")
_SYNC_FAILED = "A sync request failed."


def _response_sealed(message: dict) -> bool:
    headers = message.get("headers") or ()
    return any(name.lower() == _SEAL_NAME for name, _value in headers)


def _without_vary(message: dict) -> dict:
    """Drop ``Vary`` from one ASGI start message. Other messages pass through.

    Starlette 1.7's CORS middleware sets ``Vary: Origin`` on every non-preflight
    response, including one with no Origin. Older Starlette does that only when
    it reflects an allowed Origin.
    """
    if message.get("type") != "http.response.start":
        return message
    headers = message.get("headers")
    if not headers:
        return message
    kept = [(name, value) for name, value in headers if name.lower() != b"vary"]
    if len(kept) == len(headers):
        return message
    return {**message, "headers": kept}


class _SyncChannelSend:
    """On ``/api/sync``, the response that leaves is the one the route built.

    The published-name 404 is ``Response(status_code=404)`` sent from outside
    CORS, so it has no ``Vary``. A response that did pass through CORS would
    otherwise carry ``Vary: Origin`` and no longer match it, and a sealed
    response would carry that header out to the proxy.
    """

    def __init__(self, send: Send) -> None:
        self._send = send

    async def __call__(self, message: dict) -> None:
        await self._send(_without_vary(message))


class _BareUnlessSealed:
    """On the published name, a response without the seal header is the empty 404.

    The replacement is Starlette's ``Response(status_code=404)``, the same call
    the sync routes use, so the status, body, and headers match that 404.
    """

    def __init__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self._scope = scope
        self._receive = receive
        self._send = send
        self._forward = True
        self.started = False

    async def __call__(self, message: dict) -> None:
        kind = message["type"]
        if kind == "http.response.start":
            self.started = True
            await self._start(message)
            return
        if kind == "http.response.body" and not self._forward:
            return
        await self._send(message)

    async def _start(self, message: dict) -> None:
        if _response_sealed(message):
            await self._send(message)
            return
        self._forward = False
        await Response(status_code=404)(self._scope, self._receive, self._send)


class SyncPublicHostMiddleware:
    """TrustedHostMiddleware, plus the sync tree while a public host is configured.

    The extra hostname is not added to allowed_hosts. It is read from settings
    on each request, because allowed_hosts itself was captured at import.
    While it is set, every http path under ``/api/sync`` is public whatever Host
    says. A path the tree does not admit is the empty 404 directly. An admitted
    path has its ``send`` wrapped: anything without the seal header, including a
    raise before a response starts, leaves as that same 404. Every http response
    on a sync-shaped path also drops ``Vary`` on the way out, so a CORS
    middleware that adds ``Vary: Origin`` cannot split that 404 in two or add a
    header to a sealed response.
    """

    def __init__(self, app: ASGIApp, allowed_hosts: list[str]) -> None:
        self.app = app
        self.trusted = TrustedHostMiddleware(app, allowed_hosts=allowed_hosts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") == "http" and _sync_shaped(scope.get("path") or ""):
            send = _SyncChannelSend(send)
        if _public_sync_http(scope):
            await self._serve_public_sync(scope, receive, send)
            return
        # WebSocket on the published name still follows the host. Http sync does not.
        if _admits_public_host(scope):
            await self.app(scope, receive, send)
            return
        await self.trusted(scope, receive, send)

    async def _serve_public_sync(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not _under_sync(scope.get("path") or ""):
            await Response(status_code=404)(scope, receive, send)
            return
        outbound = _BareUnlessSealed(scope, receive, send)
        try:
            await self.app(scope, receive, outbound)
        except Exception:
            if outbound.started:
                raise
            logger.error(_SYNC_FAILED)
            await Response(status_code=404)(scope, receive, send)


# Added LAST, so it wraps everything and runs FIRST: a forged Host is rejected
# before any handler, and the 400 deliberately carries no CORS headers.
# This is the DNS-rebinding defence — see config.allowed_hosts for why CORS
# alone cannot provide it. While sync_public_host is set, every http /api/sync
# path is that door whatever Host says. The wrapper reads it per request.
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
