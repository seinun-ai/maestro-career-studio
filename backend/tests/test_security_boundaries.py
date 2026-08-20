"""Regression tests for the browser-borne attack surface of a zero-auth API.

Every test here pins a control that was ADDED after the 2026-08-04 pre-publish
security review, i.e. each one failed before its fix. They are grouped in one
module on purpose: the threat model is shared (no authentication, so the browser
and untrusted text are the adversaries) and splitting them across router modules
buries that fact.
"""

import pathlib
import shutil

import pytest
from fastapi.testclient import TestClient
from jinja2.exceptions import SecurityError

from app.main import app
from app.services import pdf_render
from app.services.template_validation import SAMPLE_RESUME


# --- S1: template source is data, not code ---------------------------------

# Reaches os.popen through attribute traversal on a plain jinja2.Environment.
# Written with the LaTeX delimiters that pdf_render._environment() configures.
SSTI_PAYLOAD = "((( cycler.__init__.__globals__.os.popen('echo pwned').read() )))"


def test_template_source_cannot_reach_python_internals():
    """A hostile template body must raise, not execute.

    Reachable without the owner typing it: importing a template someone shared,
    or prompt-injecting the chat agent, which holds update_template_draft and
    reads untrusted job descriptions.
    """
    with pytest.raises(SecurityError):
        pdf_render.render_tex_from_source(SSTI_PAYLOAD, SAMPLE_RESUME)


def test_sandbox_does_not_break_ordinary_field_access():
    """The sandbox blocks dunder traversal, not the field access templates use."""
    source = (
        r"((( resume.contact.name|latex_escape ))) "
        r"((* for e in resume.experience *))((( e.company )))((* endfor *))"
    )

    out = pdf_render.render_tex_from_source(source, SAMPLE_RESUME)

    assert "Jordan Sample" in out
    assert "Acme Corp" in out


def test_bundled_templates_still_render_under_the_sandbox():
    """Guards the fix itself: swapping in SandboxedEnvironment must be a no-op here."""
    source = (pdf_render.TEMPLATE_DIR / pdf_render.RESUME_TEMPLATE).read_text()

    out = pdf_render.render_tex_from_source(source, SAMPLE_RESUME)

    assert r"\begin{document}" in out
    assert "Jordan Sample" in out


# --- S4: shell escape is never enabled -------------------------------------


def test_pdflatex_argv_always_disables_shell_escape(tmp_path):
    """`\\write18` is command execution; no caller may opt back into it.

    The cover-letter path used to pass no_shell_escape=False. The parameter is
    gone, so this asserts on the only remaining knob: the argv itself.
    """
    argv = pdf_render._pdflatex_argv(tmp_path / "r.tex", tmp_path, "r")

    assert "-no-shell-escape" in argv
    assert "-shell-escape" not in argv


# --- S5: a template may not READ the filesystem either ---------------------
#
# `-no-shell-escape` blocks \write18, i.e. command execution. It does nothing
# about TeX's own file primitives: \input, \include, \verbatiminput and friends
# open whatever the process can open. Jinja's SandboxedEnvironment does not help
# — it constrains the TEMPLATE language, and these primitives are in the .tex
# that Jinja has already finished producing.
#
# That mattered because template source is writable from the web editor, chat,
# and MCP, and the backend user has every PII directory bind-mounted. Confirmed
# by the 2026-08-19 audit and reproduced here before the fix: a template
# containing \verbatiminput{<absolute path>} put the file's text in the PDF.
#
# The fix is kpathsea's paranoid mode, passed in the compile environment.
# Full isolation (a secretless, networkless render worker) is the real answer
# and is tracked post-publish; this bounds the damage in the meantime.


