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

**What we know (measured 2026-10-06, Linux arm64, python:3.12-slim, `--cycles 5`):**

| run | startup | after 1st ATS score | end of cycle 5 | peak |
|---|---|---|---|---|
| default allocator | 144 MB | 412 | 435 | 435 |
| `MALLOC_ARENA_MAX=2` | 144 | 393 | 390 | 405 |
| `MALLOC_ARENA_MAX=2` + a malloc_trim middleware | 144 | 406 | 356 | 406 |

One MCP server process: 76 MB. The growth is the ATS semantic layer's embedding model
(fastembed ONNX, `BAAI/bge-small-en-v1.5`, ~260 MB), loaded on the first score by
`services/ats/embeddings._model` (an `lru_cache`) and held for the process lifetime. The trim
middleware saved 8.6 % (under this plan's 10 % bar), so it is dropped. Typst compiles already run
in a spawned process. **Owner decision (2026-10-06): on small machines, ATS scoring embeds in a
short-lived helper process,** so the model's memory is freed after each scoring call, and scores
stay identical everywhere.

**Architecture:**
- `GET /health/memory` reports the process's current and peak resident memory.
- `backend/scripts/memory_profile.py` starts a throwaway backend and runs a typical, AI-free cycle
  over HTTP, sampling memory after each step: the measuring tool and the budget test's engine.
- `EMBEDDINGS_OUT_OF_PROCESS` (setting, default off): when on, `embed_texts` computes its cache
  misses in a spawned helper process that loads the model, embeds the batch, returns the vectors
  and exits (the `services/typst_compiler.py` pattern). The vector cache stays in the backend
  (small). Off by default, so the Docker laptop keeps today's speed.
- `backend/scripts/native/` installs and runs the backend from a home-directory venv with plain
  `setup`, `start`, `stop`, `health` commands any supervisor can call; `start` sets
  `MALLOC_ARENA_MAX=2`, one worker, and `EMBEDDINGS_OUT_OF_PROCESS=1`.
- No sync, no web app on the pilot machine. The MCP server is started on demand by the agent.

**Tech stack:** FastAPI, Python 3.12 stdlib (`resource`, `ctypes`, `subprocess`), bash.

**Freedom:** endpoint path `/health/memory`, its keys (`rss_mb`, `peak_mb`, `platform`), script
paths and command names, the env vars `MAESTRO_HOME` and `EMBEDDINGS_OUT_OF_PROCESS` are **fixed**. Helper decomposition is yours
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

client = TestClient(app)


def test_health_memory_reports_current_and_peak_megabytes():
    body = client.get("/health/memory").json()
    assert set(body) == {"rss_mb", "peak_mb", "platform"}
    assert body["rss_mb"] > 0 and body["peak_mb"] > 0  # ru_maxrss can lag VmRSS on Linux


def test_health_stays_tiny_for_container_healthchecks():
    assert client.get("/health").json() == {"status": "ok"}


```

**Implementation** (`services/memory.py`):

```python
"""Resident memory of this process, for /health/memory (docs/plans/2026-10-06-slim-pilot.md)."""

import resource
import sys
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


def readout() -> dict:
    return {"rss_mb": rss_mb(), "peak_mb": peak_mb(), "platform": sys.platform}
```

`main.py`: `@app.get("/health/memory")` returning `memory.readout()`; `/health` unchanged.

**Commit:** `feat(health): report resident memory at /health/memory`

---

### Task 2: `scripts/memory_profile.py` (the measuring tool)

**Files:** Create `backend/scripts/memory_profile.py` (stdlib + `httpx`), run as
`python -m scripts.memory_profile` from `backend/`; add `scripts.memory_profile` to
`backend/.slopconfig.json` `entry_points`; register the `slow` marker in
`backend/pyproject.toml` `[tool.pytest.ini_options].markers` and the root `pytest.ini`
(`slow: starts a real backend or installs a venv; skipped when MAESTRO_SKIP_SLOW is set`);
Test `backend/tests/test_memory_profile.py`.

**Behavior:** `python -m scripts.memory_profile [--port 8711] [--json out.json] [--cycles 3]`:
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

The dry run found these AI-free endpoints: `POST /api/jobs/ingest` (MCP `store_extracted_jd`),
`POST /api/ats-scores` (`score_ats`), `POST /api/applications/from-base`,
`POST /api/applications/{id}/render`, `POST`/`GET /api/jobs/{id}/filled-answers`,
`GET /api/proposals?limit=500`, `GET /api/automations`. The ATS steps load the embedding model
(downloaded once into `FASTEMBED_CACHE_PATH`). Write the startup poll as a helper returning a
bool (a bare `except ...: pass` trips the error-masking ratchet). Expect ±3 % run-to-run noise.

**Tests:** the module imports with no side effects; `build_env(home)` returns the expected keys;
`parse_args` defaults; and one end-to-end run marked `@pytest.mark.slow` that starts the server on a
free port with `--cycles 1` and asserts every step produced a reading (skipped when
`MAESTRO_SKIP_SLOW` is set).

**Then measure (reviewer, Linux):** inside the backend image, `--cycles 5`, with
`MALLOC_ARENA_MAX=2`, record the numbers in the commit message (Task 3 re-measures with the
helper process).

**Commit:** `feat(scripts): measure the backend's memory across a typical cycle`

---

### Task 3: ATS embeddings in a short-lived helper process

**Files:** Modify `backend/app/config.py` (`embeddings_out_of_process: bool = False`, env
`EMBEDDINGS_OUT_OF_PROCESS`), `backend/app/services/ats/embeddings.py`; Test
`backend/tests/ats/test_embeddings_out_of_process.py` (use the existing `embeddings_internals`
fixture conventions in `tests/conftest.py`: the suite patches `embed_texts` with
`fake_embed_texts`, so tests of this path stub the model loader, never download it).

When the setting is on, `embed_texts` sends its cache misses (one batch) to a `spawn`
multiprocessing child that imports fastembed, loads the pinned model, embeds the batch and returns
the vectors through a pipe, then exits; a join timeout (60 s) kills a stuck child and raises a
clear error. The parent keeps the vector cache exactly as today. When off, behavior is unchanged
(in-process `_model`). The child module stays import-light (stdlib + the deferred fastembed
import), like `typst_compiler`.

**Tests:** with the setting on and the child's loader stubbed to a deterministic fake, vectors equal
the in-process path's for the same stub; cache hits never spawn; a child that dies raises the
clear error; with the setting off, no child is spawned. A `slow`, Linux-only test runs Task 2's
cycle with the setting on and asserts the backend's last reading is below the in-process
reading by at least 150 MB (it downloads the real model; skipped under `MAESTRO_SKIP_SLOW`).

**Measure (reviewer, Linux):** Task 2's script with `MALLOC_ARENA_MAX=2` and the setting on;
record startup, after first score, end of cycle 5, peak, and the per-score time cost.

**Commit:** `feat(ats): embed in a short-lived helper process when EMBEDDINGS_OUT_OF_PROCESS is on`

---

### Task 4: Native install and run scripts

**Files:** Create `backend/scripts/native/common.sh` (sourced: env export, pidfile probe, a
python-based GET so curl is not required), `setup.sh`, `start.sh`, `stop.sh`, `health.sh`,
`maestro.env.example`; Test `backend/tests/test_native_scripts.py`.

- `setup.sh` (idempotent): needs `MAESTRO_HOME` (default `~/maestro`); creates the directory
  layout of Task 2; creates `$MAESTRO_HOME/venv` with the `python3.12` found on PATH (or
  `$PYTHON`); `pip install -e "$REPO/backend[mcp]"` (editable: startup resolves `alembic.ini`
  beside the `app` package; `[mcp]` so `python -m mcp_server.server` imports); copies `maestro.env.example` to
  `$MAESTRO_HOME/maestro.env` if absent (mode 0600); runs `alembic upgrade head`.
- `start.sh`: refuses if already running (pidfile `$MAESTRO_HOME/backend.pid` with a live pid);
  sources `maestro.env`; exports `DATA_DIR` etc. into `$MAESTRO_HOME`, `MALLOC_ARENA_MAX=2`,
  `ALLOWED_HOSTS=localhost,127.0.0.1`, `EMBEDDINGS_OUT_OF_PROCESS=1`,
  `FASTEMBED_CACHE_PATH=$MAESTRO_HOME/fastembed_cache` (the default `/tmp` is often RAM-backed on a
  small VM); starts `uvicorn app.main:app --host 127.0.0.1 --port
  ${MAESTRO_PORT:-8001} --workers 1` in the background with logs to `$MAESTRO_HOME/logs/backend.log`;
  writes the pidfile; waits up to 30 s for `/health`.
- `stop.sh`: TERM, wait, KILL after 10 s, remove the pidfile; succeeds when not running.
- `health.sh`: prints `/health/memory`; exit 0 when healthy, 1 when not running or unhealthy.
  A supervisor (systemd, a watchdog cron, launchd) restarts with `health.sh || start.sh`.
- `maestro.env.example`: the AI key lines commented out, a note that secrets come from the
  machine's own secret store, never a chat. `maestro.env` is created under `umask 077` and
  `chmod 600`; `MAESTRO_HOME` is 700; no script uses `set -x` (a test pins it).
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
three times with `MALLOC_ARENA_MAX=2` and `EMBEDDINGS_OUT_OF_PROCESS=1`, and assert the last
reading is at most `BUDGET_MB`. **Set `BUDGET_MB` from the reviewer's Task 2/3 measurements plus 15 % headroom;
the implementer leaves it as a named constant with the measurement in a comment, and stops to ask
if no measurement is available.** The real model download is a third-party dependency CI already
avoids (`tests/ats/test_golden.py`), so CI sets `MAESTRO_SKIP_SLOW=1` and the budget is pinned by
the reviewer's Linux run and the pilot, not by CI.

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

Full backend suite (with and without `frontend/node_modules`), ruff, both slop ratchets (a
`complexity_hotspots` count bump is re-baselined with a reason, per SYSTEM.md §9), the SYSTEM.md
gate, and on Linux (Docker image) the Task 2 profile and Task 5 budget test. Report the numbers,
and whether backend + one MCP server fits beside a browser in ~640 MB.
