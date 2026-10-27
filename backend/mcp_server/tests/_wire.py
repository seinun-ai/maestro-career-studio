"""In-process Streamable HTTP for the MCP tests: the endpoint on a bare Starlette app, a
2025-era session (initialize, then initialized), one JSON-RPC request on it, and the
normalisation that compares responses on what an agent reads."""

import contextlib
import re
from typing import Any

from starlette.applications import Starlette
from starlette.routing import Route

HDR = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "pytest-client", "version": "1"},
    },
}


def asgi_app(endpoint):
    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with endpoint.run():
            yield

    return Starlette(
        routes=[Route("/mcp", endpoint=endpoint), Route("/mcp/{profile}", endpoint=endpoint)],
        lifespan=lifespan,
    )


def session(c, path="/mcp"):
    r = c.post(path, json=INIT, headers=HDR)
    assert r.status_code == 200, r.text
    sid = r.headers["mcp-session-id"]
    initialized = c.post(
        path,
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers={**HDR, "Mcp-Session-Id": sid},
    )
    assert initialized.status_code == 202, initialized.text
    return sid


def rpc(c, path, sid, method, params=None, id_=2):
    body = {"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}}
    return c.post(path, json=body, headers={**HDR, "Mcp-Session-Id": sid})


# Added by the 2026-07-28 revision; absent on 1.30.
_REVISION_KEYS = frozenset({"resultType", "ttlMs", "cacheScope", "_meta"})
# pydantic links each validation error to its docs for the installed minor version, and CI
# installs the newest one, so the version in that link is not part of what an agent reads.
_PYDANTIC_DOCS = re.compile(r"errors\.pydantic\.dev/[0-9.]+/")


def _strip(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip(v) for k, v in value.items() if k not in _REVISION_KEYS}
    if isinstance(value, list):
        return [_strip(v) for v in value]
    if isinstance(value, str):
        return _PYDANTIC_DOCS.sub("errors.pydantic.dev/<version>/", value)
    return value


def normalise_response(response: Any) -> Any:
    """One JSON-RPC response without its envelope's jsonrpc and id, and without, at any depth,
    the keys the 2026-07-28 revision adds: what an agent reads, on either SDK."""
    if isinstance(response, dict):
        response = {k: v for k, v in response.items() if k not in ("jsonrpc", "id")}
    return _strip(response)


def normalise_record(entries: dict[str, Any]) -> dict[str, Any]:
    """normalise_response applied to every entry of a record, keyed by entry name."""
    return {name: normalise_response(entry) for name, entry in entries.items()}
