"""Who wrote this row? Read from request headers, set by the MCP server.

Headers rather than schema fields: two lines in BackendClient cover every KB
mutation, where adding `origin`/`origin_detail` to each request model would mean
five schemas that callers could also spoof per-field.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header

# A closed set: an untrusted header must not be able to invent an origin value
# that the timeline or a future filter has no meaning for.
ALLOWED_ORIGINS = frozenset({"mcp"})
_DETAIL_MAX = 120


@dataclass(frozen=True)
class WriteOrigin:
    """None means "no override" — the route keeps its own default."""

    origin: str | None = None
    detail: str | None = None


def get_write_origin(
    x_maestro_cs_origin: str | None = Header(default=None, alias="X-Maestro-CS-Origin"),
    x_maestro_cs_origin_detail: str | None = Header(
        default=None, alias="X-Maestro-CS-Origin-Detail"
    ),
    # One-release alias for the pre-rename headers.
    x_career_studio_origin: str | None = Header(
        default=None, alias="X-Career-Studio-Origin"
    ),
    x_career_studio_origin_detail: str | None = Header(
        default=None, alias="X-Career-Studio-Origin-Detail"
    ),
) -> WriteOrigin:
    origin = (
        x_maestro_cs_origin or x_career_studio_origin or ""
    ).strip().lower()
    if origin not in ALLOWED_ORIGINS:
        return WriteOrigin()
    detail = (
        x_maestro_cs_origin_detail or x_career_studio_origin_detail or ""
    ).strip()[:_DETAIL_MAX] or None
    return WriteOrigin(origin=origin, detail=detail)