def test_a_template_cannot_read_a_file_outside_its_output_directory(tmp_path):
    """The SEC-03 repro, inverted into a regression test."""
    pdfplumber = pytest.importorskip("pdfplumber")
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is not installed")

    secret = tmp_path / "not_for_the_pdf.txt"
    secret.write_text("CANARY_ABSOLUTE_READ\n")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    tex = (
        "\\documentclass{article}\n"
        "\\usepackage{verbatim}\n"
        "\\begin{document}\n"
        "Rendered.\n"
        f"\\verbatiminput{{{secret}}}\n"
        "\\end{document}\n"
    )

    # The read failing is one acceptable outcome; a PDF that simply does not
    # contain the secret is the other. Both mean the same thing, and which one
    # you get depends on the TeX distribution's error handling.
    try:
        pdf = pdf_render.compile_pdf(tex, out_dir, stem="probe")
    except RuntimeError:
        return

    with pdfplumber.open(pdf) as doc:
        text = "\n".join((page.extract_text() or "") for page in doc.pages)

    assert "CANARY_ABSOLUTE_READ" not in text, (
        "a template read a file outside its output directory and embedded it "
        "in the PDF — openin_any is not restricting input"
    )


def test_every_pdflatex_call_site_passes_the_hardened_environment():
    """There is more than one, and the second one was missed.

    `compile_pdf` is the APPLICATION render path. `render_and_compile` is the
    BASE-RESUME one, and it builds its own `subprocess.run` around the same
    `_pdflatex_argv` — so hardening only the first left the whole
    `POST /api/base_resumes/{slug}/render` path (plus MCP `render_base_resume`,
    resume_versions, resume_ops, career_kb and kb_import) reading files exactly
    as before. Found by adversarial review, not by the outcome test below, which
    only ever called `compile_pdf`.

    Keyed on the source so it covers call sites this test file does not
    exercise: every `subprocess.run` in the module must carry `env=`.
    """
    source = pathlib.Path(pdf_render.__file__).read_text()
    calls = source.split("subprocess.run(")[1:]
    assert len(calls) >= 2, "expected at least two pdflatex call sites"
    for i, block in enumerate(calls):
        head = block[: block.index(")\n")]
        assert "env=" in head, (
            f"subprocess.run call #{i + 1} in pdf_render.py has no env= — "
            "paranoid file access is not applied on that path"
        )


def test_the_base_resume_render_path_cannot_read_outside_its_directory(
    tmp_path, monkeypatch
):
    """The same canary, driven through the REAL `render_and_compile`.

    Stubbing `render_document` is what makes this a test of the compile half:
    it stands in for a hostile template body (which chat, MCP and the web
    editor can all write) without needing a Template row, and everything after
    it — including the subprocess call whose `env=` was missing — is the real
    code path.
    """
    pdfplumber = pytest.importorskip("pdfplumber")
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is not installed")

    secret = tmp_path / "base_render_secret.txt"
    secret.write_text("CANARY_BASE_RENDER\n")

    hostile = pdf_render.RenderedDoc(
        engine="latex",
        source_text=(
            "\\documentclass{article}\n"
            "\\usepackage{verbatim}\n"
            "\\begin{document}\n"
            "Rendered.\n"
            f"\\verbatiminput{{{secret}}}\n"
            "\\end{document}\n"
        ),
    )
    monkeypatch.setattr(pdf_render, "render_document", lambda *a, **k: hostile)

    out_dir = tmp_path / "out"
    pdf_path = out_dir / "resume.pdf"
    try:
        pdf_render.render_and_compile({}, out_dir / "resume.tex", pdf_path)
    except RuntimeError:
        return  # refusing to compile is an acceptable outcome

    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join((page.extract_text() or "") for page in pdf.pages)

    assert "CANARY_BASE_RENDER" not in text, (
        "render_and_compile embedded a file from outside its output directory — "
        "its subprocess.run is missing env=_compile_env(...)"
    )


def test_the_compile_environment_pins_paranoid_file_access(tmp_path):
    """Pins the mechanism, not just the outcome.

    The outcome test above needs a TeX install; this one runs everywhere and
    names the three variables, so a future refactor that drops `env=` from the
    subprocess call fails loudly instead of silently reopening the read.
    """
    env = pdf_render._compile_env(tmp_path)

    assert env["openin_any"] == "p"
    assert env["openout_any"] == "p"
    # Paranoid mode restricts ABSOLUTE input paths to under TEXMFOUTPUT, and
    # compile_pdf passes an absolute \input{...} of the staged file — so
    # without this the bundled templates would stop compiling.
    assert env["TEXMFOUTPUT"] == str(tmp_path)


