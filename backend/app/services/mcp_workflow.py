"""MCP workflow knobs: the user-held master switch for next-step hints.

Separate from quick_tailor_profile on purpose — one saved setting must not come
to mean two things (SYSTEM.md §4). The MCP tool layer adds next-step workflow
hints to its responses so an MCP client walks the tailoring arc without the
user narrating it; a user doing mass JD capture would otherwise get a
tailoring prompt on every one of twenty postings, so this is the off switch.
This is the USER's switch (Settings page). The per-call `brief` param the
agent controls is a separate, narrower knob owned by later tasks.
"""

from sqlalchemy.orm import Session

from app.schemas.mcp_workflow import McpWorkflowSettings
from app.services.json_settings import JsonSetting

MCP_WORKFLOW = JsonSetting("mcp_workflow", "mcp_workflow.json", McpWorkflowSettings)
# Key/filename stay importable: callers and tests address the setting by
# name, and the constants are now derived from the one definition above.
MCP_WORKFLOW_KEY = MCP_WORKFLOW.key
MCP_WORKFLOW_FILE = MCP_WORKFLOW.filename


def get_settings(session: Session | None = None) -> McpWorkflowSettings:
    return MCP_WORKFLOW.get(session)


def set_settings(
    value: McpWorkflowSettings, session: Session | None = None
) -> McpWorkflowSettings:
    return MCP_WORKFLOW.set(value, session)
