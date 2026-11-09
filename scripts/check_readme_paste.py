#!/usr/bin/env python3
"""Run the README's Start here paste on this machine, the way a new user would.

The README promises one paste on a new machine, and it holds only because of its PATH line: a
terminal can't find uv until it's reopened. .github/workflows/readme-paste.yml runs this on macOS,
Linux and Windows. `maestro start` becomes `maestro --version`, because the paste is what's under
test here, and scripts/smoke_uv_install.py already starts the app. Run it only on a throwaway
machine: it installs uv and Maestro for the user it runs as.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

README = Path(__file__).resolve().parent.parent / "README.md"
LAST_LINE = "maestro start"


def paste_blocks(readme: str) -> dict[str, list[str]]:
    """The paste for each shell, from the Start here section only."""
    section = readme.split("## Start here", 1)[1].split("\n## ", 1)[0]
    return {
        shell: code.strip().splitlines()
        for shell, code in re.findall(r"^```(bash|powershell)\n(.*?)^```", section, flags=re.M | re.S)
    }


def script_for(lines: list[str]) -> list[str]:
    """The paste, with its last line swapped for one that proves `maestro` is found."""
    if lines[-1] != LAST_LINE:
        raise ValueError(f"the paste should end with {LAST_LINE!r}, not {lines[-1]!r}")
    return [*lines[:-1], "maestro --version"]


def without_local_bin(path: str) -> str:
    """PATH without ~/.local/bin, which hosted runners already list and a new machine's terminal doesn't."""
    keep = [p for p in path.split(os.pathsep) if not p.rstrip("/\\").endswith((".local/bin", ".local\\bin"))]
    return os.pathsep.join(keep)


def run_paste(lines: list[str]) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PATH": without_local_bin(os.environ["PATH"])}
    with tempfile.TemporaryDirectory() as folder:
        if os.name == "nt":
            script = Path(folder) / "paste.ps1"
            script.write_text("\n".join([*script_for(lines), "exit $LASTEXITCODE", ""]), encoding="utf-8")
            command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
        else:
            script = Path(folder) / "paste.sh"
            script.write_text("\n".join([*script_for(lines), ""]), encoding="utf-8")
            command = [shutil.which("zsh") or "bash", str(script)]
        return subprocess.run(command, env=env, text=True, capture_output=True, timeout=1200, check=False)


def main() -> int:
    blocks = paste_blocks(README.read_text(encoding="utf-8"))
    done = run_paste(blocks["powershell" if os.name == "nt" else "bash"])
    print(done.stdout)
    print(done.stderr, file=sys.stderr)
    if done.returncode != 0 or "maestro-career-studio" not in done.stdout:
        print("The README's paste did not end with a working `maestro`.", file=sys.stderr)
        return 1
    print("The README's paste works here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
