"""`maestro mcp`: Claude Desktop's stdio ↔ this install's /mcp. Twin of mcpb/server/index.js.

Imports nothing from `app` and applies no environment: it only needs the backend port, which
comes from the process environment, then the install's `maestro.env`, then the default.
"""
from __future__ import annotations

import contextlib
import json
import os
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

    def post(self, line: str) -> tuple[int, str | None, Any]:
        headers = {"Accept": "application/json, text/event-stream",
                   "Content-Type": "application/json"}
        if self.session_id:
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
            body = None
            if status == 200:
                try:
                    body = json.loads(b"".join(chunks))
                except (ValueError, RecursionError):
                    raise BridgeError(
                        "Maestro Career Studio returned an invalid JSON response.") from None
            return status, session, body
        self.note(message)
        raise BridgeError(message)

    @staticmethod
    def accepted(result: tuple[int, str | None, Any]) -> tuple[int, str | None, Any]:
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
