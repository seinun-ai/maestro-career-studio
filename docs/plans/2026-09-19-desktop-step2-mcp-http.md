# Desktop step 2, branch 2: MCP over HTTP, the bridge, the connect page, store readiness — implementation plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or
> superpowers:subagent-driven-development) to implement this plan task-by-task.

**Goal:** Any MCP-capable assistant connects to a running Maestro CS with a
URL or one click and no Docker, host Python or hand-edited config on the
client side; Claude Desktop keeps working through a Docker-free bundle; the
extension is ready for a Chrome Web Store upload the owner makes later.

**Architecture:** `/mcp` is mounted INSIDE the FastAPI process (stateful
sessions, JSON responses) so the existing loopback bind and Host → Origin →
CORS stack cover it with no second policy; every MCP tool runs off the event
loop (`_guard`) so the in-process server may call the backend over loopback
without deadlocking a single-worker uvicorn; scoped profiles are served by
path (`/mcp`, `/mcp/hunt`, …) from per-profile FastMCP instances sharing one
tool registry, with a request-scoped `ContextVar` feeding the workflow
hints; the `.mcpb` shim becomes a zero-dependency stdio↔HTTP bridge; a
`connect` endpoint composes every client's link server-side so pytest pins
the formats; old stdio routes get a one-release §13 window.

**Tech Stack:** FastAPI + Starlette mounts, `mcp` 1.29.1 (`FastMCP`,
`streamable_http_app`, `StreamableHTTPSessionManager`), anyio threads,
httpx, pytest (+ a subprocess uvicorn integration test), Node ≥ 18
(`fetch`, `node:test`) for the bridge, Next 16 for the settings section,
GitHub Actions.

Design: `docs/plans/2026-09-19-desktop-step2-design.md` §3 (serving,
security, profiles by path, bridge, connect page, declarations,
deprecations), §4 (store readiness), §6 (docs, SYSTEM.md), §7 gates G1,
G4–G9, §8 decisions. Branch 1 (`engines`) must be merged first: this plan
assumes `render_note`, `engine_available` and `setup/status.engines` exist.

---

## Before you start

- Work in a worktree branched from the MERGED `engines` result on local
  `main` (or from `claude/desktop-step2-engines-mcp` after its merge). Never
  `cd` to the main checkout (live stack on 3000/8001/55432, real `data/`).
  Never run `./scripts/update.sh`. Never `git stash`. Never push.
- Interpreter `/opt/anaconda3/bin/python3`; tests from `backend/`:
  `python3 -m pytest tests/ mcp_server/tests/ -q`. Ad-hoc scripts from
  `backend/` with `PYTHONPATH=.` (the editable install points at the main
  checkout). Node 18+ is on this machine (check `node --version`); the
  MCPB packer is `npx @anthropic-ai/mcpb pack` (network on first use).
- The pinned SDK is `mcp==1.29.1` in `backend/requirements.lock`; the
  anaconda interpreter has 1.26.0. Every SDK claim below was verified on
  1.26.0 during the brainstorm (deviation-log it if 1.29.1 differs):
  `FastMCP(json_response=True, streamable_http_path="/")`,
  `mcp.streamable_http_app()`, `mcp.session_manager.run()` (exists only
  AFTER `streamable_http_app()` was called), `mcp.settings.transport_security`
  defaults to protection OFF, sync tools are called directly on the event
  loop by `FuncMetadata.call_fn_with_arg_validation`, and an `async`
  `functools.wraps` wrapper keeps the input schema (`ctx` hidden) and
  `Context` injection.
- `asyncio_mode = "auto"` is set in `pyproject.toml`, so tests may be
  `async def`. Existing `mcp_server/tests` that call a guarded tool
  directly (e.g. the `# ---- @_guard ----` block in
  `test_onboarding_tools.py`) become `async def` + `await` in Task 1.
- Every commit message ends with
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Keep the **Deviation log** and **Gate results** tables at the end current.
- Suggested subagent model per task: default for Tasks 1, 2, 3, 4, 9, 11;
  `opus` for 5, 6, 7, 8, 10, 12.

---

### Task 1: Every tool runs off the event loop (`_guard`)

**Files:**
- Modify: `backend/mcp_server/server.py` (`_guard`, ~line 91)
- Modify: `backend/mcp_server/tests/test_onboarding_tools.py` (the `@_guard` block) and any other test that calls a guarded tool synchronously (`grep -rn "srv\.[a-z_]*(" mcp_server/tests | grep -v list_registered_tool_names`)
- Test: `backend/mcp_server/tests/test_guard.py` (new)

**Step 1: Write the failing tests**

```python
# backend/mcp_server/tests/test_guard.py
"""Design 2026-09-19 §3.1: the SDK calls a sync tool on the event loop, so a
tool that calls the backend over loopback would deadlock a single-worker
server. _guard runs the body in a worker thread and keeps the schema."""
import asyncio
import inspect
import threading

import pytest
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from mcp_server import server as srv
from mcp_server.client import BackendError


def test_guarded_tools_are_coroutine_functions():
    assert inspect.iscoroutinefunction(srv.list_jobs)
    assert inspect.iscoroutinefunction(srv.kb_capture)


async def test_the_body_runs_off_the_event_loop():
    probe = FastMCP("probe")

    @probe.tool()
    @srv._guard
    def which_thread(text: str, ctx: Context | None = None) -> dict:
        """Probe."""
        return {"thread": threading.current_thread().name, "ctx": type(ctx).__name__}

    tools = await probe.list_tools()
    assert list(tools[0].inputSchema["properties"]) == ["text"]  # ctx hidden
    result = await probe.call_tool("which_thread", {"text": "x"})
    body = result[0].text
    assert "MainThread" not in body
    assert "Context" in body


async def test_backend_errors_still_become_tool_errors():
    @srv._guard
    def boom() -> None:
        raise BackendError("nope")

    with pytest.raises(ToolError, match="nope"):
        await boom()


def test_a_sync_caller_gets_a_coroutine_not_a_result():
    # The old contract (call and get a dict) is gone on purpose; a test that
    # still relies on it must await.
    assert asyncio.iscoroutine(srv.list_registered_tool_names.__wrapped__()) is False if hasattr(
        srv.list_registered_tool_names, "__wrapped__") else True
```

