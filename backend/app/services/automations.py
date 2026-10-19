"""Automations: prompts a user copies into their own agent app.

The skill files under app/automations/skills are the single source of the text
(docs/plans/2026-10-04-automations-page-design.md). A skill with a `metadata`
block is a card; one without (agent-apply-execution) rides on a card through
`include`. Nothing about the user is inserted: the agent reads the brief, caps
and preferences live over MCP, and asks the user when to run. Every card's
`prompt` is one app-neutral wrapper plus its body
(docs/plans/2026-10-19-neutral-automation-prompt-design.md).
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
ALTERNATES = {"apply-auto": "apply-session"}

# `scheduled` cards open with SCHEDULED_WRAPPER (ask when, then use whatever scheduler the
# agent can reach); `attended` and `custom` cards open with ATTENDED_WRAPPER (do it now).
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
    model_config = ConfigDict(frozen=True)
    id: str
    title: str
    summary: str
    kind: Kind
    needs: tuple[Need, ...]
    never: str | None
    body: str
    prompt: str


class AutomationCatalog(BaseModel):
    cards: list[AutomationCard]


# Neither wrapper names an agent app or a scheduling mechanism: apps change weekly, so the
# agent works out what it can do and says plainly when it can't.
SCHEDULED_WRAPPER = (
    "Using your Maestro Career Studio connection, set the job below up to run on a schedule. "
    "First ask me how often and when. Then use whatever scheduling you can reach: one built "
    "into this app if it has one, otherwise one available on this computer. If you can't "
    "schedule it from here, tell me plainly, say where I could run it on a schedule instead, "
    "and offer to run it once now. Schedule only the job below, not this paragraph. If you "
    "can't reach Maestro's tools at all, tell me to connect you first and stop."
)
ATTENDED_WRAPPER = (
    "Using your Maestro Career Studio connection, do the job below with me now. If you can't "
    "reach Maestro's tools, tell me to connect you first and stop."
)


def _prompt(kind: Kind, body: str) -> str:
    """The text Copy puts on the clipboard: the kind's wrapper, then the skill."""
    wrapper = SCHEDULED_WRAPPER if kind == "scheduled" else ATTENDED_WRAPPER
    return f"{wrapper}\n\n{body}"


def _split(path: Path) -> tuple[dict, str]:
    """Return a skill file's frontmatter mapping and its body."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: no frontmatter")
    head, sep, body = text[4:].partition("\n---\n")
    if not sep:
        raise ValueError(f"{path}: unterminated frontmatter")
    try:
        front = yaml.safe_load(head)
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: frontmatter is not valid YAML: {exc}") from exc
    if not isinstance(front, dict):
        raise ValueError(f"{path}: frontmatter must be a mapping")
    return front, body.lstrip("\n")


def _read_skills() -> tuple[dict[str, str], dict[str, _Meta]]:
    """Every skill's body by folder name, and the validated metadata of those that are cards."""
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
    return bodies, metas


def _check_card_set(metas: dict[str, _Meta]) -> None:
    expected = sorted(CARD_ORDER + tuple(ALTERNATES))
    if sorted(metas) != expected:
        raise ValueError(
            f"cards {sorted(metas)} != designed {expected} (looked in {SKILLS_DIR})")


def _check_no_orphans(bodies: dict[str, str], metas: dict[str, _Meta]) -> None:
    used = {extra for meta in metas.values() for extra in meta.include}
    orphans = sorted(set(bodies) - set(metas) - used)
    if orphans:
        raise ValueError(f"skills {orphans} are neither a card nor included by one")


def _card_body(skill_id: str, bodies: dict[str, str], metas: dict[str, _Meta]) -> str:
    """A card's own body followed by each non-card skill it includes."""
    body = bodies[skill_id]
    for extra in metas[skill_id].include:
        if extra not in bodies:
            raise ValueError(f"{skill_id}: include {extra!r} has no skill file")
        if extra in metas or extra == skill_id:
            raise ValueError(f"{skill_id}: include {extra!r} must be a non-card skill")
        body = f"{body.rstrip()}\n\n{bodies[extra]}"
    return body


def _card(card_id: str, meta: _Meta, body: str) -> AutomationCard:
    """A card from its metadata and body, with the prompt Copy hands the agent."""
    return AutomationCard(
        id=card_id, title=meta.title, summary=meta.summary, kind=meta.kind,
        needs=tuple(meta.needs), never=meta.never, body=body,
        prompt=_prompt(meta.kind, body),
    )


@lru_cache(maxsize=1)
def load_cards() -> tuple[AutomationCard, ...]:
    """Parse every skill once. Raises ValueError on any malformed or unknown card."""
    bodies, metas = _read_skills()
    _check_card_set(metas)
    cards = tuple(_card(s, metas[s], _card_body(s, bodies, metas)) for s in CARD_ORDER)
    for skill_id in ALTERNATES:
        _card_body(skill_id, bodies, metas)
    _check_no_orphans(bodies, metas)
    return cards


@lru_cache(maxsize=1)
def _alternate(skill_id: str) -> AutomationCard:
    """Build an alternate card and keep the catalog identity it replaces."""
    bodies, metas = _read_skills()
    meta = metas[skill_id]
    return _card(ALTERNATES[skill_id], meta, _card_body(skill_id, bodies, metas))


def apply_kind() -> Kind:
    """The attended Apply card remains the default when automation is off."""
    return "attended"


def catalog(full_automation: bool = False) -> AutomationCatalog:
    """The cards in designed order, each with its finished prompt."""
    cards = []
    for card in load_cards():
        if card.id != "apply-session":
            cards.append(card)
        elif full_automation:
            cards.append(_alternate("apply-auto"))
        else:
            kind = apply_kind()
            cards.append(card.model_copy(update={"kind": kind, "prompt": _prompt(kind, card.body)}))
    return AutomationCatalog(cards=cards)
