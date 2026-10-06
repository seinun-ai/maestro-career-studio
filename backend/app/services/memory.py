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