(Drop the last test if it reads as contrived; the first three are the pins.)

**Step 2: Run** `python3 -m pytest mcp_server/tests/test_guard.py -q` → fails: `list_jobs` is not a coroutine function.

**Step 3: Implement**

```python
import anyio  # top of server.py


def _guard(fn):
    """Every tool body runs in a worker thread and BackendError becomes
    ToolError. Off-loop is load-bearing since /mcp is served in-process
    (design §3.1): the SDK awaits a coroutine but calls a plain function on
    the event loop, and the body calls the backend over loopback — on a
    single-worker uvicorn that is a deadlock. functools.wraps keeps the
    signature FastMCP reads for the input schema and Context injection."""

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await anyio.to_thread.run_sync(functools.partial(fn, *args, **kwargs))
        except BackendError as exc:
            raise ToolError(str(exc)) from exc

    return wrapper
```

Then fix every test that called a guarded tool synchronously: make the test
`async def` and `await` the call. `list_registered_tool_names()` is unchanged
(it already uses `asyncio.run(mcp.list_tools())`).

**Step 4: Run** `python3 -m pytest mcp_server/tests/ -q` → all pass (311 + new). `ruff check mcp_server`.

**Step 5: Commit** `feat(mcp): tools run off the event loop`.

---

### Task 2: Profiles by path — per-profile servers and a request-scoped profile

**Files:**
- Modify: `backend/mcp_server/profiles.py`
- Modify: `backend/mcp_server/server.py` (replace the import-time `apply_profile_filter(mcp)`; `_active_allowed_tools`; `main()`; `list_registered_tool_names`)
- Test: `backend/mcp_server/tests/test_profiles.py` (append)

**Step 1: Write the failing tests**

```python
from mcp_server import profiles, server as srv


def test_every_profile_has_its_own_server_sharing_the_registry():
    full = srv.server_for("full")
    hunt = srv.server_for("hunt")
    assert full is srv.mcp
    full_names = set(srv.tool_names(full))
    hunt_names = set(srv.tool_names(hunt))
    assert hunt_names == profiles.HUNT_TOOLS & full_names
    assert len(full_names) == 83
    # Same Tool objects, not copies: a docstring fix reaches every profile.
    assert full._tool_manager._tools["score_ats"] is hunt._tool_manager._tools["score_ats"]


def test_unknown_profile_is_rejected():
    import pytest
    with pytest.raises(ValueError):
        srv.server_for("nope")


def test_the_active_profile_is_request_scoped_with_the_env_default(monkeypatch):
    monkeypatch.delenv("MAESTRO_CS_MCP_PROFILE", raising=False)
    assert profiles.current_profile.get() == "full"
    token = profiles.current_profile.set("hunt")
    try:
        assert profiles.allowed_tools() == profiles.HUNT_TOOLS
        assert srv._active_allowed_tools() == profiles.HUNT_TOOLS
    finally:
        profiles.current_profile.reset(token)
    assert profiles.allowed_tools() is None
```

**Step 2: Run** → `AttributeError: server_for` / `current_profile`.

**Step 3: Implement**

`profiles.py`:

```python
from contextvars import ContextVar

# The profile of the CURRENT request (HTTP: set per request by the path
# router in app/main.py; stdio: the env default, set once in main()). One
# mechanism for both transports, one allowlist source.
current_profile: ContextVar[str] = ContextVar("mcp_profile", default="full")


def allowed_tools(profile: str | None = None) -> frozenset[str] | None:
    """Allowlist for ``profile`` (default: the current request's), None = all."""
    return PROFILE_ALLOWLISTS[get_profile(profile if profile is not None else current_profile.get())]
```

Delete `apply_profile_filter` (its only caller goes away below); keep
`get_profile` for env parsing.

`server.py`, after the last tool definition (replacing `_ACTIVE_PROFILE = apply_profile_filter(mcp)`):

```python
_SERVERS: dict[str, FastMCP] = {"full": mcp}


def tool_names(server: FastMCP) -> list[str]:
    return sorted(server._tool_manager._tools)


def server_for(profile: str) -> FastMCP:
    """One FastMCP per profile, built lazily from the full registry. The
    Tool objects are shared, not copied, so one docstring fix reaches every
    profile; only the visible set differs. Both transports use this: stdio
    runs the env profile's server, HTTP mounts one per path (app/main.py)."""
    name = get_profile(profile)
    if name not in _SERVERS:
        allow = allowed_tools(name)
        scoped = FastMCP(f"maestro-career-studio-{name}", json_response=True, streamable_http_path="/")
        scoped._tool_manager._tools = {
            k: v for k, v in mcp._tool_manager._tools.items() if k in allow
        }
        _SERVERS[name] = scoped
    return _SERVERS[name]


def _active_allowed_tools() -> "frozenset[str] | None":
    return allowed_tools()


def list_registered_tool_names(profile: str | None = None) -> list[str]:
    import asyncio

    tools = asyncio.run(server_for(profile or current_profile.get()).list_tools())
    return [t.name for t in tools]


def main() -> None:
    profile = get_profile()          # env, validated
    current_profile.set(profile)
    server_for(profile).run()        # stdio
```

`mcp = FastMCP("maestro-career-studio", json_response=True, streamable_http_path="/")`
at the top (the HTTP settings are harmless for stdio). Read the pinned SDK's
`FastMCP.__init__` for the exact kwarg names before writing them.

Every place that read `_ACTIVE_PROFILE` now reads `current_profile.get()`.
`_client_label` is untouched.

**Step 4: Run** `python3 -m pytest mcp_server/tests/ -q` — the cold-install
loop in CI runs `maestro-career-studio-mcp` per profile; locally run
`MAESTRO_CS_MCP_PROFILE=hunt python3 -m mcp_server.server < /dev/null` and
require exit 0.

**Step 5: Commit** `feat(mcp): per-profile servers over one registry; request-scoped active profile`.

---

### Task 3: Mount `/mcp` in the backend

