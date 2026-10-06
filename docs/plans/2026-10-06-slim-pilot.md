# Slim Pilot Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or
> superpowers:subagent-driven-development in this session) to implement this plan task by task.

**Goal:** Maestro's backend runs natively (no Docker) on a small, memory-tight Linux machine,
reports its own memory, and stays inside a measured budget, so the owner's always-on agent machine
can run it single-machine as a pilot before any sync is built.

**Owner's goal (2026-10-06):** "can we first make a slimmer copy version onto [the agent's VM] and
if it can run it freely over there, and then plan about building sync?" The agent VM has about
640 MB available, no swap, and its own browser on top during runs. Phase 4b (split-ownership sync,
`docs/plans/2026-10-06-split-ownership-sync-design.md`) waits on this pilot's numbers.

**What we know (measured 2026-10-06):** the backend uses ~155 MB right after startup on macOS
(importing every service adds nothing); the live Docker backend sits at ~400 MB after a day of
use; one MCP server process is ~56–64 MB. Typst PDF compiles already run in a short-lived spawned
process (`services/typst_compiler.py`). The app does not import litellm (it calls the OpenAI
client and Gemini over HTTP). So the growth is runtime memory the process keeps after peaks;
glibc's per-thread arenas and unreturned freed memory are the usual cause on Linux.

**Architecture:**
- `GET /health/memory` reports the process's current and peak resident memory.
- `scripts/memory_profile.py` starts a throwaway backend and runs a typical, AI-free cycle over
  HTTP, sampling memory after each step. It is both the measuring tool and the budget test's
  engine.
- `app/services/memory.py` returns freed memory to the OS on Linux (`malloc_trim(0)` via ctypes,
  a no-op elsewhere) after requests that grew memory; the native start script sets
  `MALLOC_ARENA_MAX=2` and runs one worker.
- `scripts/native/` installs and runs the backend from a home-directory venv with plain
  `setup`, `start`, `stop`, `health` commands any supervisor can call.
- No sync, no web app on the pilot machine. The MCP server is started on demand by the agent.

**Tech stack:** FastAPI, Python 3.12 stdlib (`resource`, `ctypes`, `subprocess`), bash.

**Freedom:** endpoint path `/health/memory`, its keys (`rss_mb`, `peak_mb`, `platform`), script
paths and command names, the env var `MAESTRO_HOME` are **fixed**. Helper decomposition is yours
(cc < 10, ≤ 50 lines, ≤ 5 params). **Stop and report** before changing tailoring, filling, the
Companion, or any behavior beyond memory handling. The repo is PUBLIC: no real company names; the
agent app is described generically ("an always-on agent machine").

**Environment:** as in `docs/plans/2026-10-05-full-automation.md` (Python
`/opt/anaconda3/bin/python3` from `backend/`; xdist suite; slop ratchets; SYSTEM.md gate at
1000/1000, so Task 6 grooms before adding). Linux-only measurements run inside the backend Docker
image (`docker build -t maestro-pilot ./backend` then `docker run --rm ...`); a sandboxed
implementer without Docker writes the code and the reviewer measures.

---

### Task 1: `GET /health/memory`

**Files:** Create `backend/app/services/memory.py`; Modify `backend/app/main.py` (next to
`/health`); Test `backend/tests/test_health_memory.py`.

**Tests first:**

```python
from fastapi.testclient import TestClient

from app.main import app
from app.services import memory

client = TestClient(app)


def test_health_memory_reports_current_and_peak_megabytes():
    body = client.get("/health/memory").json()
    assert set(body) == {"rss_mb", "peak_mb", "platform"}
    assert 0 < body["rss_mb"] <= body["peak_mb"] + 1


def test_health_stays_tiny_for_container_healthchecks():
    assert client.get("/health").json() == {"status": "ok"}


def test_trim_is_safe_everywhere():
    memory.trim()  # a no-op off glibc, never raises
```

**Implementation** (`services/memory.py`):

