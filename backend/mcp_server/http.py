"""MCP over Streamable HTTP, inside the FastAPI app.

One MCPServer (mcp_server.server.mcp) holds every tool registration. Each set in
PROFILE_ALLOWLISTS is its own server (server.build_set): the registry's Tool
objects for that set and the set's instructions. As a _ServedSet it also offers
the automation playbooks that use it as prompts. Every lifespan run gives each
set a fresh session manager.

Registered sync tools run on worker threads (2.x already keeps them off the
event loop) drawn from a dedicated capacity limiter: they call the backend's
REST API over loopback, and on anyio's default limiter, which FastAPI's sync
endpoints also draw on, tools waiting on REST could starve the endpoints they
wait on. Module-level functions stay sync and directly callable. Tools only read
ctx.session.client_params; worker threads must not await Context methods such as
log or report_progress.

SDK DNS-rebinding protection is off on purpose: the app's Host -> Origin -> CORS
middleware is the one definition (SYSTEM.md §6 inv-mcp-inside-the-app).
"""

from __future__ import annotations

import contextlib
import functools
from collections.abc import AsyncIterator, Callable
from typing import Any

import anyio
import anyio.to_thread
from mcp import MCPError
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import GetPromptResult, Prompt, PromptMessage, TextContent
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

from mcp_server import server as tools_server
from mcp_server.client import BackendError
from mcp_server.profiles import PROFILE_ALIASES, PROFILE_ALLOWLISTS

# Separate from FastAPI's default 40-token limiter: a tool waiting on loopback
# REST must never starve the endpoint it is waiting on.
TOOL_THREADS = 8
SESSION_IDLE_SECONDS = 6 * 60 * 60
# A 10 MB evidence upload inflates by 4/3 when base64-encoded in tool arguments.
MAX_REQUEST_BYTES = 16 * 1024 * 1024


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


def offload_tools(mcp: MCPServer) -> int:
    """Wrap registered sync Tool.fn functions to run on worker threads.

    Argument validation, schemas and Context injection stay on the Tool.
    Already-async tools are unchanged, so repeated calls are idempotent.
    """
    n = 0
    for tool in tools_server._registered_tools(mcp):
        if tool.is_async:
            continue
        tool.fn, tool.is_async = _offloaded(tool.fn), True
        n += 1
    return n


def _prompt_refusal(message: str) -> MCPError:
    """A prompt request refused in words. Code 0 with the text is what the 2025 path has always
    answered; as an MCPError the 2026-07-28 path answers the same, not "Internal server error"."""
    return MCPError(code=0, message=message)


class _ServedSet(tools_server._ServedMCP):
    """One HTTP set: build_set's server, offering as prompts the automation playbooks that
    use the set (full: all)."""

    async def _cards(self) -> list[dict[str, Any]]:
        # The playbooks as the web's Copy prompt gives them. A REST read like the tools, so it
        # runs off the event loop too.
        try:
            catalog = await anyio.to_thread.run_sync(
                tools_server._client.get_automations, limiter=_LIMITER.get()
            )
        except BackendError as exc:
            raise _prompt_refusal(str(exc)) from exc
        cards = (catalog or {}).get("cards") or []
        return [c for c in cards if self.profile == "full" or c.get("toolset") == self.profile]

    async def list_prompts(self) -> list[Prompt]:
        return [
            Prompt(name=c["id"], title=c.get("title"), description=c.get("summary"))
            for c in await self._cards()
        ]

    async def get_prompt(
        self, name: str, arguments: dict[str, Any] | None = None, context: Context | None = None
    ) -> GetPromptResult:
        card = next((c for c in await self._cards() if c["id"] == name), None)
        if card is None:
            raise _prompt_refusal(f"Unknown prompt: {name}")
        return GetPromptResult(
            description=card.get("summary"),
            messages=[PromptMessage(role="user", content=TextContent(type="text", text=card["prompt"]))],
        )


class McpEndpoint:
    """ASGI endpoint for Route('/mcp') and Route('/mcp/{profile}').

    Starlette treats a non-function endpoint as an ASGI app: route the instance,
    not a bound method, to preserve the true path without a 307 redirect.
    """

    def __init__(self, registry: MCPServer | None = None) -> None:
        registry = registry or tools_server.mcp
        # The sets hold these same Tool objects, so wrapping the registry's covers every set.
        offload_tools(registry)
        self.servers = {
            p: tools_server.build_set(p, cls=_ServedSet, registry=registry)
            for p in PROFILE_ALLOWLISTS
        }
        self.security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
        self.managers: dict[str, StreamableHTTPSessionManager] = {}

    def _fresh_manager(self, server: MCPServer) -> StreamableHTTPSessionManager:
        """A session manager runs once, so each lifespan run asks the SDK for a new one per set:
        streamable_http_app makes it and session_manager hands it out (the seam the SDK keeps for
        mounting several servers in one app). The Starlette app it also returns is not mounted;
        the app routes /mcp to this endpoint."""
        server.streamable_http_app(
            json_response=True,
            stateless_http=False,
            transport_security=self.security,
            session_idle_timeout=SESSION_IDLE_SECONDS,
            max_request_body_size=MAX_REQUEST_BYTES,
        )
        return server.session_manager

    @contextlib.asynccontextmanager
    async def run(self) -> AsyncIterator[None]:
        _LIMITER.reset()
        managers = {p: self._fresh_manager(server) for p, server in self.servers.items()}
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
