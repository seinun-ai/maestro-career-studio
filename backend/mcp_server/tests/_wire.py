"""In-process Streamable HTTP for the MCP tests: the endpoint on a bare Starlette app, a
2025-era session (initialize, then initialized) and one JSON-RPC request on it."""

import contextlib

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


def app(endpoint):
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