```python
"""Resident memory: report it, and on Linux hand freed memory back to the OS.

glibc keeps freed heap in per-thread arenas instead of returning it, so a Python service's
resident memory ratchets up to its peaks; malloc_trim(0) releases what is free. Elsewhere trim
is a no-op. See docs/plans/2026-10-06-slim-pilot.md.
"""

import ctypes
import ctypes.util
import gc
import resource
import sys
from functools import lru_cache
from pathlib import Path


def rss_mb() -> float:
    status = Path("/proc/self/status")
    if status.exists():
        for line in status.read_text().splitlines():
            if line.startswith("VmRSS:"):
                return round(int(line.split()[1]) / 1024, 1)
    return peak_mb()  # macOS has no /proc; the peak is the best cheap stand-in


def peak_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024, 1)


@lru_cache(maxsize=1)
def _malloc_trim():
    name = ctypes.util.find_library("c")
    if not name or not sys.platform.startswith("linux"):
        return None
    return getattr(ctypes.CDLL(name), "malloc_trim", None)


def trim() -> None:
    gc.collect()
    fn = _malloc_trim()
    if fn is not None:
        fn(0)


def readout() -> dict:
    return {"rss_mb": rss_mb(), "peak_mb": peak_mb(), "platform": sys.platform}
```

`main.py`: `@app.get("/health/memory")` returning `memory.readout()`; `/health` unchanged.

**Commit:** `feat(health): report resident memory at /health/memory`

---

### Task 2: `scripts/memory_profile.py` (the measuring tool)

**Files:** Create `scripts/memory_profile.py` (stdlib + `httpx`, which the backend already
depends on); Test `backend/tests/test_memory_profile.py`.

**Behavior:** `python scripts/memory_profile.py [--port 8711] [--json out.json] [--cycles 3]`:
1. Makes a temp `MAESTRO_HOME` with `data/ applications/ settings/ base_resumes/ kb_documents/
   logs/ exports/`, copies `base_resumes/example.json` in, runs `alembic upgrade head` against it.
2. Starts `uvicorn app.main:app --workers 1 --port <port>` from `backend/` with `DATA_DIR` etc.
   pointing into the temp home, inheriting `MALLOC_ARENA_MAX` from the caller.
