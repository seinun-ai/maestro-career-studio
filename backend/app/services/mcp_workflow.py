"""MCP workflow knobs: the user-held master switch for next-step hints.

Separate from quick_tailor_profile on purpose — one saved setting must not come
to mean two things (SYSTEM.md §4). The MCP tool layer adds next-step workflow
hints to its responses so an MCP client walks the tailoring arc without the
user narrating it; a user doing mass JD capture would otherwise get a
tailoring prompt on every one of twenty postings, so this is the off switch.
This is the USER's switch (Settings page). The per-call `brief` param the
agent controls is a separate, narrower knob owned by later tasks.
"""

import json
from typing import Any

from sqlalchemy.orm import Session

from app.services import text_settings

MCP_WORKFLOW_KEY = "mcp_workflow"
MCP_WORKFLOW_FILE = "mcp_workflow.json"

DEFAULTS: dict[str, Any] = {"hints": True}


def get_settings(session: Session | None = None) -> dict[str, Any]:
    raw = text_settings.get_text(MCP_WORKFLOW_KEY, MCP_WORKFLOW_FILE, session)
    stored: dict[str, Any] = {}
    if raw.strip():
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            stored = data
    return {**DEFAULTS, **stored}


def set_settings(value: dict[str, Any], session: Session | None = None) -> dict[str, Any]:
    text_settings.set_text(
        MCP_WORKFLOW_KEY, MCP_WORKFLOW_FILE, json.dumps(value, indent=2, sort_keys=True), session
    )
    return {**DEFAULTS, **value}
