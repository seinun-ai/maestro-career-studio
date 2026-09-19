"""Which PDF engines can THIS process run — the one place that looks for one.

A GUI-launched process (the desktop shell, a Claude Desktop child) has no shell
`PATH`, so MacTeX's `/Library/TeX/texbin` is invisible to it. The probe searches
the known TeX homes after `PATH`, and `pdf_render` runs the resolved absolute
path. `MAESTRO_CS_PDFLATEX` overrides the search and fails closed when wrong.

Cheap by design: `which` re-runs on every call (installing TeX while the app
runs is noticed on the next probe), the `--version` subprocess runs once per
resolved path per process.
"""
from __future__ import annotations

import glob
import importlib.metadata
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

# Where TeX installs put pdflatex when it is not on PATH. Globs sort newest
# TeX Live year first.
_TEX_HOMES_POSIX = (
    "/Library/TeX/texbin",
    "/usr/local/texlive/*/bin/*",
    "~/.TinyTeX/bin/*",
    "/opt/homebrew/bin",
    "/usr/local/bin",
)
_TEX_HOMES_WINDOWS = (
    "%LOCALAPPDATA%\\Programs\\MiKTeX\\miktex\\bin\\x64",
    "C:\\texlive\\*\\bin\\windows",
)


@dataclass(frozen=True)
class EngineStatus:
    name: str
    available: bool
    version: str | None = None
    path: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class EnginesStatus:
    pdflatex: EngineStatus
    typst: EngineStatus


def _candidate_dirs() -> list[str]:
    homes = _TEX_HOMES_WINDOWS if sys.platform == "win32" else _TEX_HOMES_POSIX
    dirs: list[str] = []
    for pattern in homes:
        expanded = os.path.expandvars(os.path.expanduser(pattern))
        dirs.extend(sorted(glob.glob(expanded), reverse=True))
    return dirs


def find_pdflatex() -> tuple[str | None, str | None]:
    """(path, reason). An explicit override is not a hint: wrong = unavailable."""
    override = settings.maestro_cs_pdflatex
    if override is not None:
        candidate = Path(override)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate), None
        return None, (
            f"MAESTRO_CS_PDFLATEX points at {override}, which is not an "
            "executable file; correct it or unset it to search the usual locations"
        )
    # Drop empty entries before joining: an empty entry means "the current
    # directory" to shutil.which, and an absent PATH — the GUI-launched process
    # this module exists for — would otherwise put the process's cwd ahead of
    # the TeX homes and resolve to a bare, relative "pdflatex".
    entries = [e for e in [os.environ.get("PATH", ""), *_candidate_dirs()] if e]
    found = shutil.which("pdflatex", path=os.pathsep.join(entries))
    if found is None:
        return None, "pdflatex not found on PATH or in the usual TeX locations"
    return found, None


def pdflatex_command() -> str:
    """argv[0] for a pdflatex run: the override verbatim (wrong ones fail at
    spawn, by design), else the resolved path, else the bare name."""
    override = settings.maestro_cs_pdflatex
    if override is not None:
        return str(override)
    found, _ = find_pdflatex()
    return found or "pdflatex"


# path -> (version, reason). One --version per path per process.
_VERSION_CACHE: dict[str, tuple[str | None, str | None]] = {}


def reset_cache() -> None:
    _VERSION_CACHE.clear()


def _pdflatex_version(path: str) -> tuple[str | None, str | None]:
    if path in _VERSION_CACHE:
        return _VERSION_CACHE[path]
    try:
        result = subprocess.run(
            [path, "--version"], capture_output=True, text=True, timeout=15, check=False
        )
        first = (result.stdout or "").strip().splitlines()
        outcome = (first[0], None) if result.returncode == 0 and first else (
            None, f"{path} --version failed (exit {result.returncode})"
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        outcome = (None, f"{path} could not be run: {exc}")
    _VERSION_CACHE[path] = outcome
    return outcome


def probe_pdflatex() -> EngineStatus:
    path, reason = find_pdflatex()
    if path is None:
        return EngineStatus("pdflatex", False, reason=reason)
    version, reason = _pdflatex_version(path)
    if version is None:
        return EngineStatus("pdflatex", False, path=path, reason=reason)
    return EngineStatus("pdflatex", True, version=version, path=path)


def pdflatex_available() -> bool:
    return probe_pdflatex().available


def probe_typst() -> EngineStatus:
    try:
        import typst  # noqa: F401 — presence is the point
    except ImportError:
        return EngineStatus("typst", False, reason="the typst package is not installed")
    version = importlib.metadata.version("typst")
    missing = [str(p) for p in settings.typst_font_paths if not Path(p).is_dir()]
    if missing:
        # typst falls back to embedded fonts SILENTLY for a missing dir — a
        # wrong typeface, not an error — so report it here instead.
        return EngineStatus(
            "typst", False, version=version,
            reason=f"font directory missing: {', '.join(missing)}",
        )
    return EngineStatus("typst", True, version=version)


def probe() -> EnginesStatus:
    return EnginesStatus(pdflatex=probe_pdflatex(), typst=probe_typst())
