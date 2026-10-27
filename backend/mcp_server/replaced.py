"""What a merge took off the MCP surface, and what does that job now.

A call that still uses a removed argument is answered with a plain sentence naming the tool
that does that job, never acted on: FastMCP drops an argument a tool does not declare, so
kb_approve_points(state="retired") from an old prompt would otherwise approve the drafts the
user rejected. Pure: no httpx, no app imports.
"""
from __future__ import annotations

from typing import Any


def refused_argument(name: str, arguments: dict[str, Any]) -> str | None:
    """The refusal for an argument `name` no longer takes, or None. kb_approve_points lost
    `state`: approving is all it does, so only an explicit "approved" still means that."""
    if name == "kb_approve_points" and arguments.get("state", "approved") != "approved":
        return "kb_approve_points only approves; kb_retire_points retires points."
    return None