**Files:**
- Create: `backend/app/mcp_mount.py`
- Modify: `backend/app/main.py` (lifespan; mount)
- Modify: `backend/pyproject.toml` (`mcp` from the `[mcp]` extra into `dependencies`; keep the extra as an empty alias for one release so `pip install -e ".[mcp]"` still works), `backend/requirements.lock` (regenerate per the Dockerfile recipe — inside `python:3.12-slim`, never on macOS; the pinned set should not change since the image already installed the extra; diff must be a header line)
- Modify: `docker-compose.yml` (no port change; add `MAESTRO_CS_PUBLIC_BACKEND_URL: http://localhost:${BACKEND_HOST_PORT:-8001}` to the backend env for Task 5)
- Test: `backend/tests/test_mcp_http.py` (new), `backend/tests/test_mcp_http_loopback.py` (new, integration)

**Step 1: Write the failing tests**

```python
# backend/tests/test_mcp_http.py
"""Design 2026-09-19 §3.1–3.3: /mcp lives inside the app, so one Host →
Origin → CORS policy covers it; JSON responses; profiles by path."""
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "pytest", "version": "0"}}}
INITIALIZED = {"jsonrpc": "2.0", "method": "notifications/initialized"}
LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}


@pytest.fixture
def client():
    with TestClient(app) as c:   # runs the lifespan → session manager
        yield c


def _session(client, path="/mcp"):
    r = client.post(path, json=INIT, headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/json")  # never SSE
    sid = r.headers["mcp-session-id"]
    r2 = client.post(path, json=INITIALIZED, headers={**HEADERS, "mcp-session-id": sid})
    assert r2.status_code == 202
    return sid


def test_initialize_and_list_tools_over_json(client):
    sid = _session(client)
    r = client.post("/mcp", json=LIST, headers={**HEADERS, "mcp-session-id": sid})
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert len(names) == 83


def test_profile_paths_serve_their_allowlists(client):
    from mcp_server import profiles

    sid = _session(client, "/mcp/hunt")
    r = client.post("/mcp/hunt", json=LIST, headers={**HEADERS, "mcp-session-id": sid})
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert names == profiles.HUNT_TOOLS & names and names <= profiles.HUNT_TOOLS
    assert client.post("/mcp/nope", json=INIT, headers=HEADERS).status_code == 404


def test_a_hidden_tool_called_by_name_is_refused(client):
    sid = _session(client, "/mcp/explore")
    call = {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "kb_capture", "arguments": {}}}
    r = client.post("/mcp/explore", json=call, headers={**HEADERS, "mcp-session-id": sid})
    body = r.json()
    assert "error" in body or body.get("result", {}).get("isError")


def test_forged_host_is_400_and_foreign_origin_is_403(client):
    assert client.post("/mcp", json=INIT, headers={**HEADERS, "Host": "evil.example"}).status_code == 400
    assert client.post("/mcp", json=INIT, headers={**HEADERS, "Origin": "https://evil.example"}).status_code == 403


def test_json_responses_are_pinned():
    from mcp_server import server as srv

    assert srv.mcp.settings.json_response is True
    assert srv.server_for("hunt").settings.json_response is True
```

```python
# backend/tests/test_mcp_http_loopback.py
"""The load-bearing test: a real single-worker uvicorn serves /mcp AND
answers the loopback REST calls the tools make. If _guard ever runs a tool
on the loop again, this hangs and the timeout fails it."""
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.integration

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server(tmp_path):
    port = _free_port()
    env = {**os.environ,
           "DATA_DIR": str(tmp_path / "data"), "BASE_RESUMES_DIR": str(tmp_path / "br"),
           "APPLICATIONS_DIR": str(tmp_path / "apps"), "SETTINGS_DIR": str(tmp_path / "settings"),
           "LOGS_DIR": str(tmp_path / "logs"), "EXPORTS_DIR": str(tmp_path / "exports"),
           "KB_DOCUMENTS_DIR": str(tmp_path / "kb"),
           "BACKEND_URL": f"http://127.0.0.1:{port}",   # the tools' loopback target
           "MAESTRO_CS_PUBLIC_BACKEND_URL": f"http://127.0.0.1:{port}"}
    for k in ("DATA_DIR", "BASE_RESUMES_DIR", "APPLICATIONS_DIR", "SETTINGS_DIR",
              "LOGS_DIR", "EXPORTS_DIR", "KB_DOCUMENTS_DIR"):
        Path(env[k]).mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port),
                             "--host", "127.0.0.1", "--log-level", "warning"],
                            env=env, cwd=Path(__file__).resolve().parents[1])
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            if httpx.get(base + "/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.25)
    else:
        proc.kill()
        pytest.fail("uvicorn did not come up")
    try:
        yield base
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_a_tool_that_calls_the_backend_completes_under_one_worker(server):
    with httpx.Client(base_url=server, timeout=30) as c:
        r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                 "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                            "clientInfo": {"name": "loopback", "version": "0"}}},
                   headers=HEADERS)
        sid = r.headers["mcp-session-id"]
        h = {**HEADERS, "mcp-session-id": sid}
        c.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=h)
        r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                 "params": {"name": "list_jobs", "arguments": {}}}, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "result" in body and not body["result"].get("isError"), body
```

Register the `integration` marker in `pyproject.toml` (`markers`). CI runs
it (no service needed); a developer may `-m "not integration"`.

**Step 2: Run** → 404 on `/mcp` (nothing mounted).

**Step 3: Implement**

`app/mcp_mount.py`:

