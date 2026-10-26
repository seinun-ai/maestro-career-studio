"""Who writes for an agent request: Maestro's AI or the agent app (Settings › Agent apps).

A request is an agent request when it carries the MCP origin header (app/write_origin.py); the MCP
client sends it on every call. The mark is a ContextVar set by AgentRequestMiddleware, a pure ASGI
middleware, so it reaches sync routes on the threadpool (contextvars are copied into worker threads).
The web app and the Companion send no such header, so Maestro's AI always writes for them.
"""

from __future__ import annotations

import contextlib
from contextvars import ContextVar

from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from app.services import llm, mcp_workflow

_AGENT_REQUEST: ContextVar[bool] = ContextVar("maestro_agent_request", default=False)

AGENT_WRITES = ("Your settings say your agent app writes, so Maestro's AI doesn't write for agent apps "
                "(Settings › Agent apps changes it).")


class AgentWritesError(Exception):
    """A model call for an agent request while the agent app writes (llm.call_openai's backstop)."""


def is_agent_request() -> bool:
    return _AGENT_REQUEST.get()


@contextlib.contextmanager
def agent_request():
    """Mark the code inside as an agent request (tests, and any caller outside a request)."""
    token = _AGENT_REQUEST.set(True)
    try:
        yield
    finally:
        _AGENT_REQUEST.reset(token)


def maestro_writes() -> bool:
    """Whether Maestro's AI may write for this request: always for the web app and the Companion; for an
    agent request only when the user chose Maestro's AI. A missing setting reads as the default, the
    agent app."""
    if not is_agent_request():
        return True
    return mcp_workflow.peek_settings().writer == "maestro"


def model_available() -> bool:
    """A key is set and Maestro's AI may write for this request: the health check and the resume
    import ask this before calling a model, so agent mode takes their no-AI path quietly."""
    return llm.any_model_key_configured() and maestro_writes()


def refuse_unless_maestro_writes(instead: str) -> None:
    """A writing route's own refusal, naming the tool that takes the agent's text."""
    if not maestro_writes():
        raise HTTPException(status_code=409, detail=f"{AGENT_WRITES} {instead}")


def _on_request() -> None:  # test seam: runs inside the marked context
    return None


class AgentRequestMiddleware:
    """Sets the mark for one HTTP request from its origin header, read the way app/write_origin.py
    reads it (either header name, any case). Raw ASGI, never BaseHTTPMiddleware, like the origin gate."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        origin = headers.get("x-maestro-cs-origin") or headers.get("x-career-studio-origin") or ""
        token = _AGENT_REQUEST.set(origin.strip().lower() == "mcp")
        try:
            _on_request()
            await self.app(scope, receive, send)
        finally:
            _AGENT_REQUEST.reset(token)
