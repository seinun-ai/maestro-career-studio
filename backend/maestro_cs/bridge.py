"""`maestro mcp`: Claude Desktop's stdio ↔ this install's /mcp. Twin of mcpb/server/index.js.

Imports nothing from `app` and applies no environment: it only needs the backend port, which
comes from the process environment, then the install's `maestro.env`, then the default.
"""
from __future__ import annotations

import base64
import contextlib
import json
import os
import re
import signal
import sys
import time
from typing import Any, BinaryIO, TextIO

import httpx

from maestro_cs.home import ports_from, read_env_file, resolve_home

TIMEOUT_SECONDS = 600.0
TIMEOUT_MESSAGE = ("Maestro Career Studio did not answer within 10 minutes. "
                   "The request may still finish in the app.")
FAILED_MESSAGE = ("Maestro Career Studio could not complete the request. "
                  "The request may still finish in the app.")

# A 2026-07-28 message has no initialize or session: it names its revision in params._meta, and the
# SDK routes on MCP-Protocol-Version, then checks Mcp-Method and Mcp-Name against the body. A header
# naming a handshake revision (the SDK's HANDSHAKE_PROTOCOL_VERSIONS) goes down the 2025 path, which
# needs the session, so a message naming one is 2025 traffic.
# No Mcp-Param-* headers: no Maestro tool declares x-mcp-header, and one that did would be refused
# through the bridge until it mirrored that tool's arguments too.
# Copied, not imported: importing `mcp` adds about 200 ms to every start. test_bridge.py pins these
# and header_value to the SDK's own.
PROTOCOL_VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
HANDSHAKE_VERSIONS = frozenset({"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"})
NAME_PARAMS = {"tools/call": "name", "prompts/get": "name", "resources/read": "uri"}
_HEADER_SAFE = re.compile(r"[\x20-\x7E]*")
_BASE64_FORM = re.compile(r"=\?base64\?.*\?=")


def header_value(value: str) -> str:
    """The SDK's header codec (encode_header_value): printable ASCII without edge spaces goes as is,
    anything else as =?base64?<UTF-8>?=. The SDK encodes only Mcp-Name and compares the version and
    method raw; encoding those too is harmless, since any value the codec changes is refused either
    way, and it keeps httpx from raising UnicodeEncodeError on a non-ASCII value."""
    if (_HEADER_SAFE.fullmatch(value) and value == value.strip()
            and not _BASE64_FORM.fullmatch(value)):
        return value
    return f"=?base64?{base64.b64encode(value.encode('utf-8')).decode('ascii')}?="


def routing_headers(message: Any) -> dict[str, str] | None:
    params = message.get("params") if isinstance(message, dict) else None
    meta = params.get("_meta") if isinstance(params, dict) else None
    version = meta.get(PROTOCOL_VERSION_KEY) if isinstance(meta, dict) else None
    if not isinstance(version, str) or version in HANDSHAKE_VERSIONS:
        return None
    headers = {"MCP-Protocol-Version": header_value(version)}
    method = message.get("method")
    if isinstance(method, str):
        headers["Mcp-Method"] = header_value(method)
        name = params.get(NAME_PARAMS[method]) if method in NAME_PARAMS else None
        if isinstance(name, str):
            headers["Mcp-Name"] = header_value(name)
    return headers


def _is_integer(value: Any) -> bool:
    # JavaScript's Number.isInteger on a parsed JSON value, as the Node twin checks: 5.0 is one,
    # true is not.
    if isinstance(value, bool):
        return False
    return isinstance(value, int) or (isinstance(value, float) and value.is_integer())


def _same_id(a: Any, b: Any) -> bool:
    # JavaScript's === on two parsed JSON ids: true is not 1, and no object or array equals another.
    return not isinstance(a, (dict, list)) and isinstance(a, bool) == isinstance(b, bool) and a == b


def refusal_for(request: Any, status: int, raw: bytes) -> dict[str, Any] | None:
    """That path refuses a request with its JSON-RPC error and a 400 or 404 (Method not found, an
    unsupported revision with the supported list); the client is owed that answer, not
    "HTTP 404"."""
    if not 400 <= status < 500 or not isinstance(request, dict) or "id" not in request:
        return None
    try:
        body = json.loads(raw)
    except (ValueError, RecursionError):
        return None
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    if (body.get("jsonrpc") == "2.0" and "id" in body and _same_id(body["id"], request["id"])
            and isinstance(error, dict) and _is_integer(error.get("code"))
            and isinstance(error.get("message"), str)):
        return body
    return None


class BridgeError(Exception):
    pass


class _Stop(Exception):
    """SIGTERM or SIGINT arrived: leave quietly with exit code 0."""


def mcp_url(backend_url: str, profile: str = "full") -> str:
    base = backend_url.rstrip("/")
    return f"{base}/mcp" if profile == "full" else f"{base}/mcp/{profile}"