```python
"""Mount point for the MCP server INSIDE the FastAPI app (design §3.1–3.3).

Why in-process: one port, one process, and the app's Host → Origin → CORS
stack already covers /mcp — no second security definition, no second
sidecar for the desktop shell. Why a path router: FastMCP filters tools per
instance, so each profile gets its own instance over the shared registry
(mcp_server.server.server_for) and the first path segment picks it.
"""
from contextlib import AsyncExitStack, asynccontextmanager

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp_server import profiles
from mcp_server.server import server_for


class ProfileRouter:
    """`/mcp` → full, `/mcp/<profile>` → that profile, else 404. Sets the
    request-scoped profile the workflow hints read, then hands the request
    to that profile's streamable-HTTP app with the path rewritten to "/"."""

    def __init__(self) -> None:
        self.apps: dict[str, ASGIApp] = {
            name: server_for(name).streamable_http_app() for name in sorted(profiles.VALID_PROFILES)
        }

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.apps["full"](scope, receive, send)
            return
        segment = scope["path"].strip("/")
        profile = segment or "full"
        if profile not in self.apps:
            await JSONResponse({"detail": "unknown MCP profile"}, status_code=404)(scope, receive, send)
            return
        token = profiles.current_profile.set(profile)
        try:
            await self.apps[profile]({**scope, "path": "/", "raw_path": b"/"}, receive, send)
        finally:
            profiles.current_profile.reset(token)


@asynccontextmanager
async def run_session_managers():
    """Every profile's StreamableHTTPSessionManager must be running for the
    app's lifetime; the SDK creates it lazily on streamable_http_app()."""
    async with AsyncExitStack() as stack:
        for name in sorted(profiles.VALID_PROFILES):
            await stack.enter_async_context(server_for(name).session_manager.run())
        yield
```

`app/main.py`:

```python
from app.mcp_mount import ProfileRouter, run_session_managers

@asynccontextmanager
async def lifespan(app: FastAPI):
    seeding.run_startup()
    _log_llm_config()
    async with run_session_managers():
        yield
    tracing.shutdown()

# after the routers:
app.mount("/mcp", ProfileRouter())
```

Order matters: the mount must be added BEFORE the middleware calls? No —
`add_middleware` wraps the whole app including mounts regardless of order;
confirm with the forged-Host test. Confirm the SDK's `transport_security`
stays at its default (protection off) — the app's middleware is the one
definition (§3.2); add a one-line comment saying so.

`pyproject.toml`: move `"mcp>=1.2,<2"` into `dependencies` (keep the
comment about the 2.0 API move); leave `mcp = []` under
`[project.optional-dependencies]` with a comment "empty alias, one release
(SYSTEM.md §13 `mcp-stdio-venv`)". Regenerate `requirements.lock` inside
`python:3.12-slim` exactly as the Dockerfile comment says; the diff must be
the header line only.

**Step 4: Run** `python3 -m pytest tests/test_mcp_http.py tests/test_mcp_http_loopback.py tests/test_frontend_host_guard.py tests/test_security_boundaries.py -q`, then the full suite.

**Step 5: Commit** `feat(mcp): /mcp mounted in the backend, profiles by path, JSON responses`.

---

### Task 4: The bridge — `mcpb/server/index.js` as a stdio↔HTTP proxy

**Files:**
- Rewrite: `mcpb/server/index.js`
- Modify: `mcpb/manifest.json` (`user_config`: `backend_url` + `profile`; drop `container_name`/`docker_path`; `compatibility.platforms: ["darwin","win32","linux"]`; env: `MAESTRO_CS_BACKEND_URL`, `MAESTRO_CS_MCP_PROFILE`; description no longer mentions Docker)
- Rewrite: `mcpb/tests/shim.test.js` → `mcpb/tests/bridge.test.js`
- Re-pack: `cd mcpb && npx @anthropic-ai/mcpb pack . maestro-career-studio.mcpb`; `python3 scripts/check_mcpb_bundle.py` must pass (its TRACKED map is unchanged)

**Step 1: Write the failing tests** (`node --test mcpb/tests/`)

```js
// mcpb/tests/bridge.test.js
// Run: node --test mcpb/tests/   (zero dependencies: node:test + node:http)
"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
const http = require("node:http");
const { spawn } = require("node:child_process");
const path = require("node:path");

const BRIDGE = path.join(__dirname, "..", "server", "index.js");
const INIT = { jsonrpc: "2.0", id: 1, method: "initialize",
  params: { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "t", version: "0" } } };
const INITIALIZED = { jsonrpc: "2.0", method: "notifications/initialized" };
const LIST = { jsonrpc: "2.0", id: 2, method: "tools/list" };

function fakeServer(behaviour) {
  const seen = [];
  const server = http.createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      const msg = JSON.parse(body);
      seen.push({ path: req.url, sid: req.headers["mcp-session-id"], method: msg.method });
      behaviour(msg, req, res, seen);
    });
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve({ server, seen, port: server.address().port })));
}

function runBridge(env, lines) {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, [BRIDGE], { env: { PATH: "", HOME: process.env.HOME, ...env }, stdio: ["pipe", "pipe", "pipe"] });
    let out = "", err = "";
    child.stdout.on("data", (c) => (out += c));
    child.stderr.on("data", (c) => (err += c));
    child.on("exit", (code) => resolve({ code, out, err }));
    for (const l of lines) child.stdin.write(JSON.stringify(l) + "\n");
    child.stdin.end();
  });
}

test("initialize → initialized → tools/list round-trips with the session header", async () => {
  const { server, seen, port } = await fakeServer((msg, req, res) => {
    if (msg.method === "initialize") { res.setHeader("mcp-session-id", "S1"); res.setHeader("content-type", "application/json"); res.end(JSON.stringify({ jsonrpc: "2.0", id: msg.id, result: { serverInfo: { name: "fake" } } })); }
    else if (msg.method === "notifications/initialized") { res.statusCode = 202; res.end(); }
    else { res.setHeader("content-type", "application/json"); res.end(JSON.stringify({ jsonrpc: "2.0", id: msg.id, result: { tools: [] } })); }
  });
  const r = await runBridge({ MAESTRO_CS_BACKEND_URL: `http://127.0.0.1:${port}` }, [INIT, INITIALIZED, LIST]);
  server.close();
  const outLines = r.out.trim().split("\n").map((l) => JSON.parse(l));
  assert.strictEqual(outLines.length, 2, "a 202 notification writes nothing to stdout");
  assert.strictEqual(outLines[1].id, 2);
  assert.deepStrictEqual(seen.map((s) => s.sid), [undefined, "S1", "S1"]);
  assert.ok(seen.every((s) => s.path === "/mcp"));
});

