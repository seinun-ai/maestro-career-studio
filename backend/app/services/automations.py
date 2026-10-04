"""Automations: prompts a user copies into their own agent app.

The skill files under app/automations/skills are the single source of the text
(docs/plans/2026-10-04-automations-page-design.md). A skill with a `metadata`
block is a card; one without (agent-apply-execution) rides on a card through
`include`. Nothing about the user is inserted: the agent reads the brief, caps
and preferences live over MCP, and asks the user when to run.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

SKILLS_DIR = Path(__file__).resolve().parent.parent / "automations" / "skills"

CARD_ORDER = ("mail-status", "job-hunt", "referral-pages", "tailor-run", "apply-session",
              "customize-job-skills")

Kind = Literal["scheduled", "attended", "custom"]
Need = Literal["maestro", "email", "browser", "web"]


class _Meta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    summary: str
    kind: Kind
    needs: list[Need]
    never: str | None = None
    include: list[str] = []


class AutomationCard(BaseModel):
    id: str
    title: str
    summary: str
    kind: Kind
    needs: list[Need]
    never: str | None
    body: str


class AgentApp(BaseModel):
    id: str
    label: str
    reachable: bool
    preamble: str
    attended_preamble: str
    note: str | None


class AutomationCatalog(BaseModel):
    cards: list[AutomationCard]
    apps: list[AgentApp]


_ASK = "First ask me how often and when to run it, then set up the schedule."
_REMOTE = "Needs remote access to Maestro, which isn't available yet."

APPS: tuple[AgentApp, ...] = (
    AgentApp(
        id="claude-desktop", label="Claude Desktop", reachable=True,
        preamble=("Using your Maestro Career Studio connector, set the job below up as a "
                  f"scheduled task. {_ASK}"),
        attended_preamble=(
            "Using your Maestro Career Studio connector, "
            "do the job below with me now."),
        note=None,
    ),
    AgentApp(
        id="codex", label="Codex", reachable=True,
        preamble=("Using the Maestro Career Studio MCP server, do the job below. Then help me "
                  "schedule it: ask how often and when, and write a launchd or cron entry that "
                  "runs `codex exec` with this prompt."),
        attended_preamble=(
            "Using the Maestro Career Studio MCP server, "
            "do the job below with me now."),
        note=("Codex has no scheduler of its own. It can write a launchd or cron entry that "
              "runs codex exec on a timer."),
    ),
    AgentApp(
        id="generic", label="Any MCP agent", reachable=True,
        preamble=("Using the Maestro Career Studio MCP server, set the job below up with your "
                  f"own scheduler. {_ASK}"),
        attended_preamble=(
            "Using the Maestro Career Studio MCP server, "
            "do the job below with me now."),
        note=None,
    ),
    AgentApp(
        id="claude-web", label="Claude web", reachable=False,
        preamble=("Using your Maestro Career Studio connector, set the job below up as a "
                  f"scheduled task. {_ASK}"),
        attended_preamble=(
            "Using your Maestro Career Studio connector, "
            "do the job below with me now."),
        note=f"{_REMOTE} Use Claude Desktop for now.",
    ),
    AgentApp(
        id="chatgpt", label="ChatGPT", reachable=False,
        preamble=("Using the Maestro Career Studio connector, set the job below up as a "
                  f"scheduled task. {_ASK}"),
        attended_preamble=(
            "Using the Maestro Career Studio connector, "
            "do the job below with me now."),
        note=f"{_REMOTE} Use Codex or Claude Desktop for now.",
    ),
)


def _split(path: Path) -> tuple[dict, str]:
    """Return a skill file's frontmatter mapping and its body."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: no frontmatter")
    head, sep, body = text[4:].partition("\n---\n")
    if not sep:
        raise ValueError(f"{path}: unterminated frontmatter")
    return yaml.safe_load(head) or {}, body.lstrip("\n")


@lru_cache(maxsize=1)
def load_cards() -> tuple[AutomationCard, ...]:
    """Parse every skill once. Raises ValueError on any malformed or unknown card."""
    bodies: dict[str, str] = {}
    metas: dict[str, _Meta] = {}
    for path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        front, body = _split(path)
        skill_id = path.parent.name
        if front.get("name") != skill_id:
            raise ValueError(f"{path}: name {front.get('name')!r} must match its folder")
        bodies[skill_id] = body
        if "metadata" in front:
            try:
                metas[skill_id] = _Meta.model_validate(front["metadata"])
            except ValidationError as exc:
                raise ValueError(f"{path}: bad metadata: {exc}") from exc
    if sorted(metas) != sorted(CARD_ORDER):
        raise ValueError(f"cards {sorted(metas)} != designed {sorted(CARD_ORDER)}")
    cards = []
    for skill_id in CARD_ORDER:
        meta = metas[skill_id]
        body = bodies[skill_id]
        for extra in meta.include:
            if extra not in bodies:
                raise ValueError(f"{skill_id}: include {extra!r} has no skill file")
            body = f"{body.rstrip()}\n\n{bodies[extra]}"
        cards.append(AutomationCard(id=skill_id, title=meta.title, summary=meta.summary,
                                    kind=meta.kind, needs=meta.needs, never=meta.never, body=body))
    return tuple(cards)


def apply_kind() -> Kind:
    """Attended until full automation mode (phase 4) adds the auto-submit setting.

    Phase 4 reads that setting here and switches the Apply card's kind, `never`
    line and body to the auto-submit prompt; the page needs no change.
    """
    return "attended"


def catalog() -> AutomationCatalog:
    """The cards in designed order plus the per-agent-app wrappers."""
    cards = [c.model_copy(update={"kind": apply_kind()}) if c.id == "apply-session" else c
             for c in load_cards()]
    return AutomationCatalog(cards=cards, apps=list(APPS))
