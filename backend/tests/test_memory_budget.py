"""The backend's resident memory after a typical cycle stays inside a measured budget.

Runs scripts.memory_profile's cycle against a throwaway backend, with the small-machine
settings the native install uses, and checks the last /health/memory reading. Linux only
(rss is not comparable elsewhere). CI skips it: it downloads the real embedding model, a
third-party dependency CI's backend job avoids (like tests/ats/test_golden.py), so the
reviewer runs it on Linux and the pilot confirms it. Set FASTEMBED_CACHE_PATH to reuse a
model cache between runs.
"""

import importlib
import os
import socket
import sys

import pytest


# Measured 2026-10-06 on Linux arm64 (python:3.12-slim, MALLOC_ARENA_MAX=2,
# EMBEDDINGS_OUT_OF_PROCESS=1, --cycles 5): end of cycle 5 = 172.8 MB. Budget = that + 15%
# headroom. The same run with the helper off ended at 426.9 MB.
BUDGET_MB = 200
CYCLES = 3


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.mark.slow
@pytest.mark.skipif(bool(os.environ.get("MAESTRO_SKIP_SLOW")), reason="MAESTRO_SKIP_SLOW is set")
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="rss budget is measured on Linux")
def test_backend_rss_after_a_typical_cycle_stays_inside_the_budget(monkeypatch):
    monkeypatch.setenv("MALLOC_ARENA_MAX", "2")
    monkeypatch.setenv("EMBEDDINGS_OUT_OF_PROCESS", "1")
    profiler = importlib.import_module("scripts.memory_profile")
    rows = profiler.run_profile(port=free_port(), cycles=CYCLES)
    last = rows[-1]["rss_mb"]
    assert last <= BUDGET_MB, f"rss after cycle {CYCLES} was {last} MB, budget {BUDGET_MB} MB"