test("a profile becomes a path segment", async () => {
  const { server, seen, port } = await fakeServer((msg, req, res) => { res.setHeader("mcp-session-id", "S"); res.setHeader("content-type", "application/json"); res.end(JSON.stringify({ jsonrpc: "2.0", id: msg.id, result: {} })); });
  await runBridge({ MAESTRO_CS_BACKEND_URL: `http://127.0.0.1:${port}`, MAESTRO_CS_MCP_PROFILE: "hunt" }, [INIT]);
  server.close();
  assert.strictEqual(seen[0].path, "/mcp/hunt");
});

test("a 404 on a known session replays initialize and retries once", async () => {
  let sessions = 0;
  const { server, seen, port } = await fakeServer((msg, req, res) => {
    if (msg.method === "initialize") { sessions += 1; res.setHeader("mcp-session-id", `S${sessions}`); res.setHeader("content-type", "application/json"); res.end(JSON.stringify({ jsonrpc: "2.0", id: msg.id, result: {} })); return; }
    if (msg.method === "notifications/initialized") { res.statusCode = 202; res.end(); return; }
    if (req.headers["mcp-session-id"] === "S1") { res.statusCode = 404; res.end("session not found"); return; }
    res.setHeader("content-type", "application/json"); res.end(JSON.stringify({ jsonrpc: "2.0", id: msg.id, result: { tools: [] } }));
  });
  const r = await runBridge({ MAESTRO_CS_BACKEND_URL: `http://127.0.0.1:${port}` }, [INIT, INITIALIZED, LIST]);
  server.close();
  const outLines = r.out.trim().split("\n").map((l) => JSON.parse(l));
  assert.strictEqual(outLines.at(-1).id, 2, "the retried request answers with the ORIGINAL id");
  assert.strictEqual(sessions, 2);
  assert.deepStrictEqual(seen.map((s) => s.method), ["initialize", "notifications/initialized", "tools/list", "initialize", "notifications/initialized", "tools/list"]);
});

test("a refused connection is one sentence on stderr and a JSON-RPC error on stdout", async () => {
  const r = await runBridge({ MAESTRO_CS_BACKEND_URL: "http://127.0.0.1:1" }, [INIT]);
  assert.match(r.err, /\[maestro-career-studio\] Maestro CS is not running/);
  const line = JSON.parse(r.out.trim().split("\n")[0]);
  assert.strictEqual(line.id, 1);
  assert.ok(line.error);
});

test("unsaved user_config placeholders are ignored, not obeyed", async () => {
  const { server, seen, port } = await fakeServer((msg, req, res) => { res.setHeader("content-type", "application/json"); res.end(JSON.stringify({ jsonrpc: "2.0", id: msg.id, result: {} })); });
  // A placeholder backend_url must fall back to the default, which is NOT this fake server; assert nothing reached it.
  await runBridge({ MAESTRO_CS_BACKEND_URL: "${user_config.backend_url}", MAESTRO_CS_MCP_PROFILE: "${user_config.profile}" }, [INIT]);
  server.close();
  assert.strictEqual(seen.length, 0);
});

test("stdout never carries anything but JSON-RPC", async () => {
  const r = await runBridge({ MAESTRO_CS_BACKEND_URL: "http://127.0.0.1:1" }, [INIT]);
  for (const l of r.out.trim().split("\n").filter(Boolean)) JSON.parse(l);
});
```

**Step 2: Run** `node --test mcpb/tests/` → fails (the shim spawns docker).

**Step 3: Implement** `mcpb/server/index.js`:

```js
#!/usr/bin/env node
// Stdio ↔ Streamable-HTTP bridge: Claude Desktop <-> the MCP server INSIDE
// the Maestro CS backend (design 2026-09-19 §3.4).
//
// Why a bridge at all: Claude Desktop's custom connectors take a public
// https:// URL only, so a local server must be a stdio child process. Why
// this is not `docker exec` any more: the backend serves /mcp itself, so the
// client side needs neither Docker nor a host Python — only the Node that
// ships inside Claude Desktop. Zero dependencies, so the packed bundle stays
// small enough to commit.
//
// Protocol shape, kept deliberately simple by the server: stateful sessions
// (Mcp-Session-Id) and JSON responses (never SSE). Each stdin line is one
// JSON-RPC message → one POST. A 202 (notification) writes nothing back.
// A 404 on a known session means the backend restarted: replay the cached
// initialize + initialized, adopt the new id, retry the message once.
"use strict";

const fs = require("node:fs");
const readline = require("node:readline");

// Claude Desktop passes an unfilled user_config field as its LITERAL
// placeholder, not an empty string — screen every value before believing it.
const setting = (name) => {
  const raw = (process.env[name] || "").trim();
  return /^\$\{.*\}$/.test(raw) ? "" : raw;
};

const backend = (setting("MAESTRO_CS_BACKEND_URL") || "http://localhost:8001").replace(/\/+$/, "");
const profile = setting("MAESTRO_CS_MCP_PROFILE") || "full";
const url = profile === "full" ? `${backend}/mcp` : `${backend}/mcp/${profile}`;

const log = (message) => fs.writeSync(2, `\n[maestro-career-studio] ${message}\n`);
const emit = (obj) => process.stdout.write(JSON.stringify(obj) + "\n");

let sessionId = null;
let cachedInit = null;          // the initialize request, for replay after a restart
let replaying = false;

async function post(message) {
  const headers = { "content-type": "application/json", accept: "application/json, text/event-stream" };
  if (sessionId) headers["mcp-session-id"] = sessionId;
  const res = await fetch(url, { method: "POST", headers, body: JSON.stringify(message) });
  const sid = res.headers.get("mcp-session-id");
  if (sid) sessionId = sid;
  return res;
}

async function reinitialize() {
  if (!cachedInit || replaying) return false;
  replaying = true;
  try {
    sessionId = null;
    const res = await post(cachedInit);
    if (!res.ok) return false;
    await post({ jsonrpc: "2.0", method: "notifications/initialized" });
    return true;
  } finally {
    replaying = false;
  }
}