# --- S2: Host header validation (DNS rebinding) ----------------------------


def test_forged_host_header_is_rejected():
    """DNS rebinding makes an attacker page same-origin, so CORS never runs.

    The Host header is the only thing left that still names the attacker.
    """
    response = TestClient(app).get("/health", headers={"Host": "evil.example"})

    assert response.status_code == 400


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "backend"])
def test_expected_hosts_still_pass(host):
    """The compose stack's real Hosts: browser → localhost/127.0.0.1, Next proxy → backend."""
    response = TestClient(app).get("/health", headers={"Host": host})

    assert response.status_code == 200


def test_host_check_ignores_the_port():
    """Published ports differ (8001 host, 8000 container); the hostname is what matters."""
    response = TestClient(app).get("/health", headers={"Host": "localhost:8001"})

    assert response.status_code == 200


# --- S2: base_url decides where the API key is sent ------------------------


@pytest.mark.parametrize("bad", ["file:///etc/passwd", "notaurl", "ftp://x/y", "//evil.example"])
def test_base_url_rejects_non_http_schemes(db_session, bad):
    from app.services import model_settings

    with pytest.raises(ValueError):
        model_settings.set_base_url(db_session, bad)


@pytest.mark.parametrize(
    "good", ["http://host.docker.internal:11434/v1", "https://openrouter.ai/api/v1"]
)
def test_base_url_accepts_real_endpoints(db_session, good):
    from app.services import model_settings

    assert model_settings.set_base_url(db_session, good) == good


def test_base_url_can_be_cleared(db_session):
    from app.services import model_settings

    model_settings.set_base_url(db_session, "http://localhost:11434/v1")

    assert model_settings.set_base_url(db_session, "") is None


