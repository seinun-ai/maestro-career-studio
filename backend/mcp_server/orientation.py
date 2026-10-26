"""The tool sets, in the order a job search moves through them.

One table that the per-set server instructions and get_setup_status read, so a
set's name and its job are written once. Pure: no httpx, no app imports.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolSet:
    name: str
    use_when: str  # what the user says, in their own words
    holds: str


SETS: tuple[ToolSet, ...] = (
    ToolSet(
        "profile",
        "set me up, import my resume, add a project, make a resume for a role",
        "career history, base resumes and their anchors, the health check, versions, "
        "form answers, job preferences, markets and persona",
    ),
    ToolSet("hunt", "find me jobs", "the search brief, saving jobs, scoring them and proposing them"),
    ToolSet(
        "tailor",
        "tailor my resume for this job",
        "looking up or saving the job, scoring, gaps, the tailored resume and its PDF, "
        "the health check, undo and the tailoring presets",
    ),
    ToolSet(
        "apply",
        "apply to this job, work my queue",
        "the cover letter and answers, form answers, the proposal, evidence, the user's yes "
        "and submitting",
    ),
    ToolSet(
        "track",
        "update my statuses, how is my search going",
        "applications and their statuses, referrals and the analytics charts",
    ),
    ToolSet("templates", "make a resume design", "drafting, checking and previewing resume templates"),
    ToolSet("full", "anything", "every tool"),
)

SET_NAMES: tuple[str, ...] = tuple(s.name for s in SETS)

_BY_NAME = {s.name: s for s in SETS}

_INTRO = "Maestro Career Studio keeps one person's job search on their own computer."
_START = (
    "Start with get_setup_status: it says where setup stands, whether Maestro has its own "
    "AI key, which base resume is the shipped demo, and the next step. Its writer says who "
    "writes: your agent app (Maestro's own writing then refuses, so you write the text and save "
    "it) or Maestro's AI (it writes with the user's key)."
)
_STYLE = (
    "Talk with the user however suits them. Maestro supplies their facts, presets and rules, "
    "not a script. However you work, Maestro keeps its rules: a skill the user has not shown "
    "goes only into a skills list, resume lines stay in the owner's implied first person, and "
    "saved keywords land."
)


def instructions_for(profile: str) -> str:
    """The server instructions for one set: under Claude Code's 4,096-character cut, naming
    every other set and no tool the set lacks (pinned by tests/test_orientation.py)."""
    others = [s for s in SETS if s.name not in (profile, "full")]
    rest = "; ".join(f"{s.name}: {s.holds}" for s in others)
    if profile == "full":
        parts = [
            _INTRO,
            "This is the full set: every tool. They also come in smaller sets, each at its own "
            f"address (/mcp/<set>), for apps that load every tool up front: {rest}.",
            _START,
        ]
    else:
        me = _BY_NAME[profile]
        parts = [
            _INTRO,
            f"This is the {me.name} set: {me.holds}. Use it when the user says things like: "
            f"{me.use_when}.",
            f"Other sets hold the rest: {rest}. The full set has every tool. When the user "
            "needs one of those, say which set to connect.",
        ]
        if profile != "templates":
            parts.append(_START)
    parts.append(_STYLE)
    return "\n\n".join(parts)
