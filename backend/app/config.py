import json
import os
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# XCharter, vendored beside this package so the render path never depends on a
# TeX Live installation or a per-machine env var. Resolved from __file__ so it
# works from a source checkout, an editable install, a wheel, and the container
# alike. See app/assets/fonts/xcharter/README.md.
VENDORED_FONTS_DIR = Path(__file__).resolve().parent / "assets" / "fonts" / "xcharter"


def _split_env_list(value, *, extra_separator: str | None = None) -> list[str]:
    """Parse a list-valued env var written as JSON *or* as a delimited string.

    Every list setting here is `NoDecode`, opting out of pydantic-settings'
    automatic JSON decoding: without that, a plain `ALLOWED_HOSTS="a,b"` crashes
    the parse of ALL settings, not just its own field. This is the shared
    lenient parser those fields validate through — commas always separate, plus
    `os.pathsep` for the one field that holds filesystem paths.
    """
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):  # JSON array form (back-compat)
            return [str(v).strip() for v in json.loads(text)]
        chunks = text.split(extra_separator) if extra_separator else [text]
        return [p.strip() for chunk in chunks for p in chunk.split(",") if p.strip()]
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value]
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    gemini_api_key: str = ""
    # Point the OpenAI-compatible client at something other than api.openai.com:
    # Ollama (http://host.docker.internal:11434/v1), LM Studio, vLLM, LiteLLM,
    # OpenRouter. Setting this is what makes the local-first claim literally
    # true — with a local endpoint no resume text leaves the machine. A DB
    # setting (llm.base_url) overrides this env default.
    openai_base_url: str = ""
    database_url: str = "postgresql://app:app@postgres:5432/maestro_cs"
    fast_model: str = "gpt-4o-mini"
    smart_model: str = "gpt-4o"
    # Chat agent needs the OpenAI tools loop; must stay an OpenAI-provider model.
    chat_model: str = "gpt-4o"

    # Langfuse LLM tracing — off unless both keys are set. No Langfuse stack
    # ships with this repo (a bundled one meant publishing its session-signing
    # secrets), so there is no local default host: point this at an instance you
    # run, or leave it empty and let the SDK use Langfuse Cloud.
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = ""

    @field_validator("database_url")
    @classmethod
    def _use_psycopg_v3(cls, value: str) -> str:
        # SQLAlchemy maps the bare "postgresql://" scheme to the psycopg2 driver
        # by default, but we install psycopg v3. Normalize so every consumer
        # (app engine, Alembic, scripts) picks up the v3 dialect.
        if value.startswith("postgresql://"):
            return "postgresql+psycopg://" + value[len("postgresql://") :]
        return value

    # --- Browser-borne attack surface -------------------------------------
    # This API has no authentication by design, so the browser is the only
    # attacker that matters and these two lists are the whole boundary.
    #
    # `allowed_hosts` is checked against the Host header (TrustedHostMiddleware).
    # Without it, DNS rebinding defeats the localhost binding entirely: a page on
    # http://evil.example:8001 whose DNS re-resolves to 127.0.0.1 is SAME-ORIGIN
    # to the browser, so CORS is never consulted and the whole career record is
    # readable. Binding to 127.0.0.1 does not help — the browser is inside.
    # Defaults cover the compose stack (browser → localhost/127.0.0.1, Next
    # server-side proxy → `backend`). Add your own hostname if you front this
    # with a reverse proxy: ALLOWED_HOSTS="localhost,127.0.0.1,backend,studio.lan".
    allowed_hosts: Annotated[list[str], NoDecode] = ["localhost", "127.0.0.1", "backend"]
    # Exact chrome-extension:// origins allowed through CORS, comma-separated.
    # This used to be the regex `chrome-extension://.*`, which trusted EVERY
    # extension the user had installed — any one of them could read the entire
    # profile from the zero-auth API. It stays an exact-id allowlist; the only
    # thing that changed is that the id is now KNOWN AHEAD OF TIME.
    #
    # extension/manifest.json pins a `key`, so the bundled extension hashes to
    # this same id on every machine that loads it unpacked. Defaulting to it is
    # what removes the old four-step dance (load unpacked → copy the id Chrome
    # generated → paste into .env → restart the backend), which failed closed
    # with nothing but CORS errors on the card until you got it right.
    #
    # This does NOT widen the allowlist: it is one exact id, belonging to the
    # extension in this repo. Setting the env var REPLACES this list rather than
    # extending it, which is what a fork (different key → different id) wants.
    # List several comma-separated to admit more than one build — e.g. the
    # unpacked id here alongside a Web Store id, which is assigned by Google and
    # will not match this one.
    maestro_cs_extension_ids: Annotated[list[str], NoDecode] = [
        "pjmfonfapjdabkoicnelpflpjojdjgan"
    ]

    @field_validator("allowed_hosts", "maestro_cs_extension_ids", mode="before")
    @classmethod
    def _parse_str_list(cls, value):
        return _split_env_list(value)

    app_root: Path = Path("/app")
    applications_dir: Path = Path("/app/applications")
    settings_dir: Path = Path("/app/settings")
    logs_dir: Path = Path("/app/logs")
    exports_dir: Path = Path("/app/exports")
    base_resumes_dir: Path = Path("/app/base_resumes")
    kb_documents_dir: Path = Path("/app/kb_documents")
    # Font directories handed to typst.compile(font_paths=...). Defaults to the
    # VENDORED XCharter next to this package (app/assets/fonts/xcharter), so
    # font resolution is identical on every OS, in CI, and in the container with
    # no TeX Live install and no env var. Path-based discovery cannot generalize
    # (TeX lives in a different place on every platform, and the end state has no
    # TeX at all) and typst SILENTLY falls back to embedded fonts for a missing
    # directory — a wrong typeface, not an error. See
    # app/assets/fonts/xcharter/README.md.
    # Override via env for custom fonts, e.g. TYPST_FONT_PATHS="/a:/b".
    # NoDecode: opt out of pydantic-settings' automatic JSON decoding of the env
    # value so a plain (non-JSON) string does not crash ALL settings parsing;
    # the validator below accepts a JSON array OR a comma / os.pathsep separated
    # string.
    typst_font_paths: Annotated[list[Path], NoDecode] = [VENDORED_FONTS_DIR]

    @field_validator("typst_font_paths", mode="before")
    @classmethod
    def _parse_font_paths(cls, value):
        parsed = _split_env_list(value, extra_separator=os.pathsep)
        return [Path(p) for p in parsed] if isinstance(parsed, list) else parsed

    # Default ISO 4217 currency assumed for jobs that disclose a salary amount
    # without a currency code (legacy rows + extraction fallback). Override via
    # HOME_CURRENCY — never hard-code USD at the call site or in migrations.
    home_currency: str = "USD"

    @field_validator("home_currency", mode="before")
    @classmethod
    def _normalize_home_currency(cls, value):
        text = str(value or "USD").strip().upper() or "USD"
        if len(text) != 3 or not text.isalpha():
            raise ValueError(f"home_currency must be a 3-letter ISO 4217 code, got {value!r}")
        return text


