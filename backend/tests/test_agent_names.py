"""The server's agent names agree with the web app's (`frontend/lib/agent-name.ts`).

One table in two languages: the timeline the server writes and the by-lines
the web renders must name the same client the same way. The TypeScript runs
under node's own type stripping; with no node, or a node too old to strip
types, the parity half is skipped and the Python half still runs.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.services.agent_names import agent_display_name, written_by

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

NAMES = [
    "claude-ai", "Claude Desktop", "codex-mcp-client", "openai-mcp", "ChatGPT",
    "cursor-vscode", "precursor-bot", "windsurf", "gemini-cli", "mcp", "mcp-client",
    "my-agent", "my_agent tool", "iPhone-helper", "you", "", "  ", "ai-api-cli",
]


def _typescript_names(names: list[str]) -> list[str | None]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    probe = subprocess.run([node, "-p", "Boolean(process.features.typescript)"],
                           capture_output=True, text=True, check=False)
    if probe.stdout.strip() != "true":
        pytest.skip("this node cannot strip TypeScript types")
    script = (
        "import('./lib/agent-name.ts').then((m) => process.stdout.write("
        f"JSON.stringify({json.dumps(names)}.map(m.agentDisplayName))))"
    )
    done = subprocess.run([node, "-e", script], cwd=FRONTEND, capture_output=True,
                          text=True, check=True)
    return json.loads(done.stdout)


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
