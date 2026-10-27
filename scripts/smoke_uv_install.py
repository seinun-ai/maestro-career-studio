#!/usr/bin/env python3
"""End-to-end proof that a built wheel installs with `uv tool install` and runs.

    python3 scripts/smoke_uv_install.py --wheel dist/maestro_career_studio-X-py3-none-any.whl
                                        [--expect-version X] [--keep]

Stdlib only; runs on macOS, Linux and Windows. Everything lives in one temp folder (tool dir,
shim dir, MAESTRO_HOME) that is deleted at the end unless --keep: a uv venv is ~500 MB, and a
full disk first shows up as SQLite I/O errors. Start, every check and stop all happen inside
this one process, because agent sandboxes kill what a tool call started.

Ports come from MAESTRO_PORT / MAESTRO_WEB_PORT in this process's environment (default 8001 and
3000). FASTEMBED_CACHE_PATH, when set, names a folder holding the scoring model: it is copied
into the install's home before start (so CI does not download 100 MB every run), and filled
from the install's own download afterwards when it was empty.

The newest-dependency guard: `uv tool install` resolves the newest FastAPI/Starlette/uvicorn, not
backend/requirements.lock (the CI lesson: Starlette 1.7 once changed the empty 404s), so the
checks below assert over HTTP what the security boundary relies on.
"""
from __future__ import annotations

import argparse
import contextlib
import http.client
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

if sys.version_info < (3, 12):
    raise SystemExit("smoke_uv_install.py needs Python 3.12 or newer (this is %d.%d)." % sys.version_info[:2])

WINDOWS = sys.platform == "win32"
EXPECTED_TOOLS = 94  # the full set; backend/tests/test_wheel_scripts.py pins it to the registry
LOG_TAIL = 40
FORGED_HOST = "evil.example"
FOREIGN_ORIGIN = "http://evil.example"
# The response headers frontend/next.config.ts sets on every route.
NEXT_SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
}
# Secrets and locations the smoke must not inherit: the score step must run with no LLM key.
_SCRUBBED = (
    "OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY",
    "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "OPENAI_BASE_URL", "FAST_MODEL", "SMART_MODEL", "CHAT_MODEL",
    "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST", "SYNC_REMOTE_URL", "SYNC_KEY_FILE",
    "SYNC_PUBLIC_HOST", "DATABASE_URL", "TEST_DATABASE_URL", "ALLOWED_HOSTS", "ALLOWED_WEB_ORIGINS",
    "FRONTEND_ALLOWED_HOSTS", "INTERNAL_API_URL", "BACKEND_URL", "MAESTRO_WEB_CMD", "MAESTRO_NODE",
    "MAESTRO_WEB_DIR", "VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME",
)

JD = {
    "company": "Smoke Test Co",
    "title": "Data Engineer",
    "role_category": "data_engineer",
    "country": "US",
    "work_authorization": "unstated",
    "skills": [
        {"skill_name": "Python", "skill_category": "language", "requirement_level": "required"},
        {"skill_name": "SQL", "skill_category": "language", "requirement_level": "required"},
        {"skill_name": "Apache Kafka", "skill_category": "data", "requirement_level": "preferred"},
        {"skill_name": "dbt", "skill_category": "data", "requirement_level": "preferred"},
    ],
    "responsibilities": ["Build reliable batch and streaming data pipelines."],
    "qualifications": ["5+ years building data platforms."],
}


class Failure(Exception):
    """A check failed; the message says what was expected and what was seen."""


# --- pure helpers (unit-tested in backend/tests/test_wheel_scripts.py) ---------------------

def is_connection_failure(exc: BaseException) -> bool:
    return isinstance(exc, (ConnectionError, TimeoutError, socket.timeout, socket.gaierror))


def describe(exc: BaseException) -> str:
    """One line for a failure. Only a refused/dropped/timed-out connection reads as 'no answer';
    anything else carries its exception type, so a bug is never reported as 'not running'."""
    kind = type(exc).__name__
    if isinstance(exc, Failure):
        return str(exc)
    if is_connection_failure(exc):
        return f"no answer from the server ({kind}: {exc})"
    return f"{kind}: {exc}"


