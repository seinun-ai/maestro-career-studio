#!/usr/bin/env python3
"""Report (and optionally fix) prompt rows that have drifted from their files.

WHY THIS EXISTS
---------------
`app/services/prompts.get_prompt()` returns the `settings` row `prompt.<key>`
whenever one exists; the file under `app/prompts/` is only the fallback used to
SEED a missing row. So once a row exists, editing the .txt file changes nothing
at runtime — the row wins, permanently.

That is deliberate (it is how a user's customized prompt survives an upgrade),
and it is why shipping a prompt edit is supposed to come with a resync migration
that rewrites the row *only* when it still matches the previous default. When a
release edits a prompt and skips that migration, the row silently keeps serving
old instructions: the code, the tests and the file all say one thing, and the
running app does another.

A fresh install is never affected — no rows exist, so every prompt seeds from
the current file. This is strictly an EXISTING-INSTALL problem, which is exactly
the kind that goes unnoticed until someone wonders why a shipped feature does
not seem to be on.

USAGE
-----
    python3 scripts/prompt-drift.py                  # report only (default)
    python3 scripts/prompt-drift.py --diff           # show what differs
    python3 scripts/prompt-drift.py --reset KEY ...  # reset named prompts
    python3 scripts/prompt-drift.py --reset-all      # reset every drifted prompt

Reporting is the default because a drifted row is AMBIGUOUS: it is either a
stale default or a customization the user made on purpose, and nothing stored
distinguishes them. Read the diff before resetting. `--reset` writes the current
file default over the row and cannot be undone from here, so it prints a backup
path first.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROMPT_DIR = REPO / "backend" / "app" / "prompts"


def backend_url() -> str:
    if url := os.environ.get("BACKEND_URL"):
        return url.rstrip("/")
    port = "8001"
    env = REPO / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if m := re.match(r"\s*BACKEND_HOST_PORT\s*=\s*['\"]?(\d+)", line):
                port = m.group(1)
    return f"http://localhost:{port}"


def api(base: str, path: str, method: str = "GET"):
    req = urllib.request.Request(f"{base}/api/settings{path}", method=method)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--diff", action="store_true", help="show a unified diff per drifted prompt")
    ap.add_argument("--reset", nargs="+", metavar="KEY", help="reset these prompt keys to their file default")
    ap.add_argument("--reset-all", action="store_true", help="reset every drifted prompt")
    args = ap.parse_args()

    base = backend_url()
    try:
        rows = api(base, "/prompts")
    except (urllib.error.URLError, OSError) as exc:
        print(f"error: cannot reach the backend at {base} ({exc}).", file=sys.stderr)
        print("Start it with 'docker compose up -d' and check the published port.", file=sys.stderr)
        return 2

    drifted: dict[str, tuple[str, str]] = {}
    missing_file: list[str] = []
    for row in rows:
        key, live = row["key"], row["value"] or ""
        path = PROMPT_DIR / f"{key}.txt"
        if not path.is_file():
            missing_file.append(key)
            continue
        default = path.read_text(encoding="utf-8")
        if live.rstrip() != default.rstrip():
            drifted[key] = (live, default)

    print(f"backend: {base}")
    print(f"prompts checked: {len(rows)}   in sync: {len(rows) - len(drifted) - len(missing_file)}   drifted: {len(drifted)}")
    if missing_file:
        print(f"no file on disk (cannot compare): {', '.join(missing_file)}")

    if not drifted:
        print("\nEvery prompt row matches its file default.")
        return 0

    print("\nDrifted — the RUNNING app uses the stored row, not the file:")
    for key, (live, default) in drifted.items():
        print(f"  - {key}  (stored {len(live)} chars, file {len(default)} chars)")

    if args.diff:
        for key, (live, default) in drifted.items():
            print(f"\n{'=' * 70}\n{key}\n{'=' * 70}")
            for line in difflib.unified_diff(
                live.splitlines(), default.splitlines(),
                fromfile="stored row (what the app uses)",
                tofile=f"app/prompts/{key}.txt (what the code ships)",
                lineterm="",
            ):
                print(line)

    targets: list[str] = []
    if args.reset_all:
        targets = list(drifted)
    elif args.reset:
        unknown = [k for k in args.reset if k not in drifted]
        if unknown:
            print(f"\nerror: not drifted (or not a prompt): {', '.join(unknown)}", file=sys.stderr)
            return 2
        targets = args.reset

    if not targets:
        print("\nNothing was changed. Re-run with --diff to inspect, then")
        print("--reset <key> to overwrite a row with the current file default.")
        print("A drifted row may be YOUR customization — read the diff first.")
        return 1

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = REPO / "logs" / f"prompt-backup-{stamp}.json"
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text(
        json.dumps({k: drifted[k][0] for k in targets}, indent=2), encoding="utf-8"
    )
    print(f"\nbacked up {len(targets)} stored row(s) to {backup}")

    for key in targets:
        api(base, f"/prompts/{key}/reset", method="POST")
        print(f"  reset {key}")
    print("\nDone. The reset rows now match the files the code ships.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
