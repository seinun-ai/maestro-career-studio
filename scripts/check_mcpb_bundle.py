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

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "mcpb"
BUNDLE = SRC / "maestro-career-studio.mcpb"
# Every path the bundle is expected to carry, mapped to its source file.
TRACKED = {"manifest.json": SRC / "manifest.json",
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

    print(f"check_mcpb_bundle: OK — {len(TRACKED)} files match "
          f"({BUNDLE.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
