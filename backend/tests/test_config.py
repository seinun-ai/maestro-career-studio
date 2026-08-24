def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")

    from app.config import Settings

    s = Settings()

    assert s.openai_api_key == "sk-test"
    assert s.database_url == "postgresql+psycopg://x/y"
    assert s.fast_model == "gpt-5.6-luna"


def test_typst_font_paths_default_and_env_override(monkeypatch):
    from pathlib import Path
    from app.config import Settings

    # The default assertion must not see a developer's local override.
    monkeypatch.delenv("TYPST_FONT_PATHS", raising=False)
    s = Settings(_env_file=None)
    # Default = the VENDORED fonts beside the package, so no TeX Live install
    # and no env var is needed on any platform. The directory must really exist
    # and hold the OTFs: typst silently falls back to embedded fonts for a
    # missing path, so a broken default would surface as a wrong typeface in a
    # rendered PDF rather than as an error here.
    from app.config import VENDORED_FONTS_DIR

    assert s.typst_font_paths == [VENDORED_FONTS_DIR]
    assert VENDORED_FONTS_DIR.is_dir()
    assert any(VENDORED_FONTS_DIR.glob("XCharter-*.otf"))
    monkeypatch.setenv("TYPST_FONT_PATHS", '["/tmp/fonts", "/tmp/other"]')
    s2 = Settings(_env_file=None)
    assert s2.typst_font_paths == [Path("/tmp/fonts"), Path("/tmp/other")]


def test_typst_font_paths_plain_string_env_does_not_crash(monkeypatch):
    from pathlib import Path
    from app.config import Settings

    # A plain (non-JSON) string previously crashed ALL settings parsing.
    monkeypatch.setenv("TYPST_FONT_PATHS", "/a:/b")
    assert Settings(_env_file=None).typst_font_paths == [Path("/a"), Path("/b")]
    # comma-separated is accepted too
    monkeypatch.setenv("TYPST_FONT_PATHS", "/x,/y")
    assert Settings(_env_file=None).typst_font_paths == [Path("/x"), Path("/y")]


# --- empty env vars mean UNSET (2026-08-05) ----------------------------------
# docker-compose writes `VAR: ${VAR:-}` for every optional setting, which injects
# the variable as an EMPTY STRING rather than leaving it absent. Third-party SDKs
# read os.environ directly, behind this app's settings, and treat "" as
# configured: the OpenAI SDK adopted an empty base_url (every request lost its
# scheme -> "Connection error"), and the Langfuse SDK did the same with its host.
# The app's own `or None` guards could not help, because those libraries never
# consult app settings. So the rule is enforced at the environment boundary.


def test_scrub_empty_env_removes_blank_values_only():
    import os

    from app.config import scrub_empty_env

    os.environ["_CS_BLANK"] = ""
    os.environ["_CS_SPACES"] = "   "
    os.environ["_CS_REAL"] = "value"
    try:
        removed = scrub_empty_env()

        assert "_CS_BLANK" not in os.environ
        assert "_CS_SPACES" not in os.environ
        assert os.environ["_CS_REAL"] == "value"
        assert {"_CS_BLANK", "_CS_SPACES"} <= set(removed)
        assert "_CS_REAL" not in removed
    finally:
        for name in ("_CS_BLANK", "_CS_SPACES", "_CS_REAL"):
            os.environ.pop(name, None)


def test_importing_config_scrubs_an_empty_openai_base_url():
    """The regression that shipped: OPENAI_BASE_URL="" reaching the OpenAI SDK.

    Run in a SUBPROCESS, deliberately. Import-time behavior cannot be tested with
    importlib.reload here: reloading app.config rebuilds `settings` from the
    ambient environment, losing the suite's data-dir overrides, and every later
    test then writes to the container-absolute /app paths. A child process is the
    only honest way to observe what a fresh import does.
    """
    import os
    import subprocess
    import sys
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    env = {
        **os.environ,
        "OPENAI_BASE_URL": "",
        "LANGFUSE_HOST": "   ",
        "OPENAI_API_KEY": "sk-kept",
    }
    code = (
        "import os, app.config; "
        "print(os.environ.get('OPENAI_BASE_URL'), os.environ.get('LANGFUSE_HOST'), "
        "os.environ.get('OPENAI_API_KEY'))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=backend, env=env, capture_output=True, text=True, timeout=180,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "None None sk-kept"
