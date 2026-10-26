"""Who wrote this row? Read from request headers, set by the MCP server.

Headers rather than schema fields: two lines in BackendClient cover every KB
mutation, where adding `origin`/`origin_detail` to each request model would mean
five schemas that callers could also spoof per-field.
"""

from __future__ import annotations

import string
import unicodedata
from dataclasses import dataclass
from urllib.parse import quote, unquote

from fastapi import Header

# A closed set: an untrusted header must not be able to invent an origin value
# that the timeline or a future filter has no meaning for.
ALLOWED_ORIGINS = frozenset({"mcp"})
# The origin header and its one-release alias from before the rename. Both readers
# (get_write_origin, and app/agent_writer.py's mark) name them from here.
ORIGIN_HEADER = "X-Maestro-CS-Origin"
LEGACY_ORIGIN_HEADER = "X-Career-Studio-Origin"
_DETAIL_MAX = 120
# Printable ASCII stays as it is on the wire, so the names already stored for
# KB writes read the same; "%" is encoded so that decoding round-trips.
_DETAIL_SAFE = "".join(c for c in string.punctuation if c != "%") + " "


def _clean_detail(name: str) -> str:
    """No control characters, trimmed, at most _DETAIL_MAX characters."""
    visible = "".join(c for c in name if unicodedata.category(c) != "Cc")
    return visible.strip()[:_DETAIL_MAX]


def encode_detail(name: str | None) -> str | None:
    """A client's name as an HTTP header value. Header values must be ASCII
    (httpx raises UnicodeEncodeError otherwise), so "Café Agent" or "クロード"
    travels percent-encoded; get_write_origin decodes it back."""
    cleaned = _clean_detail(name or "")
    return quote(cleaned, safe=_DETAIL_SAFE) if cleaned else None


def decode_detail(raw: str | None) -> str | None:
    """The real name from an encode_detail header value, cleaned the same way."""
    return _clean_detail(unquote(raw or "")) or None


def origin_from(value: str | None, legacy_value: str | None) -> str | None:
    """The origin a request names, or None: the current header, else the legacy
    one, trimmed and lower-cased, and only a value in ALLOWED_ORIGINS. The one
    rule for every reader of the header."""
    origin = (value or legacy_value or "").strip().lower()
    return origin if origin in ALLOWED_ORIGINS else None


@dataclass(frozen=True)
class WriteOrigin:
    """None means "no override" — the route keeps its own default."""

    origin: str | None = None
    detail: str | None = None


def get_write_origin(
    x_maestro_cs_origin: str | None = Header(default=None, alias=ORIGIN_HEADER),
    x_maestro_cs_origin_detail: str | None = Header(
        default=None, alias="X-Maestro-CS-Origin-Detail"
    ),
    # One-release alias for the pre-rename headers.
    x_career_studio_origin: str | None = Header(default=None, alias=LEGACY_ORIGIN_HEADER),
    x_career_studio_origin_detail: str | None = Header(
        default=None, alias="X-Career-Studio-Origin-Detail"
    ),
) -> WriteOrigin:
    origin = origin_from(x_maestro_cs_origin, x_career_studio_origin)
    if origin is None:
        return WriteOrigin()
    detail = decode_detail(x_maestro_cs_origin_detail or x_career_studio_origin_detail)
    return WriteOrigin(origin=origin, detail=detail)
