"""In-process Streamable HTTP for the MCP tests: the endpoint on a bare Starlette app, a
2025-era session (initialize, then initialized), one JSON-RPC request on it, one request on
the 2026-07-28 revision, and the normalisation that compares responses on what an agent reads.
Also each set's path, and the automation cards served with no backend.

Shared here, not in a conftest: pytest loads a conftest before tests/conftest.py points app.db
at the test database, and mcp_server.server imports the app."""

import contextlib
import re
from typing import Any

from mcp.shared.inbound import NAME_BEARING_METHODS
from starlette.applications import Starlette
from starlette.routing import Route

from mcp_server import server as srv

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


def set_path(profile: str) -> str:
    """Where a set is served: the full set at /mcp, every other at /mcp/<set>."""
    return "/mcp" if profile == "full" else f"/mcp/{profile}"


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


MODERN = "2026-07-28"


def modern_rpc(c, path, method, params=None, client_info=INIT["params"]["clientInfo"]):
    """One request on the 2026-07-28 revision: no handshake and no session; the version, the
    client and its capabilities ride in `_meta` (keys the caller's own `_meta` sets win), the
    method and, when the body names one, the name or uri in headers too. With client_info None
    the request names no client."""
    params = dict(params or {})
    meta = {
        "io.modelcontextprotocol/protocolVersion": MODERN,
        "io.modelcontextprotocol/clientCapabilities": {},
    }
    if client_info is not None:
        meta["io.modelcontextprotocol/clientInfo"] = client_info
    params["_meta"] = {**meta, **(params.get("_meta") or {})}
    headers = {**HDR, "MCP-Protocol-Version": MODERN, "Mcp-Method": method}
    key = NAME_BEARING_METHODS.get(method)
    if key is not None and params.get(key) is not None:
        headers["Mcp-Name"] = params[key]
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    return c.post(path, json=body, headers=headers)


def serve_catalog(monkeypatch) -> dict[str, dict[str, Any]]:
    """Serve the automation cards as GET /api/automations does (no backend in these tests);
    returns them by id."""
    from app.services import automations

    body = automations.catalog().model_dump(mode="json")
    monkeypatch.setattr(srv._client, "get_automations", lambda: body)
    return {c["id"]: c for c in body["cards"]}


# Added by the 2026-07-28 revision; absent on 1.30.
_REVISION_KEYS = frozenset({"resultType", "ttlMs", "cacheScope", "_meta"})
# pydantic links each validation error to its docs for the installed minor version, and CI
# installs the newest one, so the version in that link is not part of what an agent reads.
_PYDANTIC_DOCS = re.compile(r"errors\.pydantic\.dev/[0-9.]+/")


def _strip(value: Any) -> Any:
    if isinstance(value, dict):
        kept = {k: _strip(v) for k, v in value.items() if k not in _REVISION_KEYS}
        capabilities = kept.get("capabilities")
        if isinstance(capabilities, dict) and capabilities.get("experimental") == {}:
            # 1.30 sent an empty experimental capability, 2.x omits it: both say there are none.
            kept["capabilities"] = {k: v for k, v in capabilities.items() if k != "experimental"}
        return kept
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
