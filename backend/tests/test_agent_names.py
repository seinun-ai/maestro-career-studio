"""The server's agent names agree with the web app's (`frontend/lib/agent-name.ts`).

One table in two languages: the timeline the server writes and the by-lines
the web renders must name the same client the same way. The TypeScript runs
under node's own type stripping (`tests/node_ts.py`): with no such node the
parity half skips locally and FAILS in CI, where the backend job installs node.
"""
from app.services.agent_names import agent_display_name, written_by
from tests.node_ts import ts_map

NAMES = [
    "claude-ai", "Claude Desktop", "codex-mcp-client", "openai-mcp", "ChatGPT",
    "cursor-vscode", "precursor-bot", "windsurf", "gemini-cli", "mcp", "mcp-client",
    "my-agent", "my_agent tool", "iPhone-helper", "you", "", "  ", "ai-api-cli",
]


def _typescript_names(names: list[str]) -> list[str | None]:
    return ts_map("./lib/agent-name.ts", "agentDisplayName", names)


def test_the_server_names_agents_as_the_web_app_does():
    assert [agent_display_name(name) for name in NAMES] == _typescript_names(NAMES)


def test_known_clients_by_product_and_unknown_ones_in_words():
    assert agent_display_name("claude-ai") == "Claude"
    assert agent_display_name("openai-mcp") == "ChatGPT"
    assert agent_display_name("precursor-bot") == "Precursor Bot"
    assert agent_display_name("mcp") is None
    assert agent_display_name("ai-api-cli") == "AI API CLI"


def test_written_by_names_the_writer_or_nobody():
    assert written_by("mcp", "claude-ai") == "Claude"
    assert written_by("mcp", None) == "a connected agent"
    assert written_by("mcp", "mcp") == "a connected agent"
    assert written_by("chat", None) == "the Assistant"
    assert written_by("consolidated", None) is None
    assert written_by(None, None) is None
