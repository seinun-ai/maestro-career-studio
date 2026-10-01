#!/usr/bin/env python3
"""Fail if the committed .mcpb does not match the source it was packed from.

The bundle is committed so a user can install it straight out of their clone
(docs/GETTING_STARTED.md Part 2). That convenience has one predictable failure:
someone edits the manifest or the shim, does not re-pack, and the bundle keeps
installing older behaviour without anything looking wrong.

Compares CONTENTS rather than bytes: a zip carries timestamps, so a byte
comparison would fail on a re-pack that changed nothing. Needs no npm, so it
runs in CI without a Node toolchain.

    python3 scripts/check_mcpb_bundle.py          # from the repo root
"""
from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "mcpb"
BUNDLE = SRC / "maestro-career-studio.mcpb"
SERVER_JSON = ROOT / "server.json"
# Every path the bundle is expected to carry, mapped to its source file.
TRACKED = {"manifest.json": SRC / "manifest.json",
           "icon.png": SRC / "icon.png",
           "server/index.js": SRC / "server" / "index.js"}


def main() -> int:
    if not BUNDLE.exists():
        print(f"error: {BUNDLE.relative_to(ROOT)} is missing — run `mcpb pack`", file=sys.stderr)
        return 1

    with zipfile.ZipFile(BUNDLE) as zf:
        packed = set(zf.namelist())
        expected = set(TRACKED)
        if packed != expected:
            print(f"error: bundle contents changed.\n  in bundle: {sorted(packed)}"
                  f"\n  expected : {sorted(expected)}", file=sys.stderr)
            return 1
        stale = [name for name, source in TRACKED.items()
                 if zf.read(name) != source.read_bytes()]

    if stale:
        print("error: the committed bundle is stale — re-pack it:\n"
              "    cd mcpb && npx @anthropic-ai/mcpb pack . maestro-career-studio.mcpb\n"
              "  differs from source: " + ", ".join(stale), file=sys.stderr)
        return 1

    # server.json pins the bundle by hash for the MCP Registry. Unlike the
    # contents check above this one IS byte-level: a re-pack that changed nothing
    # still moves the hash, and every registry install would then fail its
    # integrity check.
    if SERVER_JSON.exists():
        problems = check_server_json()
        if problems:
            print("error: server.json does not match the committed bundle:\n  "
                  + "\n  ".join(problems), file=sys.stderr)
            return 1

    print(f"check_mcpb_bundle: OK — {len(TRACKED)} files match "
          f"({BUNDLE.stat().st_size} bytes)")
    return 0


def check_server_json() -> list[str]:
    server = json.loads(SERVER_JSON.read_text(encoding="utf-8"))
    version = json.loads((SRC / "manifest.json").read_text(encoding="utf-8"))["version"]
    sha = hashlib.sha256(BUNDLE.read_bytes()).hexdigest()
    problems = []
    if server.get("version") != version:
        problems.append(f"version {server.get('version')!r} != mcpb manifest {version!r}")
    for pkg in server.get("packages", []):
        if pkg.get("registryType") != "mcpb":
            continue
        if pkg.get("version") != version:
            problems.append(f"package version {pkg.get('version')!r} != {version!r}")
        if f"/releases/download/v{version}/" not in pkg.get("identifier", ""):
            problems.append(f"identifier does not point at the v{version} release")
        if pkg.get("fileSha256") != sha:
            problems.append(f"fileSha256 is stale — set it to {sha}")
    return problems


if __name__ == "__main__":
    raise SystemExit(main())
