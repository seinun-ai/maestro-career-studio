"""Regression tests for the browser-borne attack surface of a zero-auth API.

Every test here pins a control that was ADDED after the 2026-08-04 pre-publish
security review, i.e. each one failed before its fix. They are grouped in one
module on purpose: the threat model is shared (no authentication, so the browser
and untrusted text are the adversaries) and splitting them across router modules
buries that fact.
"""

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
                "fast_model": "gpt-4o-mini",
                "smart_model": "gpt-4o",
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

