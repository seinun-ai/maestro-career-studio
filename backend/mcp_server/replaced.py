"""What changes took off the MCP surface, and what does that job now.

A call to a removed tool, from an agent or an old saved prompt, is answered with a plain
sentence naming its replacement, not a bare "Unknown tool", on stdio and on every HTTP set
(mcp_server.server._ServedMCP.call_tool, which every set runs on both transports). A call
that still uses a removed argument gets the same kind of sentence and is never acted on:
MCPServer drops an argument a tool does not declare, so kb_approve_points(state="retired")
from an old prompt would otherwise approve the drafts the user rejected. Pure: no httpx, no
app imports.
"""
from __future__ import annotations

import re
from collections.abc import Collection
from typing import Any

from mcp_server.profiles import PROFILE_ALLOWLISTS

# Each removed tool and what replaced it, as a call where one call does the job. A test keeps
# it honest: no key is registered in any set, and every tool a replacement names is.
REPLACED_TOOLS: dict[str, str] = {
    "explore_top_skills": 'explore_trends(view="top_skills")',
    "explore_skill_heatmap": 'explore_trends(view="heatmap")',
    "explore_role_mix_over_time": 'explore_trends(view="role_mix")',
    "explore_fit_distribution": 'explore_trends(view="fit_distribution")',
    "explore_ats_over_time": 'explore_trends(view="ats_over_time")',
    "explore_tailoring_lift": 'explore_trends(view="tailoring_lift")',
    "get_career_export": 'get_career_context(format="markdown")',
    "attach_evidence_file": "attach_evidence(file_path=...)",
    "quick_tailor": "create_tailoring_session(use_presets=true)",
    "tailor_application": (
        "a tailoring session (create_tailoring_session, then tailor_session), or "
        "edit_application for the current draft"
    ),
}


def _named_tools(replacement: str) -> frozenset[str]:
    """The tools a replacement names: identifiers with an underscore, neither an argument
    name (before "=") nor a quoted argument value."""
    unquoted = re.sub(r'"[^"]*"', "", replacement)
    return frozenset(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b(?!=)", unquoted))


def _listed(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def replaced_message(name: str, served: Collection[str] | None = None) -> str | None:
    """The answer to a call to `name` when a change removed it, or None. `served` is what the
    set the call came to serves (None: every tool); when it lacks a tool the replacement names,
    the answer adds the scoped sets that serve all of them, in journey order."""
    replacement = REPLACED_TOOLS.get(name)
    if not replacement:
        return None
    needed = _named_tools(replacement)
    if served is None or needed <= set(served):
        return f"{name} was replaced by {replacement}."
    sets = [s for s, allow in PROFILE_ALLOWLISTS.items() if allow and needed <= allow] or ["full"]
    return f"{name} was replaced by {replacement}, in the {_listed(sets)} set{'s' * (len(sets) > 1)}."


def refused_argument(name: str, arguments: dict[str, Any]) -> str | None:
    """The refusal for an argument `name` no longer takes, or None. kb_approve_points lost
    `state`: approving is all it does, so only an explicit "approved" still means that."""
    if name == "kb_approve_points" and arguments.get("state", "approved") != "approved":
        return "kb_approve_points only approves; kb_retire_points retires points."
    return None