def bare_404_problems(status: int, headers: dict[str, str], body: bytes) -> list[str]:
    """The empty 404 of a sync route while sync is off (backend/tests/sync/test_public_host.py
    `_BARE`): no body, `content-length: 0`, no `Vary`, no CORS headers, no server banner, no seal."""
    problems = []
    if status != 404:
        problems.append(f"status {status}, expected 404")
    if body:
        problems.append(f"body {body[:60]!r}, expected empty")
    if headers.get("content-length") != "0":
        problems.append(f"content-length {headers.get('content-length')!r}, expected '0'")
    extra = sorted(set(headers) - {"content-length", "date"})
    if extra:
        problems.append(f"unexpected headers {extra} (Vary or CORS added to the bare 404?)")
    return problems


def version_printed(text: str) -> str:
    """The version `maestro --version` printed: its last word (`maestro-career-studio 0.8.0`)."""
    words = text.split()
    return words[-1] if words else ""


def security_header_problems(headers: dict[str, str]) -> list[str]:
    return [f"{name}: {headers.get(name)!r}, expected {value!r}"
            for name, value in NEXT_SECURITY_HEADERS.items() if headers.get(name) != value]


def tail_lines(path: Path, count: int = LOG_TAIL) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-count:]
    except OSError:
        return []


def folder_mb(path: Path) -> float:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            with contextlib.suppress(OSError):
                total += os.lstat(os.path.join(root, name)).st_size
    return round(total / (1024 * 1024), 1)


# --- HTTP and processes ---------------------------------------------------------------------

@dataclass
class Reply:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> object:
        return json.loads(self.body)


def http_request(port: int, method: str, path: str, *, host: str | None = None,
                 headers: dict[str, str] | None = None, body: bytes | None = None,
                 timeout: float = 30.0) -> Reply:
    """Plain http.client to 127.0.0.1: no proxy, no redirects, and a Host header we control."""
    sent = dict(headers or {})
    if host is not None:
        sent["Host"] = host
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request(method, path, body=body, headers=sent)
        response = conn.getresponse()
        data = response.read()
        collected: dict[str, str] = {}
        for name, value in response.getheaders():
            key = name.lower()
            collected[key] = f"{collected[key]}, {value}" if key in collected else value
        return Reply(response.status, collected, data)
    finally:
        conn.close()