function rpcError(message, id, text) {
  return { jsonrpc: "2.0", id: id === undefined ? null : id, error: { code: -32000, message: text } };
}

async function handle(message) {
  if (message.method === "initialize") cachedInit = message;
  let res;
  try {
    res = await post(message);
    if (res.status === 404 && sessionId && message.method !== "initialize") {
      if (await reinitialize()) res = await post(message);
    }
  } catch (err) {
    log("Maestro CS is not running (" + (err.cause?.code || err.message) + "). Start it with " +
        "`docker compose up -d` from your checkout, or open the app, then retry.");
    if (message.id !== undefined) emit(rpcError(message, message.id, "Maestro CS backend unreachable at " + url));
    return;
  }
  if (res.status === 202) return;                       // a notification: nothing to write
  const text = await res.text();
  if (!res.ok) {
    if (message.id !== undefined) emit(rpcError(message, message.id, `backend answered ${res.status}: ${text.slice(0, 200)}`));
    return;
  }
  // The server is configured for JSON responses; an SSE body here means a
  // misconfigured server, and saying so beats silently hanging the client.
  if ((res.headers.get("content-type") || "").startsWith("text/event-stream")) {
    log("the backend answered with SSE; this bridge expects JSON responses (json_response=True).");
    if (message.id !== undefined) emit(rpcError(message, message.id, "unexpected SSE response"));
    return;
  }
  process.stdout.write(text.trim() + "\n");
}

const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
let chain = Promise.resolve();
rl.on("line", (line) => {
  if (!line.trim()) return;
  let message;
  try { message = JSON.parse(line); } catch { log("ignoring a non-JSON line from the client"); return; }
  chain = chain.then(() => handle(message));   // strictly in order
});
rl.on("close", () => { chain.then(() => process.exit(0)); });
for (const stream of [process.stdin, process.stdout]) {
  stream.on("error", (err) => { if (err && err.code !== "EPIPE") throw err; });
}
```

Batches (arrays) pass through `post` unchanged — `handle` receives the
array; guard `message.method` reads with `Array.isArray` (treat an array as
a request with no cached-init semantics and always write the reply).

`manifest.json` `user_config`:

```json
"backend_url": {"type": "string", "title": "Backend URL",
  "description": "Where Maestro CS is running. The default is right for docker compose; change the port only if you changed BACKEND_HOST_PORT in .env.",
  "default": "http://localhost:8001", "required": false},
"profile": { …unchanged… }
```

and `"env": {"MAESTRO_CS_BACKEND_URL": "${user_config.backend_url}", "MAESTRO_CS_MCP_PROFILE": "${user_config.profile}"}`,
`"compatibility": {"platforms": ["darwin", "win32", "linux"], "runtimes": {"node": ">=18.0.0"}}`.
Update `description`/`long_description` (no Docker mention; "requires the
app to be running").

**Step 4: Run** `node --test mcpb/tests/` → 6 pass; re-pack; `python3 scripts/check_mcpb_bundle.py` OK.

**Step 5: Commit** `feat(mcpb): zero-dependency stdio↔HTTP bridge replaces the docker exec shim`.

---

### Task 5: The connect endpoint

**Files:**
- Modify: `backend/app/config.py` (`maestro_cs_public_backend_url: str | None = None`; `maestro_cs_mcpb_bundle_path: Path = Path("/app/mcpb/maestro-career-studio.mcpb")`)
- Create: `backend/app/schemas/connect.py`, `backend/app/services/connect.py`
- Modify: `backend/app/routers/setup.py` (two routes)
- Modify: `docker-compose.yml` (the env var from Task 3; volume `./mcpb:/app/mcpb:ro`)
- Test: `backend/tests/test_connect.py`

**Step 1: Write the failing tests**

```python
import base64
import json
from urllib.parse import unquote

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def _client(db_session):
    from app.db import get_db
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_connect_composes_every_client_from_the_public_url(db_session, monkeypatch):
    monkeypatch.setattr(settings, "maestro_cs_public_backend_url", "http://localhost:8001")
    try:
        body = _client(db_session).get("/api/setup/connect").json()
    finally:
        app.dependency_overrides.clear()
    assert body["backend_url"] == "http://localhost:8001"
    assert body["mcp_url"] == "http://localhost:8001/mcp"
    assert {p["name"]: p["url"] for p in body["profiles"]}["hunt"] == "http://localhost:8001/mcp/hunt"
    clients = {c["id"]: c for c in body["clients"]}
    assert clients["claude-code"]["value"] == "claude mcp add --transport http maestro-career-studio http://localhost:8001/mcp"
    assert clients["codex"]["value"] == "codex mcp add maestro-career-studio --url http://localhost:8001/mcp"
    cursor = clients["cursor"]["value"]
    assert cursor.startswith("cursor://anysphere.cursor-deeplink/mcp/install?name=maestro-career-studio&config=")
    assert json.loads(base64.b64decode(cursor.split("config=")[1])) == {"url": "http://localhost:8001/mcp"}
    vscode = clients["vscode"]["value"]
    assert vscode.startswith("vscode:mcp/install?")
    assert json.loads(unquote(vscode.split("?", 1)[1])) == {"name": "maestro-career-studio", "type": "http", "url": "http://localhost:8001/mcp"}
    assert clients["other"]["value"] == "http://localhost:8001/mcp"
    assert clients["claude-desktop"]["kind"] == "download"


def test_profile_query_rewrites_every_value(db_session, monkeypatch):
    monkeypatch.setattr(settings, "maestro_cs_public_backend_url", "http://localhost:8001")
    try:
        body = _client(db_session).get("/api/setup/connect?profile=hunt").json()
    finally:
        app.dependency_overrides.clear()
    clients = {c["id"]: c for c in body["clients"]}
    assert clients["claude-code"]["value"].endswith("maestro-career-studio-hunt http://localhost:8001/mcp/hunt")
    assert "/mcp/hunt" in clients["other"]["value"]


