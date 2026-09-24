import json
import os
from pathlib import Path
from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

# XCharter, vendored beside this package so the render path never depends on a
# TeX Live installation or a per-machine env var. Resolved from __file__ so it
# works from a source checkout, an editable install, a wheel, and the container
# alike. See app/assets/fonts/xcharter/README.md.
VENDORED_FONTS_DIR = Path(__file__).resolve().parent / "assets" / "fonts" / "xcharter"

# The one relational file (SYSTEM.md §3), created under data_dir; its -wal/-shm
# sidecars sit beside it. app/db.py imports this so every path that names the
# file (engine, backup) spells it the same way.
DB_FILENAME = "maestro_cs.sqlite3"


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
    # Empty = derived from data_dir after validation (see _derive_database_url).
    # Set it only to point at another FILE: sqlite:////absolute/path.sqlite3.
    # Any non-sqlite URL, Postgres included, is refused on purpose: SQLite is the
    # only database (SYSTEM.md §3).
    database_url: str = ""
    # WAL is right on a local disk. The escape hatch exists for filesystems whose
    # shared-memory semantics SQLite cannot trust (some Docker Desktop bind-mount
    # backends): set DELETE there. Only these two values are accepted.
    sqlite_journal_mode: str = "WAL"
    fast_model: str = "gpt-5.6-luna"
    smart_model: str = "gpt-5.6-luna"
    # Chat agent needs streaming tool calls; eligibility is the tools probe.
    chat_model: str = "gpt-5.6-luna"

    # Langfuse LLM tracing — off unless both keys AND the host are set
    # (services/tracing.py). No Langfuse stack ships with this repo (a bundled
    # one meant publishing its session-signing secrets), so there is no default
    # host: point it at an instance you run, or at Langfuse Cloud's URL.
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = ""

    @field_validator("database_url")
    @classmethod
    def _only_sqlite(cls, value: str) -> str:
        # An allowlist, not a Postgres blocklist: any non-sqlite URL, Postgres
        # included (either spelling), is refused, and so is a string SQLAlchemy
        # cannot parse at all, under the one message. Empty is left alone so
        # _derive_database_url can fill it in.
        if not value:
            return value
        try:
            backend = make_url(value).get_backend_name()
        except ArgumentError:
            backend = None
        if backend != "sqlite":
            raise ValueError(
                "DATABASE_URL is not a SQLite file URL; Postgres is no longer a runtime "
                "database. Leave DATABASE_URL unset. A database from v0.3.0 or older is "
                "imported by v0.4.0 (docs/UPDATING.md)."
            )
        return value

    @field_validator("sqlite_journal_mode")
    @classmethod
    def _journal_mode_is_known(cls, value: str) -> str:
        mode = value.strip().upper()
        if mode not in {"WAL", "DELETE"}:
            raise ValueError("SQLITE_JOURNAL_MODE must be WAL or DELETE")
        return mode

    @model_validator(mode="after")
    def _derive_database_url(self) -> "Settings":
        # resolve() the directory itself, not just the URL: a relative DATA_DIR
        # must not mean three different files for uvicorn, alembic and a script
        # started from different directories, and settings.data_dir (the
        # import marker lives under it) must never disagree with the URL.
        self.data_dir = self.data_dir.resolve()
        if not self.database_url:
            self.database_url = f"sqlite:///{self.data_dir / DB_FILENAME}"
        return self

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

    # Web origins allowed to call the API from a browser. Two readers, one list
    # (app/main.py ALLOWED_ORIGINS): CORS decides what may be READ, and
    # OriginGuardMiddleware decides what may RUN — a cross-origin POST's side
    # effect lands whether or not CORS lets the page read the answer.
    #
    # This is the ORIGIN twin of `allowed_hosts` and the two move together: if
    # you front the app with a reverse proxy and add a hostname there, add the
    # matching scheme+host+port here or the browser's calls will 403. A host is
    # `studio.lan`; an origin is `http://studio.lan`. Extension origins are NOT
    # configured here — they come from `maestro_cs_extension_ids` above, so the
    # exact-id rule cannot be widened by editing an origin list.
    allowed_web_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    @field_validator(
        "allowed_hosts", "maestro_cs_extension_ids", "allowed_web_origins",
        mode="before",
    )
    @classmethod
    def _parse_str_list(cls, value):
        return _split_env_list(value)

    # Write the FULL prompt and response of every LLM call to logs/llm_calls.
    #
    # Off by default since the 2026-08-19 audit (SEC-08). It used to be
    # unconditional — outside the Langfuse tracing block, so it ran whether or
    # not tracing was configured — which made a permanent second copy of every
    # resume, job description, work-authorization answer and generated
    # screening answer, in a directory any backup sweeps up. For a local-first
    # privacy product that was the loudest contradiction in the repo.
    #
    # Turn it on to debug a prompt, then turn it off: the metadata log (model,
    # duration, outcome, sizes, sha256) is enough to see WHAT happened, and
    # this is only for seeing what was SAID. Files are 0600 either way.
    llm_log_content: bool = False

    app_root: Path = Path("/app")
    # Everything relational lives in ONE file under here (SYSTEM.md §3):
    # maestro_cs.sqlite3 plus its -wal/-shm sidecars. Bind-mounted from ./data
    # in compose; override with DATA_DIR when running the backend yourself.
    data_dir: Path = Path("/app/data")
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

    # Explicit pdflatex binary. When set it WINS and is never searched around:
    # a wrong value makes the probe report unavailable with the reason, exactly
    # like the MCPB shim treats a wrong Docker path. Unset = search PATH plus the
    # known TeX homes (app/services/engines.py). Doubles as the test switch for
    # a TeX-less host: MAESTRO_CS_PDFLATEX=/nonexistent.
    maestro_cs_pdflatex: Path | None = None

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