def port_listening(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def lan_address() -> str | None:
    """This machine's non-loopback address (no packet is sent), or None when it has none."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))
            address = probe.getsockname()[0]
    except OSError:
        return None
    return None if address.startswith("127.") or address == "0.0.0.0" else address


def _clear_readonly(func, target, _exc) -> None:
    with contextlib.suppress(OSError):
        os.chmod(target, stat.S_IWRITE)
        func(target)


class Smoke:
    def __init__(self, wheel: Path, expect_version: str | None, keep: bool) -> None:
        self.wheel, self.expect, self.keep = wheel, expect_version, keep
        self.root = Path(tempfile.mkdtemp(prefix="maestro-smoke-"))
        self.tool_dir, self.bin_dir, self.home = self.root / "tools", self.root / "bin", self.root / "home"
        self.shim = self.bin_dir / ("maestro.exe" if WINDOWS else "maestro")
        self.backend_port = int(os.environ.get("MAESTRO_PORT") or 8001)
        self.web_port = int(os.environ.get("MAESTRO_WEB_PORT") or 3000)
        self.model_seed = os.environ.get("FASTEMBED_CACHE_PATH", "").strip()
        self.env = self._build_env()
        self.timings: list[tuple[str, float]] = []
        self.facts: dict[str, object] = {}
        self.current = "setup"
        self.session = ""

    # --- plumbing ---

    def _build_env(self) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if k.upper() not in _SCRUBBED}
        env.update(
            UV_TOOL_DIR=str(self.tool_dir), UV_TOOL_BIN_DIR=str(self.bin_dir),
            UV_NO_PROGRESS="1", MAESTRO_HOME=str(self.home),
            MAESTRO_PORT=str(self.backend_port), MAESTRO_WEB_PORT=str(self.web_port),
            NEXT_TELEMETRY_DISABLED="1", PYTHONUTF8="1",
            NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost",
        )
        env.pop("FASTEMBED_CACHE_PATH", None)  # the install sets its own; the seed is copied in
        return env

    def say(self, message: str) -> None:
        print(message, flush=True)

    @contextlib.contextmanager
    def step(self, name: str) -> Iterator[None]:
        self.current = name
        started = time.monotonic()
        try:
            yield
        finally:
            elapsed = time.monotonic() - started
            self.timings.append((name, elapsed))
        self.say(f"ok    {name} ({elapsed:.1f}s)")

    def run(self, argv: list[str], *, timeout: float = 120.0, expect_code: int | None = 0,
            input_text: str | None = None) -> subprocess.CompletedProcess:
        done = subprocess.run(
            [str(a) for a in argv], env=self.env, capture_output=True, text=True,
            input=input_text if input_text is not None else None,
            stdin=None if input_text is not None else subprocess.DEVNULL,
            timeout=timeout, check=False, encoding="utf-8", errors="replace",
        )
        if expect_code is not None and done.returncode != expect_code:
            out = "\n".join((done.stdout + done.stderr).strip().splitlines()[-LOG_TAIL:])
            raise Failure(f"`{Path(str(argv[0])).name} {' '.join(map(str, argv[1:]))}` exited "
                          f"{done.returncode}, expected {expect_code}:\n{out}")
        return done

    def maestro(self, *args: str, **kw) -> subprocess.CompletedProcess:
        return self.run([self.shim, *args], **kw)

    def expect_ok(self, condition: bool, message: str) -> None:
        if not condition:
            raise Failure(message)

    def get(self, port: int, path: str, **kw) -> Reply:
        return http_request(port, "GET", path, **kw)

    def mcp(self, payload: dict, session: str | None = None, *, timeout: float = 120.0) -> Reply:
        headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        if session:
            headers["Mcp-Session-Id"] = session
        return http_request(self.backend_port, "POST", "/mcp", headers=headers,
                            body=json.dumps(payload).encode(), timeout=timeout)

    # --- the checks ---

    def install(self) -> None:
        uv = shutil.which("uv")
        self.expect_ok(bool(uv), "uv is not on PATH; install it from https://docs.astral.sh/uv/")
        self.run([uv, "tool", "install", "--python", "3.12", self.wheel], timeout=900)
        self.expect_ok(self.shim.is_file(), f"uv tool install did not create {self.shim}")
        self.facts["tool_dir_mb"] = folder_mb(self.tool_dir)

    def version_flag(self) -> None:
        text = self.maestro("--version").stdout.strip()
        self.facts["maestro --version"] = text
        if self.expect:
            self.expect_ok(version_printed(text) == self.expect, f"`maestro --version` printed {text!r}, "
                           f"expected the version {self.expect}")

    def seed_model(self) -> None:
        seed = Path(self.model_seed) if self.model_seed else None
        if seed and seed.is_dir() and any(seed.iterdir()):
            shutil.copytree(seed, self.home / "fastembed_cache", dirs_exist_ok=True)
            self.facts["scoring model"] = f"seeded from {seed}"
        else:
            self.facts["scoring model"] = "downloaded on first start"

    def start(self) -> None:
        self.seed_model()
        self.maestro("start", "--no-browser", timeout=900)

    def versions(self) -> None:
        health = self.get(self.backend_port, "/health")
        self.expect_ok(health.status == 200, f":{self.backend_port}/health returned {health.status}")
        backend = self.get(self.backend_port, "/api/version")
        web = self.get(self.web_port, "/api/version")
        self.expect_ok(backend.status == 200 and web.status == 200,
                       f"/api/version returned {backend.status} (backend) and {web.status} (web)")
        self.facts["backend version"] = backend.json().get("version")
        self.facts["web version"] = web.json().get("version")
        self.facts["schema revision"] = backend.json().get("schema_revision")
        if self.expect:
            self.expect_ok(self.facts["backend version"] == self.expect,
                           f"backend /api/version is {self.facts['backend version']!r}, expected {self.expect}")
            self.expect_ok(self.facts["web version"] == self.expect,
                           f"web /api/version is {self.facts['web version']!r}, expected {self.expect}")
        self.expect_ok(self.facts["web version"] == self.facts["backend version"],
                       "the web server and backend report different versions")

    def boundary(self) -> None:
        for port, label in ((self.backend_port, "backend"), (self.web_port, "web")):
            forged = self.get(port, "/health" if port == self.backend_port else "/", host=FORGED_HOST)
            self.expect_ok(forged.status == 400, f"{label}: forged Host got {forged.status}, expected 400")
        foreign = self.get(self.backend_port, "/api/version", headers={"Origin": FOREIGN_ORIGIN})
        self.expect_ok(foreign.status == 403, f"backend: foreign Origin got {foreign.status}, expected 403")
        allowed = self.get(self.backend_port, "/api/version",
                           headers={"Origin": f"http://localhost:{self.web_port}"})
        self.expect_ok(allowed.status == 200 and "access-control-allow-origin" in allowed.headers,
                       "backend: the web app's own Origin lost its CORS answer")
        for path in ("/", "/api/version"):
            problems = security_header_problems(self.get(self.web_port, path).headers)
            self.expect_ok(not problems, f"web {path}: security headers differ: {problems}")
        hello = self.get(self.backend_port, "/api/sync/hello")
        problems = bare_404_problems(hello.status, hello.headers, hello.body)
        self.expect_ok(not problems, f"/api/sync/hello (sync off) is not the bare 404: {problems}")

    def loopback_only(self) -> None:
        address = lan_address()
        if address is None:
            self.facts["loopback only"] = "skipped (no non-loopback address on this machine)"
            return
        reachable = [p for p in (self.backend_port, self.web_port) if port_listening(p, address)]
        self.expect_ok(not reachable, f"port(s) {reachable} answer on {address}, not only 127.0.0.1")
        self.facts["loopback only"] = f"ports refuse {address}"

    def mcp_over_http(self) -> None:
        init = self.mcp({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "smoke", "version": "1"}}})
        self.expect_ok(init.status == 200, f"POST /mcp initialize returned {init.status}: {init.body[:200]!r}")
        version = init.json()["result"]["serverInfo"]["version"]
        self.facts["mcp serverInfo.version"] = version
        if self.expect:
            self.expect_ok(version == self.expect, f"MCP serverInfo.version is {version!r}, expected {self.expect}")
        session = init.headers.get("mcp-session-id")
        self.expect_ok(bool(session), "POST /mcp initialize returned no Mcp-Session-Id")
        sent = self.mcp({"jsonrpc": "2.0", "method": "notifications/initialized"}, session)
        self.expect_ok(sent.status == 202, f"notifications/initialized returned {sent.status}")
        listed = self.mcp({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, session)
        count = len(listed.json()["result"]["tools"])
        self.facts["tools"] = count
        self.expect_ok(count == EXPECTED_TOOLS, f"tools/list has {count} tools, expected {EXPECTED_TOOLS}")
        self.session = session

    def call(self, name: str, arguments: dict, call_id: int) -> dict:
        reply = self.mcp({"jsonrpc": "2.0", "id": call_id, "method": "tools/call",
                          "params": {"name": name, "arguments": arguments}}, self.session)
        self.expect_ok(reply.status == 200, f"tools/call {name} returned HTTP {reply.status}")
        result = reply.json()["result"]
        self.expect_ok(not result.get("isError"), f"tools/call {name} failed: {result.get('content')}")
        blocks = result.get("content") or []
        self.expect_ok(bool(blocks) and blocks[0].get("type") == "text",
                       f"tools/call {name} returned no text content block (Claude Desktop reads content)")
        return json.loads(blocks[0]["text"])

    def demo_base(self) -> None:
        # start already waited for health; startup renders synchronously, so polling cannot heal it.
        reply = self.get(self.backend_port, "/api/base-resumes")
        self.expect_ok(reply.status == 200, f"GET /api/base-resumes returned {reply.status}")
        demo = next((row for row in reply.json() if row["slug"] == "example"), None)
        self.expect_ok(demo is not None, "startup finished without the demo base resume")
        self.expect_ok(not demo.get("render_error"), f"demo render failed: {demo.get('render_error')}")
        self.expect_ok(bool(demo.get("pdf_rendered_at")), "startup finished without rendering the demo PDF")
        pdf = self.get(self.backend_port, "/api/base-resumes/example/pdf")
        self.expect_ok(pdf.status == 200 and pdf.body.startswith(b"%PDF"),
                       f"demo PDF download returned HTTP {pdf.status} or invalid PDF bytes")
        self.facts["demo base"] = ["example"]

    def score_without_a_key(self) -> None:
        # The path agents use: store_extracted_jd (the caller extracted the JD, so no LLM call)
        # then score_ats (deterministic, local embedding model). The Companion's own capture
        # extracts with an LLM, which this smoke deliberately has no key for.
        job = self.call("store_extracted_jd", {
            "extracted_json": JD, "raw_text": "Smoke test posting for a data engineer.",
            "source_url": "https://smoke.invalid/jobs/1", "source": "user"}, 3)
        scored = self.call("score_ats", {"job_id": job["id"], "include_other_countries": True}, 4)
        scores = scored.get("scores") or []
        self.expect_ok(bool(scores), f"score_ats returned no scores: {str(scored)[:200]}")
        composite = scores[0].get("composite")
        self.expect_ok(isinstance(composite, (int, float)) and 0 <= composite <= 100,
                       f"score_ats composite {composite!r} is not 0-100")
        self.facts["score"] = f"{composite} against {scores[0].get('target_id')} (no LLM key)"

    def bridge(self) -> None:
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "smoke-bridge", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "list_templates", "arguments": {}}},
        ]
        done = self.maestro("mcp", input_text="\n".join(json.dumps(x) for x in lines) + "\n", timeout=180)
        replies = {}
        for line in done.stdout.splitlines():
            if line.strip():
                message = json.loads(line)
                replies[message.get("id")] = message
        self.expect_ok({1, 2, 3} <= set(replies), f"`maestro mcp` answered ids {sorted(map(str, replies))}, "
                       f"stderr: {done.stderr.strip()[-300:]}")
        version = replies[1]["result"]["serverInfo"]["version"]
        if self.expect:
            self.expect_ok(version == self.expect, f"`maestro mcp` serverInfo.version {version!r}, expected {self.expect}")
        count = len(replies[2]["result"]["tools"])
        self.expect_ok(count == EXPECTED_TOOLS, f"`maestro mcp` tools/list has {count}, expected {EXPECTED_TOOLS}")
        result = replies[3]["result"]
        blocks = result.get("content") or []
        self.expect_ok(not result.get("isError") and blocks and blocks[0].get("type") == "text",
                       f"`maestro mcp` list_templates gave no text content block: {str(result)[:300]}")

    def backup(self) -> None:
        path = Path(self.maestro("backup").stdout.strip().splitlines()[-1])
        self.expect_ok(path.is_file(), f"`maestro backup` named {path}, which is not a file")
        magic = path.read_bytes()[:2]
        self.expect_ok(magic == b"\x1f\x8b", f"backup {path.name} starts with {magic!r}, not gzip magic")
        self.facts["backup"] = f"{path.name} ({path.stat().st_size // 1024} KB)"

    def check(self) -> None:
        report = json.loads(self.maestro("check").stdout)
        self.expect_ok(report.get("db_revision") == report.get("code_head"),
                       f"db_revision {report.get('db_revision')!r} != code_head {report.get('code_head')!r}")
        self.expect_ok(bool(report.get("web")), "`maestro check` says the web bundle is not usable")
        self.facts["node"] = report.get("node")
        self.facts["db revision"] = report.get("db_revision")

    def status(self) -> None:
        report = json.loads(self.maestro("status", "--json", "--offline").stdout)
        self.expect_ok(report.get("running") is True, f"`maestro status` says not running: {report}")
        self.facts["rss backend MB"] = report["backend"].get("rss_mb")
        self.facts["rss web MB"] = report["web"].get("rss_mb")

    def stop_and_verify(self) -> None:
        self.maestro("stop", timeout=90)
        for port in (self.backend_port, self.web_port):
            self.expect_ok(not port_listening(port), f"port {port} still answers after `maestro stop`")
        done = self.maestro("status", "--json", "--offline", expect_code=None)
        self.expect_ok(done.returncode == 3, f"`maestro status` exited {done.returncode} after stop, expected 3")

    def copy_model_back(self) -> None:
        seed, cache = Path(self.model_seed) if self.model_seed else None, self.home / "fastembed_cache"
        if seed and cache.is_dir() and any(cache.iterdir()) and not (seed.is_dir() and any(seed.iterdir())):
            with contextlib.suppress(OSError):
                shutil.copytree(cache, seed, dirs_exist_ok=True)

    # --- the run ---

    def stop_quietly(self) -> None:
        if self.shim.is_file():
            with contextlib.suppress(Exception):
                self.maestro("stop", timeout=90, expect_code=None)
        for name in ("supervisor", "web", "backend"):  # last resort, supervisor first: it respawns if `stop` could not
            record = self.home / "run" / f"{name}.json"
            try:
                pid = int(json.loads(record.read_text(encoding="utf-8"))["pid"])
            except (OSError, ValueError, KeyError):
                continue
            if any(port_listening(p) for p in (self.backend_port, self.web_port)):
                with contextlib.suppress(OSError):
                    if WINDOWS:
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                                       capture_output=True, check=False)
                    else:
                        os.kill(pid, 9)

    def dump_logs(self) -> None:
        logs = self.home / "logs"
        for name in ("supervisor", "backend", "web", "prefetch"):
            lines = tail_lines(logs / f"{name}.log")
            if lines:
                print(f"--- last {len(lines)} lines of logs/{name}.log ---", file=sys.stderr)
                print("\n".join(lines), file=sys.stderr)

    def summary(self, total: float) -> None:
        print("\n=== smoke summary ===")
        print(f"wheel            {self.wheel.name} ({self.wheel.stat().st_size / 1_000_000:.1f} MB)")
        for key, value in self.facts.items():
            print(f"{key:<16} {value}")
        print(f"ports            backend {self.backend_port}, web {self.web_port}")
        for name, seconds in self.timings:
            print(f"  {seconds:7.1f}s  {name}")
        print(f"total            {total:.1f}s")

    def main(self) -> int:
        started = time.monotonic()
        steps = (
            ("uv tool install", self.install),
            ("maestro --version", self.version_flag),
            ("maestro start", self.start),
            ("versions agree (backend, web proxy, expected)", self.versions),
            ("host, origin, headers and bare 404 hold", self.boundary),
            ("listeners are loopback-only", self.loopback_only),
            ("POST /mcp initialize and tools/list", self.mcp_over_http),
            ("demo base resume rendered and downloadable", self.demo_base),
            ("job stored and scored with no LLM key", self.score_without_a_key),
            ("maestro mcp bridge", self.bridge),
            ("maestro backup", self.backup),
            ("maestro check", self.check),
            ("maestro status --json", self.status),
            ("maestro stop, ports free, status exits 3", self.stop_and_verify),
        )
        code = 0
        try:
            for name, func in steps:
                with self.step(name):
                    func()
            self.copy_model_back()
        except BaseException as exc:  # noqa: BLE001  (KeyboardInterrupt too: cleanup must run)
            code = 1
            print(f"\nFAIL  {self.current}: {describe(exc)}", file=sys.stderr)
            self.dump_logs()
        finally:
            self.stop_quietly()
            if self.keep:
                print(f"kept {self.root}")
            else:
                shutil.rmtree(self.root, onexc=_clear_readonly)
                if self.root.exists():
                    print(f"could not delete {self.root}; remove it by hand", file=sys.stderr)
        if code == 0:
            self.summary(time.monotonic() - started)
        return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--expect-version")
    parser.add_argument("--keep", action="store_true", help="keep the temp tool dir and home")
    args = parser.parse_args(argv)
    if not args.wheel.is_file():
        print(f"smoke: {args.wheel} is not a file", file=sys.stderr)
        return 1
    return Smoke(args.wheel.resolve(), args.expect_version, args.keep).main()


if __name__ == "__main__":
    raise SystemExit(main())