def scrub_empty_env() -> list[str]:
    """Delete every environment variable whose value is empty or whitespace.

    **An empty environment variable means UNSET.** `docker-compose.yml` writes
    `VAR: ${VAR:-}` for optional settings, which injects the variable as an EMPTY
    STRING rather than leaving it absent. Third-party SDKs read `os.environ`
    directly — behind this app's settings — and treat `""` as configured:

      - the OpenAI SDK adopted an empty `base_url` (it consults the env only when
        `base_url=None`), so every request URL lost its scheme and surfaced as
        the maddening `APIConnectionError: Connection error.`
      - the Langfuse SDK did the same with `LANGFUSE_HOST`, producing
        `Invalid URL '/api/public/otel/v1/traces': No scheme supplied`

    This app's own `or None` guards cannot prevent either, because those
    libraries never consult app settings. So the rule is enforced once, here, at
    the boundary where the environment becomes configuration and before any
    client is constructed. Returns the names removed, for the startup log.
    """
    removed = [name for name, value in os.environ.items() if not value.strip()]
    for name in removed:
        del os.environ[name]
    return removed


# Pre-rename env aliases (one release). Prefer MAESTRO_CS_*; fall back to
# CAREER_STUDIO_* when the new name is unset.
_ENV_ALIASES = (
    ("MAESTRO_CS_EXTENSION_IDS", "CAREER_STUDIO_EXTENSION_IDS"),
    ("MAESTRO_CS_MCP_PROFILE", "CAREER_STUDIO_MCP_PROFILE"),
    ("MAESTRO_CS_MCP_CLIENT", "CAREER_STUDIO_MCP_CLIENT"),
    ("MAESTRO_CS_PDF_DIR", "CAREER_STUDIO_PDF_DIR"),
    ("MAESTRO_CS_UPLOAD_DIR", "CAREER_STUDIO_UPLOAD_DIR"),
)


def apply_legacy_env_aliases() -> None:
    for new, old in _ENV_ALIASES:
        if not (os.environ.get(new) or "").strip():
            legacy = (os.environ.get(old) or "").strip()
            if legacy:
                os.environ[new] = legacy


# Runs at import, and `app.config` is the first app module imported — so no SDK
# has read os.environ yet. Do not move this below `settings`.
SCRUBBED_ENV = scrub_empty_env()
apply_legacy_env_aliases()

settings = Settings()