def test_unknown_profile_is_422(db_session):
    try:
        assert _client(db_session).get("/api/setup/connect?profile=nope").status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_bundle_is_served_when_present_and_404_otherwise(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "maestro_cs_mcpb_bundle_path", tmp_path / "x.mcpb")
    try:
        c = _client(db_session)
        assert c.get("/api/setup/connect").json()["bundle_available"] is False
        assert c.get("/api/setup/connect/bundle").status_code == 404
        (tmp_path / "x.mcpb").write_bytes(b"PK\x03\x04fake")
        r = c.get("/api/setup/connect/bundle")
        assert r.status_code == 200 and r.content.startswith(b"PK")
        assert "maestro-career-studio.mcpb" in r.headers["content-disposition"]
    finally:
        app.dependency_overrides.clear()
```

**Step 2: Run** → 404.

**Step 3: Implement** — `services/connect.py`:

```python
SERVER_NAME = "maestro-career-studio"


def _name(profile: str) -> str:
    return SERVER_NAME if profile == "full" else f"{SERVER_NAME}-{profile}"


def mcp_url(base: str, profile: str) -> str:
    return f"{base}/mcp" if profile == "full" else f"{base}/mcp/{profile}"


def clients(base: str, profile: str, bundle_available: bool) -> list[dict]:
    url, name = mcp_url(base, profile), _name(profile)
    cursor_cfg = base64.b64encode(json.dumps({"url": url}).encode()).decode()
    vscode_cfg = quote(json.dumps({"name": name, "type": "http", "url": url}), safe="")
    return [
        {"id": "claude-code", "label": "Claude Code", "kind": "command",
         "value": f"claude mcp add --transport http {name} {url}"},
        {"id": "codex", "label": "Codex", "kind": "command",
         "value": f"codex mcp add {name} --url {url}"},
        {"id": "cursor", "label": "Cursor", "kind": "deeplink",
         "value": f"cursor://anysphere.cursor-deeplink/mcp/install?name={name}&config={cursor_cfg}"},
        {"id": "vscode", "label": "VS Code", "kind": "deeplink",
         "value": f"vscode:mcp/install?{vscode_cfg}"},
        {"id": "claude-desktop", "label": "Claude Desktop", "kind": "download",
         "value": "/api/setup/connect/bundle" if bundle_available else "mcpb/maestro-career-studio.mcpb"},
        {"id": "other", "label": "Any other MCP client (HTTP)", "kind": "url", "value": url},
    ]
```

`public_backend_url()` = `settings.maestro_cs_public_backend_url or "http://localhost:8000"`,
trailing slash stripped. Router: `GET /api/setup/connect` (`profile: Literal[...] = "full"`)
and `GET /api/setup/connect/bundle` → `FileResponse(path, media_type="application/zip", filename="maestro-career-studio.mcpb")`
or 404 `{"detail": "The bundle is not mounted here; install it from mcpb/maestro-career-studio.mcpb in your checkout."}`.
Compose: `MAESTRO_CS_PUBLIC_BACKEND_URL: http://localhost:${BACKEND_HOST_PORT:-8001}` and `- ./mcpb:/app/mcpb:ro`.

**Step 4–5:** tests, ruff, full suite; commit `feat(setup): connect endpoint composes every client's link; bundle download`.

---

### Task 6: "Connect your assistant" in Settings and the getting-started row

**Files:**
- Create: `frontend/components/settings/connect-section.tsx`
- Modify: `frontend/app/settings/page.tsx` (add the section after `McpWorkflowSection`), `frontend/lib/types.ts` (`ConnectInfo`, `ConnectClient`), `frontend/components/setup/setup-steps.ts` (a non-blocking "Connect your assistant" row linking to `/settings#connect`; `done` = false is wrong — there is no signal; make it a plain link row, not a step, if `SetupStepView` cannot express "informational"; otherwise skip the checklist and rely on the Settings section)

Rows per client with a copy button for `command`/`url`, an `<a href>` for
`deeplink` (Cursor/VS Code links open the app; note that browsers may ask
to allow the protocol), and a download link for `download`. A profile
`<select>` (full + five) refetches `?profile=`. Reuse `SettingCard`,
`IconButton` + `Copy` as `about-section.tsx` does. Gates: tsc, lint, build.

Commit `feat(ui): Connect your assistant settings section`.

---

### Task 7: Declarations, examples, the setup-script deprecation

**Files:**
- Modify: `plugins/maestro-career-studio/.mcp.json` → `{"maestro-career-studio": {"type": "http", "url": "http://localhost:8001/mcp"}}`
- Verify Codex: does the Codex plugin format accept an HTTP server in the `.mcp.json` it points at (`.codex-plugin/plugin.json` `mcpServers`)? Check OpenAI's plugin docs (WebFetch) and `codex plugin` behaviour if the CLI is installed here. If NOT: point `.codex-plugin/plugin.json` at a new `./.mcp.codex.json` carrying the old `docker exec` entry for one release, and say so in the README.
- Modify: `backend/mcp_server/claude_desktop_config.example.json` (bridge form: `"command": "node", "args": ["/absolute/path/to/maestro-career-studio/mcpb/server/index.js"], "env": {"MAESTRO_CS_BACKEND_URL": …, "MAESTRO_CS_MCP_PROFILE": …}` for each profile), `codex_config.example.toml` (`url = "http://localhost:8001/mcp"` form)
- Modify: `scripts/setup-mcp.sh`: print a deprecation banner at the top ("this route leaves in the next release; the app's Settings → Connect your assistant page gives every client a URL or one click") and, in the final printed block, the three one-liners (Claude Code, Codex, raw URL). Behaviour otherwise unchanged; `shellcheck scripts/*.sh` clean.
- Test: `backend/tests/test_plugin_declarations.py` — reads the two JSON files and the two examples, asserts the HTTP shapes.

Commit `chore(mcp): plugin and example declarations move to the URL; setup-mcp.sh deprecation banner`.

---

### Task 8: Extension store readiness (code now, listing later)

