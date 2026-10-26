"""Shared setup for the who-writes route tests (design 2026-10-26): the saved writer, the MCP
origin, and Maestro's model stubbed at `llm._call_model`, BELOW the backstop in `llm.call_openai`.
A stub of `call_openai` itself sits above the guard, so "the model is never reached" would pass
trivially and "runs as today" would never pass through it."""
from app.services import llm, text_settings

MCP = {"X-Maestro-CS-Origin": "mcp"}


def set_writer(client, monkeypatch, tmp_path, writer: str) -> None:
    """Save who writes for a connected agent app, as Settings › Agent apps does."""
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path / "settings")
    response = client.put(
        "/api/settings/mcp-workflow", json={"value": {"hints": True, "writer": writer}}
    )
    assert response.status_code == 200, response.text


def forbid_model(monkeypatch) -> None:
    """Maestro's model must not be reached: the provider call fails the test if it is."""
    def _reached(*_args, **_kwargs):
        raise AssertionError("Maestro's model was reached")

    monkeypatch.setattr(llm, "_call_model", _reached)


def model_replies(monkeypatch, tmp_path, reply) -> list[str]:
    """Maestro's model answers every call with `reply` (a string, or a function of the prompt).
    Returns the prompts it was sent, in order."""
    monkeypatch.setattr(llm.settings, "logs_dir", str(tmp_path / "logs"))  # _log_call's record
    prompts: list[str] = []

    def _answer(prompt, *_args, **_kwargs):
        prompts.append(prompt)
        return (reply(prompt) if callable(reply) else reply), None

    monkeypatch.setattr(llm, "_call_model", _answer)
    return prompts