def test_put_openai_rejects_a_bad_base_url_with_400(db_session):
    from app.db import get_db

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        response = TestClient(app).put(
            "/api/settings/openai",
            json={
                "fast_model": "gemini-3.5-flash-lite",
                "smart_model": "gpt-5.6-luna",
                "base_url": "file:///etc/passwd",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400


# --- S3: only the configured extension may call the API --------------------


def test_arbitrary_extension_origin_is_not_reflected():
    """`chrome-extension://.*` used to trust every extension the user had installed."""
    response = TestClient(app).get(
        "/health", headers={"Origin": "chrome-extension://someotherextensionid"}
    )

    assert "access-control-allow-origin" not in {k.lower() for k in response.headers}


def test_web_ui_origin_is_still_allowed():
    response = TestClient(app).get("/health", headers={"Origin": "http://localhost:3000"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


# --- S4: a disallowed Origin is REFUSED, not merely unreadable -------------
#
# CORS decides whether a hostile page may READ the response. It does not stop
# the request from running: a form or multipart POST is a "simple request" the
# browser sends cross-origin without a preflight, so the side effect lands and
# only the reply is withheld. Against a zero-auth local API that is the whole
# attack — mutate a known object, spend the user's LLM budget, fill the disk.
# So an Origin that is present and not on the allowlist is rejected outright.
#
# Absent Origin is ALLOWED on purpose: MCP over httpx, curl, and the container
# healthcheck send none, and they are not browsers. The header is only ever
# attached by a browser, so "present and wrong" is the browser saying which
# page it came from.


def _extension_origin() -> str:
    from app.config import settings as app_settings

    return f"chrome-extension://{app_settings.maestro_cs_extension_ids[0]}"


@pytest.mark.parametrize(
    "method", ["get", "post", "patch", "put", "delete"]
)
def test_hostile_origin_is_refused_on_every_method(method):
    """Not just the mutating ones — a hostile GET still costs money and leaks timing."""
    response = getattr(TestClient(app), method)(
        "/health", headers={"Origin": "https://evil.example"}
    )

    assert response.status_code == 403


def test_absent_origin_is_allowed():
    """MCP over httpx, curl and the healthcheck send no Origin and are not browsers."""
    response = TestClient(app).get("/health")

    assert response.status_code == 200


@pytest.mark.parametrize(
    "origin", ["http://localhost:3000", "http://127.0.0.1:3000"]
)
def test_web_origins_pass_the_gate(origin):
    """The web UI's own calls arrive through the Next proxy carrying this Origin."""
    response = TestClient(app).get("/health", headers={"Origin": origin})

    assert response.status_code == 200


def test_the_pinned_extension_origin_passes_the_gate():
    response = TestClient(app).get("/health", headers={"Origin": _extension_origin()})

    assert response.status_code == 200


def test_null_origin_is_refused():
    """A sandboxed iframe or a file:// page sends `null`; it is not on the list."""
    response = TestClient(app).get("/health", headers={"Origin": "null"})

    assert response.status_code == 403


def test_a_refused_origin_gets_no_cors_headers():
    """The gate runs OUTSIDE CORSMiddleware, so the refusal cannot be read either."""
    response = TestClient(app).get("/health", headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in {k.lower() for k in response.headers}


def test_a_prefix_of_an_allowed_origin_is_still_refused():
    """Exact match, never `startswith` — `http://localhost:3000.evil.example` is not us."""
    response = TestClient(app).get(
        "/health", headers={"Origin": "http://localhost:3000.evil.example"}
    )

    assert response.status_code == 403


def test_the_origin_gate_covers_the_websocket_scope_too():
    """Unreachable today (no WS routes) and written anyway.

    `TrustedHostMiddleware` guards both scopes. If the gate guarded only
    `http`, a WebSocket route added later would inherit the Host check and
    silently not inherit this one — and `Origin` is the only thing naming the
    page that opened the socket. Asserted at the ASGI layer because there is no
    route to drive it through.
    """
    import asyncio

    from app.origin_guard import OriginGuardMiddleware

    sent: list[dict] = []

    async def app(scope, receive, send):  # pragma: no cover - must not run
        raise AssertionError("a hostile origin reached the app over websocket")

    async def receive():  # pragma: no cover - never awaited
        return {}

    async def send(message):
        sent.append(message)

    guard = OriginGuardMiddleware(app, allowed_origins=["http://localhost:3000"])
    scope = {"type": "websocket", "headers": [(b"origin", b"https://evil.example")]}

    asyncio.run(guard(scope, receive, send))

    assert sent == [{"type": "websocket.close", "code": 1008}]


def test_the_origin_allowlist_is_configured_not_hardcoded():
    """A reverse-proxy user adds a hostname to ALLOWED_HOSTS; the origin must follow.

    `allowed_hosts` has always been configurable, so hardcoding its origin twin
    would 403 every browser call in the one deployment shape the config comments
    tell people how to set up.
    """
    from app.config import settings as app_settings
    from app.main import ALLOWED_ORIGINS

    for origin in app_settings.allowed_web_origins:
        assert origin in ALLOWED_ORIGINS
    assert _extension_origin() in ALLOWED_ORIGINS


def test_the_origin_gate_and_cors_read_the_same_list():
    """Two readers, one list — a drift lets the gate admit what CORS will not answer."""
    from app.main import ALLOWED_ORIGINS, app

    cors = next(
        m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware"
    )
    guard = next(
        m for m in app.user_middleware if m.cls.__name__ == "OriginGuardMiddleware"
    )

    assert cors.kwargs["allow_origins"] == guard.kwargs["allowed_origins"] == ALLOWED_ORIGINS


def test_the_host_check_outranks_the_origin_check():
    """Order is Host → Origin → CORS. A forged Host loses before Origin is read.

    Pins the middleware ORDER, which is the easy thing to get backwards:
    Starlette's add_middleware prepends, so the LAST one added runs FIRST.
    """
    response = TestClient(app).get(
        "/health",
        headers={"Host": "evil.example", "Origin": "http://localhost:3000"},
    )

    assert response.status_code == 400

