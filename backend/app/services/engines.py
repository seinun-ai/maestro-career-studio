"""Which PDF engines can THIS process run — the one place that looks for one.

A GUI-launched process (the desktop shell, a Claude Desktop child) has no shell
`PATH`, so MacTeX's `/Library/TeX/texbin` is invisible to it. The probe searches
the known TeX homes after `PATH`, and `pdf_render` runs the resolved absolute
path. `MAESTRO_CS_PDFLATEX` overrides the search and fails closed when wrong.

Cheap by design: `which` re-runs on every call (installing TeX while the app
runs is noticed on the next probe), the `--version` subprocess runs once per
working path per process (a failed `--version` is retried on the next probe).
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

# Where TeX installs put pdflatex when it is not on PATH, in priority order.
_TEX_HOMES_POSIX = (
    "/Library/TeX/texbin",
    "/usr/local/texlive/*/bin/*",
    "~/.TinyTeX/bin/*",
    # Not TeX homes: the package managers' bin dirs, where TinyTeX's
    # `tlmgr path add` and a Homebrew formula LINK pdflatex. Last, and searched
    # only after PATH and the real TeX homes, so they add a fallback without
    # ever outranking a genuine install.
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
        # Reverse-sorted WITHIN a pattern (so patterns keep their priority
        # order): that puts the newest TeX Live first only because the year is
        # the first varying component and always four digits, which makes the
        # string order the numeric order.
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
    # SPLIT PATH first, then drop every empty component. An empty component
    # means "the current directory" to shutil.which, and `PATH=/usr/bin:` or
    # `/a::/b` hides one mid-string — so does an absent PATH, which is the
    # GUI-launched process this module exists for. This is not about honouring
    # shell PATH semantics: the probe's contract is an ABSOLUTE path to hand to
    # `pdf_render`, and a cwd-relative hit is not one (the render subprocess
    # runs with `cwd=<staging dir>`, so it would not even be the same file).
    # The cwd is never a candidate.
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    entries = [e for e in [*path_entries, *_candidate_dirs()] if e]
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


# resolved path -> version string. SUCCESSES ONLY, so one --version runs per
# working path per process.
_VERSION_CACHE: dict[str, str] = {}


def reset_cache() -> None:
    _VERSION_CACHE.clear()


def _pdflatex_version(path: str) -> tuple[str | None, str | None]:
    """(version, reason), caching successes and never failures.

    A failure here is routinely transient — a probe landing mid-install finds
    the symlink farm before the binary is runnable — and caching it would mark
    TeX missing for the life of the process, which is exactly what this
    module's "noticed on the next probe, no restart" promise rules out.
    """
    cached = _VERSION_CACHE.get(path)
    if cached is not None:
        return cached, None
    try:
        result = subprocess.run(
            [path, "--version"],
            capture_output=True,
            # Not text=True: that decodes STRICTLY, and a compiler banner in an
            # unexpected encoding would raise UnicodeDecodeError (a ValueError,
            # not an OSError) out of a probe whose whole job is to report.
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return None, f"{path} could not be run: {exc}"
    lines = (result.stdout or "").strip().splitlines()
    if result.returncode != 0 or not lines:
        return None, f"{path} --version failed (exit {result.returncode})"
    _VERSION_CACHE[path] = lines[0]
    return lines[0], None


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
    try:
        version = importlib.metadata.version("typst")
    except importlib.metadata.PackageNotFoundError:
        # Importable but not installed as a distribution — a frozen build, which
        # is where the desktop shell is headed. The engine still runs.
        version = None
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