**Files:**
- Create: `extension/options.html`, `extension/options.js` (`backendUrl`, `appUrl` fields; "Test connection" → `GET ${backendUrl}/health`; saves to `chrome.storage.sync`); `extension/manifest.json` gains `"options_ui": {"page": "options.html", "open_in_tab": false}`
- Create: `scripts/pack_extension.py` (stdlib; zips `extension/` minus `README.md`, tests, dotfiles; `--first-upload` strips `key`; checks `manifest.version == pyproject version`; writes `dist/maestro-cs-companion-<version>.zip`)
- Create: `extension/STORE_LISTING.md`, `docs/PRIVACY.md`
- Modify: `docs/RELEASING.md` (§10 Chrome Web Store), `extension/README.md` (options page; the id swap), `backend/app/config.py` comment on `maestro_cs_extension_ids` (the store id is appended after the first upload)
- Test: `backend/tests/test_extension_store_readiness.py` — `pack_extension.py --first-upload` into `tmp_path` produces a zip whose manifest has no `key` and whose version matches; without the flag the key is kept; `options.html` exists and the manifest declares it; `sw.js` still reads `backendUrl` from `storage.sync` (source pin like the other extension tests).

Commit `feat(extension): options page, store packaging script, listing and privacy texts`.

---

### Task 9: CI without Docker for the MCP cold install

**Files:** `.github/workflows/ci.yml` (`mcp-cold-install` job)

Replace the six-profile stdio loop with: `pip install -e "."` (no extra — `mcp`
is core now), start `uvicorn app.main:app --port 8765` in the background with
temp data dirs, wait for `/health`, POST `initialize` → `tools/list` on `/mcp`
and on `/mcp/hunt` (assert 83 and the hunt count), one `tools/call`
(`get_health_report` or `list_jobs`), then `node --test mcpb/tests/`, then
`python3 scripts/check_mcpb_bundle.py`. Keep the stdio smoke for ONE profile
(`maestro-career-studio-mcp < /dev/null` exits 0) for the deprecation window.

Commit `ci: MCP cold install over /mcp and the bridge tests, no Docker`.

---

### Task 10: User docs

README (the "Driving it from Claude, Codex, or ChatGPT (MCP)" section
rewritten URL-first: Claude Desktop = bundle; Claude Code/Codex/Cursor/VS
Code = the Settings page's links or the one-liners; the "keep the transport
STDIO" paragraph replaced by the true rule: never publish port 8001 beyond
loopback, never proxy `/mcp` publicly), `docs/GETTING_STARTED.md` §6 (three
routes; Part 3 mentions the options page), `SECURITY.md` (`/mcp` shares the
loopback boundary; the SDK's own DNS-rebinding protection is off because
the app's Host/Origin middleware is the one definition), `KNOWN_ISSUES.md`
(profiles by path; stdio-venv leaving next release; store listing pending),
`CHANGELOG.md`, `backend/mcp_server/README.md` (transport, profile paths,
the bridge, the connect page), `extension/README.md`.

Commit `docs: MCP over HTTP, the bridge, the connect page, store readiness`.

---

### Task 11: SYSTEM.md, pins, ledger

At the cap: net-zero or paired with grooming, word-stream verified. §2/§3
(`mcp_mount.py`, `/mcp` on the backend, `connect`, the bridge); §6 two
pinned invariants: `{#inv-mcp-inside-the-app}` (pin: `tests/test_mcp_http.py::test_forged_host_is_400_and_foreign_origin_is_403`,
`app/mcp_mount.py::ProfileRouter`) and `{#inv-tools-off-loop}` (pin:
`tests/test_mcp_http_loopback.py::test_a_tool_that_calls_the_backend_completes_under_one_worker`,
`mcp_server/server.py::_guard`); §7 transport paragraph rewritten (HTTP +
bridge; profiles by path; `mcp.run()` is the stdio path of `server_for`);
§9 (`BACKEND_URL` loopback for a venv run; `MAESTRO_CS_PUBLIC_BACKEND_URL`);
§12 gotchas (stateless HTTP drops `clientInfo`; the mount path composes
`/mcp` + `streamable_http_path`, hence `"/"`; Claude Desktop connectors
refuse localhost); §13 rows `mcp-stdio-venv` (trigger: next release; delete
`setup-mcp.sh`, the venv docs, the `docker exec` examples, the empty `[mcp]`
extra) and `extension-id-swap` (trigger: one release after the store key is
committed; delete the old id). `.system_md_enforcement.json` gets both pins.

Commit `docs(system): /mcp inside the app; tools off-loop; ledger rows`.

---

### Task 12: Verification and gates

G1 (suite, ruff, `check_system_md`, `check_mcpb_bundle`, `node --test mcpb/tests`, slop ratchet backend+frontend+extension).
G4 the loopback integration test plus a manual run: uvicorn single worker,
`initialize → tools/list → list_jobs → render_pdf → get_rendered_pdf` over
`/mcp` with curl.
G5 Claude Desktop installs the re-packed `.mcpb` on the maintainer's Mac
against a fresh worktree stack (NOT the live compose stack; run uvicorn +
next dev on spare ports and set the bundle's Backend URL to that port),
runs `get_health_report`, then `kill -HUP`/restart the uvicorn and runs
another tool: the bridge must replay and succeed.
G6 `claude mcp add --transport http` lists 83 tools; a Cursor deep link
installs (if Cursor is present); `codex mcp add --url` lists 83 (if Codex
is present); `/mcp/hunt` lists exactly the hunt allowlist.
G7 `curl -H 'Host: evil.example'` → 400; `curl -H 'Origin: https://evil.example'` → 403.
G8 `python3 scripts/pack_extension.py --first-upload` → load unpacked from
the unzipped dir → a different id → CORS-refused → add the id to
`MAESTRO_CS_EXTENSION_IDS` on the scratch stack → works.
G9 `./scripts/setup-mcp.sh --print-only --skip-install` prints the banner.

Record each in the Gate results table; commit.

---

## Deviation log (append-only)

| # | Task | What the plan said | What was done instead | Why |
|---|---|---|---|---|
| | | | | |

## Gate results

| Gate | Result | Evidence |
|---|---|---|
| G1 | | |
| G4 | | |
| G5 | | |
| G6 | | |
| G7 | | |
| G8 | | |
| G9 | | |

## LLM-call audit

None planned. G4–G6 use read tools and `render_pdf` on the seeded example
resume; no API key is set on the scratch stack.
