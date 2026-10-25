"""MCP over Streamable HTTP, inside the FastAPI app.

One FastMCP (mcp_server.server.mcp) holds every tool registration. Each
profile gets a low-level MCP Server that filters that registry through the
profile allowlist, with a fresh session manager on every lifespan run.

Registered sync tools run on worker threads with a dedicated capacity limiter:
they call the backend's REST API over loopback, which would deadlock a
single-worker uvicorn if called on its event loop. Module-level functions stay
sync and directly callable. Tools only read ctx.session.client_params; worker
threads must not await Context methods such as log or report_progress.

SDK DNS-rebinding protection is off on purpose: the app's Host -> Origin -> CORS
middleware is the one definition (SYSTEM.md §6 inv-mcp-inside-the-app).
"""

from __future__ import annotations

import contextlib
import functools
import logging
import os
from collections.abc import AsyncIterator, Callable
from typing import Any

import anyio
import anyio.to_thread
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import GetPromptResult, Prompt, PromptMessage, TextContent
from mcp.types import Tool as MCPTool
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

from mcp_server import orientation
from mcp_server import server as tools_server
from mcp_server.profiles import PROFILE_ALIASES, PROFILE_ALLOWLISTS

# Separate from FastAPI's default 40-token limiter: a tool waiting on loopback
# REST must never starve the endpoint it is waiting on.
TOOL_THREADS = 8
SESSION_IDLE_SECONDS = 6 * 60 * 60
# A 10 MB evidence upload inflates by 4/3 when base64-encoded in tool arguments.
MAX_REQUEST_BYTES = 16 * 1024 * 1024

logging.getLogger("mcp.server.lowlevel.server").setLevel(logging.WARNING)


class _Limiter:
    """Created inside the running loop; reset on every lifespan run."""

    def __init__(self, tokens: int) -> None:
        self.tokens = tokens
        self._limiter: anyio.CapacityLimiter | None = None

    def reset(self) -> None:
        self._limiter = anyio.CapacityLimiter(self.tokens)

    def get(self) -> anyio.CapacityLimiter:
        if self._limiter is None:
            self.reset()
        assert self._limiter is not None
        return self._limiter


_LIMITER = _Limiter(TOOL_THREADS)


def _offloaded(original: Callable[..., Any]) -> Callable[..., Any]:
    async def run_off_loop(**kwargs: Any) -> Any:
        return await anyio.to_thread.run_sync(
            functools.partial(original, **kwargs), limiter=_LIMITER.get()
        )

    return run_off_loop


def offload_tools(mcp: FastMCP) -> int:
    """Wrap registered sync Tool.fn functions to run on worker threads.

    Argument validation, schemas and Context injection stay on the Tool.
    Already-async tools are unchanged, so repeated calls are idempotent.
    """
    n = 0
    for tool in mcp._tool_manager.list_tools():
        if tool.is_async:
            continue
        tool.fn, tool.is_async = _offloaded(tool.fn), True
        n += 1
    return n


def build_profile_server(mcp: FastMCP, profile: str, allowed: frozenset[str] | None) -> Server:
    server: Server = Server(
        mcp.name,
        version=os.environ.get("APP_VERSION", "dev"),
        instructions=orientation.instructions_for(profile),  # each set says what it holds
    )

    @server.list_tools()
    async def _list_tools() -> list[MCPTool]:
        tools = await mcp.list_tools()  # Preserve titles, annotations and outputSchema.
        return [t for t in tools if allowed is None or t.name in allowed]

    @server.call_tool(validate_input=False)  # FastMCP validates the Tool's own model.
    async def _call_tool(name: str, arguments: dict[str, Any]) -> Any:
        if allowed is not None and name not in allowed:
            raise ToolError(f"Unknown tool: {name}")
        token = tools_server.CURRENT_PROFILE.set(profile)
        try:
            # FastMCP.get_context() reads the SDK's shared request ContextVar,
            # set by this low-level server, so clientInfo belongs to this caller.
            return await mcp.call_tool(name, arguments)
        finally:
            tools_server.CURRENT_PROFILE.reset(token)

    async def _cards() -> list[dict[str, Any]]:
        # The automation playbooks, as the web's Copy prompt gives them, for this set
        # (full: all). A REST read like the tools, so it runs off the event loop too.
        catalog = await anyio.to_thread.run_sync(
            tools_server._client.get_automations, limiter=_LIMITER.get()
        )
        cards = (catalog or {}).get("cards") or []
        return [c for c in cards if profile == "full" or c.get("toolset") == profile]

    @server.list_prompts()
    async def _list_prompts() -> list[Prompt]:
        return [
            Prompt(name=c["id"], title=c.get("title"), description=c.get("summary"))
            for c in await _cards()
        ]

    @server.get_prompt()
    async def _get_prompt(name: str, arguments: dict[str, str] | None) -> GetPromptResult:
        card = next((c for c in await _cards() if c["id"] == name), None)
        if card is None:
            raise ValueError(f"Unknown prompt: {name}")
        return GetPromptResult(
            description=card.get("summary"),
            messages=[PromptMessage(role="user", content=TextContent(type="text", text=card["prompt"]))],
        )

    return server


class McpEndpoint:
    """ASGI endpoint for Route('/mcp') and Route('/mcp/{profile}').

    Starlette treats a non-function endpoint as an ASGI app: route the instance,
    not a bound method, to preserve the true path without a 307 redirect.
    """

    def __init__(self, mcp: FastMCP | None = None) -> None:
        mcp = mcp or tools_server.mcp
        offload_tools(mcp)
        self.servers = {
            p: build_profile_server(mcp, p, allow) for p, allow in PROFILE_ALLOWLISTS.items()
        }
        self.security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
        self.managers: dict[str, StreamableHTTPSessionManager] = {}

    @contextlib.asynccontextmanager
    async def run(self) -> AsyncIterator[None]:
        _LIMITER.reset()
        managers = {
            p: StreamableHTTPSessionManager(
                app=server,
                json_response=True,
                stateless=False,
                security_settings=self.security,
                session_idle_timeout=SESSION_IDLE_SECONDS,
                max_request_body_size=MAX_REQUEST_BYTES,
            )
            for p, server in self.servers.items()
        }
        async with contextlib.AsyncExitStack() as stack:
            for manager in managers.values():
                await stack.enter_async_context(manager.run())
            self.managers = managers
            try:
                yield
            finally:
                self.managers = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        profile = scope.get("path_params", {}).get("profile", "full")
        profile = PROFILE_ALIASES.get(profile, profile)  # an old name serves its set for one release
        manager = self.managers.get(profile)
        if manager is None:
            await JSONResponse({"detail": "Not Found"}, status_code=404)(scope, receive, send)
            return
        await manager.handle_request(scope, receive, send)
