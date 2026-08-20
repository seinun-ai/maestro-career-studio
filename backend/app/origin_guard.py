"""Refuse a browser request whose Origin is not on the allowlist.

CORS answers a different question than the one this API needs answered. It
decides whether a hostile page may READ a response; it does not decide whether
the request RUNS. A form-encoded or multipart POST is a "simple request", which
the browser sends cross-origin with no preflight — so against a zero-auth local
API the side effect lands in full and the browser merely withholds the reply.
Mutating a known object, spending the user's model budget, and filling the disk
are all reachable that way, and none of them needs the response back.

So the rule here is stricter than CORS: an Origin that is PRESENT and not on
the allowlist is refused before any handler runs.

**Absent Origin is allowed, deliberately.** MCP over httpx, curl, and the
container healthcheck send no Origin, and they are not browsers — a browser is
the only thing that attaches the header, and it attaches it truthfully. Reading
"missing" as "hostile" would break every non-browser client to gain nothing,
because an attacker who can forge headers is not in a browser and is already
past this boundary. This is the same reasoning that makes the Host check
meaningful: these controls bound what a PAGE can do, not what a process can do.

Written as a raw ASGI middleware rather than a `BaseHTTPMiddleware` subclass on
purpose: the chat surface streams SSE, and BaseHTTPMiddleware wraps the
response body in a way that has historically broken streaming. This one never
touches the body — it either short-circuits with its own response or steps out
of the way entirely.

Order matters and is pinned by `test_the_host_check_outranks_the_origin_check`:
Host → Origin → CORS. See `app/main.py` for why that falls out of the order the
`add_middleware` calls appear in.
"""

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class OriginGuardMiddleware:
    """Reject a present-but-unlisted `Origin` with 403, before routing."""

    def __init__(self, app: ASGIApp, allowed_origins: list[str]) -> None:
        self.app = app
        self.allowed = frozenset(allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Both scopes, matching TrustedHostMiddleware. The app registers no
        # WebSocket routes today (chat streams over SSE), so the websocket arm
        # is unreachable — which is exactly why it is written now: a WS route
        # added later would inherit the Host check and silently NOT inherit
        # this one, and `Origin` is the only thing naming the page that opened
        # the socket.
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        origin = Headers(scope=scope).get("origin")
        # Exact membership, never a prefix or suffix test: `startswith` would
        # admit `http://localhost:3000.evil.example`, which is a different site.
        if origin is not None and origin not in self.allowed:
            if scope["type"] == "websocket":
                # A WS scope cannot carry an HTTP response; the handshake is
                # refused with a close, as TrustedHostMiddleware does.
                await send({"type": "websocket.close", "code": 1008})
                return
            response = JSONResponse(
                {
                    "detail": (
                        "Origin not allowed. This API only accepts browser "
                        "requests from the local web app and the configured "
                        "extension."
                    )
                },
                status_code=403,
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
