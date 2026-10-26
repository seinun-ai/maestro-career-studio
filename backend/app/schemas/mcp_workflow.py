"""MCP workflow knobs: the next-step hints switch and who writes for a connected agent
app. A model rather than a loose dict so the shape is declared somewhere other than
the TypeScript that reads it."""

from typing import Literal

from pydantic import BaseModel

# Who writes for a connected agent app (design 2026-10-26): "agent" = the agent app writes and Maestro's
# AI never runs for an agent request; "maestro" = Maestro's AI writes with the user's key.
Writer = Literal["agent", "maestro"]


class McpWorkflowSettings(BaseModel):
    hints: bool = True
    writer: Writer = "agent"
