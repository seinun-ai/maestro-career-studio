"""MCP workflow knobs. One boolean today; a model rather than a loose dict so
the shape is declared somewhere other than the TypeScript that reads it."""

from pydantic import BaseModel


class McpWorkflowSettings(BaseModel):
    hints: bool = True
