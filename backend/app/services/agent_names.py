"""Who wrote something, in words: the server's twin of `frontend/lib/agent-name.ts`.

An MCP client names itself (`clientInfo.name`: "claude-ai", "codex-mcp-client")
and that raw string is stored as `origin_detail`. The web app maps it for the
rows it renders; the server needs the same words for the text it writes itself
(the Career history timeline). Two languages, one table:
`tests/test_agent_names.py` runs both over the same names and fails when they
disagree, so change them together.
"""
import re

# Known clients by product, matched on a whole word of the name ("precursor-bot"
# is not Cursor).
_KNOWN_WORDS = (
    ("claude", "Claude"),
    ("codex", "Codex"),
    ("chatgpt", "ChatGPT"),
    ("cursor", "Cursor"),
    ("windsurf", "Windsurf"),
    ("gemini", "Gemini"),
)
# Known clients by their whole name.
_KNOWN_NAMES = {"openai-mcp": "ChatGPT"}
# Words that only say "an MCP client": the Python MCP SDK's default name is "mcp".
_GENERIC_WORDS = {"mcp", "client"}
_ACRONYMS = {"ai", "api", "cli", "ide", "mcp"}


def _title_word(word: str) -> str:
    if word.lower() in _ACRONYMS:
        return word.upper()
    if word != word.lower():
        return word  # the client already cased it ("iPhone")
    return word[:1].upper() + word[1:]


def agent_display_name(raw: str | None) -> str | None:
    """"Claude" for "claude-ai"; an unknown name title-cased ("my-agent" → "My
    Agent"), never a slug; None for "you", nothing, or a name that says only
    "an MCP client"."""
    name = (raw or "").strip()
    if not name or name.lower() == "you":
        return None
    words = [w for w in re.split(r"[^\w]+|_", name.lower()) if w]
    known = _known_label(name, words)
    if known or all(word in _GENERIC_WORDS for word in words):
        return known
    return " ".join(_title_word(part) for part in re.split(r"[-_\s]+", name) if part)


def _known_label(name: str, words: list[str]) -> str | None:
    """A known client by its whole name, else by a whole word of it."""
    if name.lower() in _KNOWN_NAMES:
        return _KNOWN_NAMES[name.lower()]
    return next((label for word, label in _KNOWN_WORDS if word in words), None)


def written_by(origin: str | None, origin_detail: str | None) -> str | None:
    """Who wrote a Career history row, for a sentence ("Added by Claude"), or
    None when nobody but the user did (web, import, consolidation)."""
    if origin == "mcp":
        return agent_display_name(origin_detail) or "a connected agent"
    if origin == "chat":
        return "the Assistant"
    return None