3. Runs an AI-free cycle `--cycles` times over HTTP, reading `/health/memory` after each step:
   save a job from a fixed job-description text (the same route MCP `store_extracted_jd` uses);
   score it against the example base (`score_ats`'s route); create its application from the base
   and render the PDF; post a filled-answers receipt of 40 fields; read the receipt; list
   proposals with `limit=500`; read `/api/automations`.
4. Prints a table (step, rss_mb, peak_mb) and writes `--json`; stops the server and removes the
   temp home (also on Ctrl-C and on failure).

Use the real endpoints (read the routers; name each in the script). No AI key is needed: if a step
needs one, pick the AI-free route or leave the step out and say so in the docstring.

**Tests:** the module imports with no side effects; `build_env(home)` returns the expected keys;
`parse_args` defaults; and one end-to-end run marked `@pytest.mark.slow` that starts the server on a
free port with `--cycles 1` and asserts every step produced a reading (skipped when
`MAESTRO_SKIP_SLOW` is set).

**Then measure (reviewer, Linux):** run it inside the backend image with and without
`MALLOC_ARENA_MAX=2`, `--cycles 5`, and record the numbers in the commit message.

**Commit:** `feat(scripts): measure the backend's memory across a typical cycle`

---

### Task 3: Hand memory back after heavy requests

**Files:** Modify `backend/app/main.py` (a small middleware), `backend/app/services/memory.py`;
Test `backend/tests/test_health_memory.py`.

A middleware reads `rss_mb()` before and after each request; when a request grew resident memory
by more than `TRIM_THRESHOLD_MB = 16`, it calls `memory.trim()` after the response is sent
(`BackgroundTask` or `asyncio.to_thread`, never blocking the response). The threshold and the
choice to trim only on growth keep the common request free of a `gc.collect()`.

**Tests:** with `memory.rss_mb` monkeypatched to grow by 20 MB across a request, `trim` is called
once; with 4 MB it is not; a raising `trim` never fails the request.

**Measure (reviewer, Linux):** Task 2's script with and without the middleware; the trimmed run
must end the cycle lower. If the gain is under 10 %, report it; the owner decides whether to keep
the middleware.

**Commit:** `feat(memory): return freed memory to the OS after requests that grew it (Linux)`

---

### Task 4: Native install and run scripts

**Files:** Create `scripts/native/setup.sh`, `start.sh`, `stop.sh`, `health.sh`,
`scripts/native/maestro.env.example`; Test `backend/tests/test_native_scripts.py`.

- `setup.sh` (idempotent): needs `MAESTRO_HOME` (default `~/maestro`); creates the directory
  layout of Task 2; creates `$MAESTRO_HOME/venv` with the `python3.12` found on PATH (or
  `$PYTHON`); `pip install` the repo's `backend/`; copies `maestro.env.example` to
  `$MAESTRO_HOME/maestro.env` if absent (mode 0600); runs `alembic upgrade head`.
- `start.sh`: refuses if already running (pidfile `$MAESTRO_HOME/backend.pid` with a live pid);
  sources `maestro.env`; exports `DATA_DIR` etc. into `$MAESTRO_HOME`, `MALLOC_ARENA_MAX=2`,
  `ALLOWED_HOSTS=localhost,127.0.0.1`; starts `uvicorn app.main:app --host 127.0.0.1 --port
  ${MAESTRO_PORT:-8001} --workers 1` in the background with logs to `$MAESTRO_HOME/logs/backend.log`;
  writes the pidfile; waits up to 30 s for `/health`.
- `stop.sh`: TERM, wait, KILL after 10 s, remove the pidfile; succeeds when not running.
- `health.sh`: prints `/health/memory`; exit 0 when healthy, 1 when not running or unhealthy.
  A supervisor (systemd, a watchdog cron, launchd) restarts with `health.sh || start.sh`.
- `maestro.env.example`: the AI key lines commented out, a note that secrets come from the
  machine's own secret store, never a chat.
- The MCP server is not started here: the agent starts `python -m mcp_server.server` on demand
  with `BACKEND_URL=http://127.0.0.1:8001` (documented in Task 6).

**Tests:** `bash -n` on each script; `shellcheck` when installed (skip otherwise); and, marked
`slow`, a full run in a temp `MAESTRO_HOME`: setup → start → health exits 0 and prints the
readout → start again refuses → stop → health exits 1. Use the current interpreter as `PYTHON`.

**Commit:** `feat(native): install and run the backend without Docker`

---

### Task 5: The memory budget test

**Files:** Test `backend/tests/test_memory_budget.py`.

Linux only (`skipif not sys.platform.startswith("linux")`) and marked `slow`: run Task 2's cycle
three times with `MALLOC_ARENA_MAX=2` and Task 3's middleware, and assert the last reading is at
most `BUDGET_MB`. **Set `BUDGET_MB` from the reviewer's Task 2/3 measurements plus 15 % headroom;
the implementer leaves it as a named constant with the measurement in a comment, and stops to ask
if no measurement is available.** CI's backend job runs on Linux, so this pins it there.

**Commit:** `test(memory): pin the backend's resident memory after a typical cycle`

---

### Task 6: The pilot guide and docs

**Files:** Create `docs/native-install.md`; Modify `SYSTEM.md` (§9: native run, `/health/memory`;
groom first, it is at 1000/1000), `CHANGELOG.md`.

`docs/native-install.md`: who it is for (a small always-on Linux machine, single-machine, no
sync yet), the four commands, supervisor examples (systemd unit, a watchdog cron line, launchd),
the MCP server on demand over stdio, reading `/health/memory`, the measured footprint and budget,
and a "pilot report" checklist for the agent machine: run one hunt and one attended apply with
its browser open, and report `/health/memory` before, during and after, plus the machine's free
memory. A worked example describes an always-on agent app's VM generically (watchdog cron, vault
for secrets).

**Commit:** `docs: run Maestro natively on a small always-on machine (pilot)`

---

### Task 7: Verification

Full backend suite (with and without `frontend/node_modules`), both slop ratchets, the SYSTEM.md
gate, and on Linux (Docker image) the Task 2 profile and Task 5 budget test. Report the numbers.