class Bridge:
    def __init__(self, backend_url: str, profile: str = "full", *,
                 client: httpx.Client | None = None, stdout: BinaryIO | None = None,
                 stderr: TextIO | None = None, timeout: float = TIMEOUT_SECONDS) -> None:
        self.backend_url = backend_url.rstrip("/")
        self.url = mcp_url(backend_url, profile)
        self.timeout = timeout
        # trust_env=False: this is loopback, and a proxy variable must never see MCP traffic.
        self.client = client or httpx.Client(timeout=httpx.Timeout(timeout), trust_env=False)
        self.stdout = stdout or sys.stdout.buffer
        self.stderr = stderr or sys.stderr
        self.session_id: str | None = None
        self.initialize_line: str | None = None
        self.initialized_line: str | None = None

    def note(self, message: str) -> None:
        print(message, file=self.stderr, flush=True)

    def write(self, body: Any) -> None:
        self.stdout.write(json.dumps(body, separators=(",", ":")).encode("utf-8") + b"\n")
        self.stdout.flush()

    def post(self, line: str, routing: dict[str, str] | None = None
             ) -> tuple[int, str | None, Any, bytes]:
        headers = {"Accept": "application/json, text/event-stream",
                   "Content-Type": "application/json", **(routing or {})}
        if self.session_id and not routing:
            headers["Mcp-Session-Id"] = self.session_id
        # httpx's timeouts restart in every phase, so the total is checked here as each body chunk
        # arrives. The SDK sends a JSON response's headers and body together, so in practice the
        # limit is ~T; the worst case (a slow connect, then a slow first byte) is ~2*T. There is no
        # hard wall clock.
        deadline = time.monotonic() + self.timeout
        try:
            with self.client.stream("POST", self.url, content=line.encode("utf-8"),
                                    headers=headers) as response:
                chunks = []
                for chunk in response.iter_bytes():
                    chunks.append(chunk)
                    if time.monotonic() > deadline:
                        raise httpx.ReadTimeout(TIMEOUT_MESSAGE)
                status, session = response.status_code, response.headers.get("mcp-session-id")
        except httpx.TimeoutException:
            message = TIMEOUT_MESSAGE
        except (httpx.ConnectError, httpx.UnsupportedProtocol, httpx.InvalidURL):
            message = (f"Maestro Career Studio is not running at {self.backend_url}. "
                       "Start it with `maestro start` and try again.")
        except httpx.HTTPError:
            message = FAILED_MESSAGE
        else:
            body, raw = None, b"".join(chunks)
            if status == 200:
                try:
                    body = json.loads(raw)
                except (ValueError, RecursionError):
                    raise BridgeError(
                        "Maestro Career Studio returned an invalid JSON response.") from None
            return status, session, body, raw
        self.note(message)
        raise BridgeError(message)

    @staticmethod
    def accepted(result: tuple[int, str | None, Any, bytes]) -> tuple[int, str | None, Any, bytes]:
        if result[0] not in (200, 202):
            raise BridgeError(f"Maestro Career Studio returned HTTP {result[0]}.")
        return result

    def fail(self, request: Any, message: str) -> None:
        items = request if isinstance(request, list) else [request]
        errors = [{"jsonrpc": "2.0", "id": item["id"], "error": {"code": -32000, "message": message}}
                  for item in items if isinstance(item, dict) and "method" in item and "id" in item]
        if errors:
            self.write(errors if isinstance(request, list) else errors[0])

    def handle(self, line: str) -> None:
        if not line.strip():
            return
        try:
            request = json.loads(line)
        except (ValueError, RecursionError):  # RecursionError: a deeply nested "[[[[..."
            self.write({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            return
        if not isinstance(request, (dict, list)):
            self.note("The MCP message must be a JSON object or array.")
            return
        routing = routing_headers(request)
        if routing:
            # No session to send, adopt or replay: a 404 here is the server's answer, not a lost
            # session. subscriptions/listen would hold this one-at-a-time loop for its whole stream
            # if a set ever offered it; today every set refuses it at once.
            try:
                result = self.post(line, routing)
                refusal = refusal_for(request, result[0], result[3])
                if refusal is not None:
                    self.write(refusal)
                elif self.accepted(result)[0] == 200:
                    self.write(result[2])
            except BridgeError as exc:
                self.fail(request, str(exc))
            return
        method = request.get("method") if isinstance(request, dict) else None
        if method == "initialize":
            self.initialize_line = line
        elif method == "notifications/initialized":
            self.initialized_line = line
        try:
            result = self.post(line)
            if result[0] == 404 and self.session_id and self.initialize_line:
                # A restarted backend must see a fresh handshake without the stale id.
                self.session_id = None
                self.session_id = self.accepted(self.post(self.initialize_line))[1]
                if self.initialized_line:
                    self.accepted(self.post(self.initialized_line))
                result = self.post(line)
            self.accepted(result)
            if method == "initialize":
                self.session_id = result[1]
            if result[0] == 200:
                self.write(result[2])
        except BridgeError as exc:
            self.fail(request, str(exc))

    def serve(self, stdin: BinaryIO | None = None) -> int:
        for raw in (stdin or sys.stdin.buffer):
            self.handle(raw.decode("utf-8", "replace").rstrip("\r\n"))
        return 0


def backend_url_from(environ: dict[str, str] | None = None) -> str:
    """The URL this install's backend answers on; never creates or changes the folder."""
    environ = dict(os.environ if environ is None else environ)
    settings = read_env_file(resolve_home(environ) / "maestro.env")
    # The address, not `localhost`: on Windows `localhost` tries ::1 first and its refusal costs ~2 s.
    return f"http://127.0.0.1:{ports_from(settings, environ).backend}"


def run(url: str | None, profile: str = "full") -> int:
    """Serve stdin until EOF; SIGTERM and SIGINT end it quietly with exit code 0."""
    def stop(_number: int, _frame: Any) -> None:
        raise _Stop

    # Before the handlers: a bad maestro.env must not leave them installed.
    bridge = Bridge(url or backend_url_from(), profile)
    names = ("SIGINT", "SIGTERM") + (("SIGBREAK",) if sys.platform == "win32" else ())
    previous = {}
    for name in names:
        number = getattr(signal, name, None)
        if number is not None:
            previous[number] = signal.signal(number, stop)
    try:
        return bridge.serve()
    except _Stop:
        return 0
    except BrokenPipeError:  # the client went away
        # Python's own final stdout flush would fail again (exit 120): point it at devnull.
        with contextlib.suppress(OSError, ValueError):
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
