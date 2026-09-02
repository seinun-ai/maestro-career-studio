#!/usr/bin/env python3
"""check_system_md.py — hygiene gate for SYSTEM.md. Generated from the
bootstrap-system-md skill's gate template (contract v4) and adapted to this
repo; adjust CONFIG. Rationale for the generic rules AND for every
repo-specific choice below: docs/system-md-contract.md.

LEVEL controls which checks run; this repo is "large":
  small : length (WARN at 90% of the cap, naming the extraction candidate;
          FAIL at 100%), accretion detector (a `(YYYY-MM-DD` date outside
          the ledgers), SHIPPED/DONE markers in the deferred ledger, deferred
          items missing a "do when" trigger (WARN — graveyard entries)
  medium: + per-section budgets (FAIL), baselines sidecar
  large : + enforcement-point verification (.system_md_enforcement.json:
          every pinned invariant must still have its file and symbol, and
          every pin must still name an invariant in the doc), the reference
          tier under the same accretion check, and --update-baselines
          requires --reason

FAIL is exit 1. Stdlib only. Run from anywhere inside the repo:

    python3 scripts/check_system_md.py [--update-baselines --reason "<text>"]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# ---- CONFIG ----------------------------------------------------------------
LEVEL = "large"                  # "small" | "medium" | "large"

# The repo root is the parent of this script's directory. It is NOT discovered
# by walking up looking for SYSTEM.md: this repo is worked in git worktrees
# under `.claude/worktrees/`, and a walk-up finds the MAIN checkout's copy and
# silently validates the wrong file. That happened.
ROOT = Path(__file__).resolve().parent.parent
SYSTEM_MD = ROOT / "SYSTEM.md"
LEDGER = ROOT / ".slopledger.json"          # sidecar: baselines live under "system_md_baselines"
ENFORCEMENT_MAP = ROOT / ".system_md_enforcement.json"

# Reference tier — extracted from the root file, same contract, same checks.
REFERENCE_GLOBS = ("docs/entities/*.md", "docs/frontend-conventions.md")

CAP_LINES = 1000                 # ~15% above the post-extraction size
WARN_AT = 0.90                   # plan an extraction here, not under fail pressure

# Budget is a share of THE CAP, not of the current total (share-of-total
# tightens every survivor the moment one section is extracted — see the
# rationale doc). 0.25 rather than the template's 0.15 because this orientation
# tier carries two irreducibly large sections (§6 invariants, §7 agent
# surfaces) and the contract forbids splitting orientation content.
SECTION_BUDGET = 0.25            # 250 lines at the current cap

# Sections that are reference-shaped: the largest of these is the extraction
# candidate the length warning names.
REFERENCE_HEADINGS = ("entities", "agent surfaces", "conventions")
LEDGER_HEADINGS = ("deferred", "gotchas", "migrations & deprecation")

DATE_RX = re.compile(r"\(20\d\d-\d\d-\d\d")
# Uppercase only, deliberately: §11 items legitimately say "shipped as X" in
# lowercase when describing a partial landing; the marker form is the ledger rot.
SHIPPED_RX = re.compile(r"\b(SHIPPED|DONE)\b")
TRIGGER_RX = re.compile(r"\bdo when\b", re.I)
ITEM_RX = re.compile(r"^\s*\d+\.\s")
INV_ID_RX = re.compile(r"\{#(inv-[a-z0-9-]+)\}")
# -----------------------------------------------------------------------------


def sections(lines: list[str]) -> list[tuple[str, int, int]]:
    out, name, start = [], "(preamble)", 0
    for i, ln in enumerate(lines):
        if ln.startswith("## "):
            out.append((name, start, i))
            name, start = ln[3:].strip(), i
    out.append((name, start, len(lines)))
    return out


def has(name: str, keys: tuple[str, ...]) -> bool:
    return any(k in name.lower() for k in keys)


def check_accretion(name: str, body: list[str], offset: int, where: str) -> list[str]:
    if has(name, LEDGER_HEADINGS):
        return []
    return [f"date in descriptive section '{name}' ({where} line {j}): integrate, "
            f"don't append — history lives in git log"
            for j, ln in enumerate(body, offset + 1) if DATE_RX.search(ln)]


def check_deferred(body: list[str], offset: int) -> tuple[list[str], list[str]]:
    """Shipped markers FAIL; a numbered item with no 'do when' trigger WARNS.
    An item is its numbered line plus continuation lines up to the next item
    or blank line, so a trigger on a wrapped line still counts."""
    errs = [f"shipped item still in the deferred ledger (line {j}): delete it, "
            f"git remembers" for j, ln in enumerate(body, offset + 1)
            if SHIPPED_RX.search(ln)]
    warns: list[str] = []
    item_start, item_text = None, []
    def flush():
        if item_start is not None and not TRIGGER_RX.search(" ".join(item_text)):
            warns.append(f"deferred item at line {item_start} has no 'do when' trigger "
                         f"— graveyard entry; add a trigger or delete it")
    for j, ln in enumerate(body, offset + 1):
        if ITEM_RX.match(ln):
            flush(); item_start, item_text = j, [ln]
        elif item_start is not None and ln.strip():
            item_text.append(ln)
        else:
            flush(); item_start, item_text = None, []
    flush()
    return errs, warns


def check_enforcement() -> list[str]:
    """Every documented invariant must still have something enforcing it."""
    if not ENFORCEMENT_MAP.exists():
        return []
    doc = json.loads(ENFORCEMENT_MAP.read_text())
    pins = doc.get("invariants", doc)          # also accepts the flat template shape
    errs = []
    doc_ids = set(INV_ID_RX.findall(SYSTEM_MD.read_text(encoding="utf-8")))

    for inv, spec in pins.items():
        if inv.startswith("_"):
            continue
        if inv not in doc_ids:
            errs.append(f"enforcement map pins {inv}, which no longer appears in "
                        f"SYSTEM.md — the invariant was renamed or removed and the "
                        f"pin is now guarding nothing")
        for pin in (spec if isinstance(spec, list) else [spec]):
            tgt = ROOT / pin["path"]
            if not tgt.is_file():
                errs.append(f"invariant {inv}: enforcement point {pin['path']} is "
                            f"gone — the doc promises what the code no longer does")
            elif pin.get("symbol") and pin["symbol"] not in tgt.read_text(
                    encoding="utf-8", errors="replace"):
                errs.append(f"invariant {inv}: symbol {pin['symbol']!r} no longer in "
                            f"{pin['path']} — re-verify the invariant or move the pin")

    for inv in doc.get("unpinned", {}).get("ids", []):
        if inv not in doc_ids:
            errs.append(f"unpinned list names {inv}, which is not in SYSTEM.md — "
                        f"drop it from the list or restore the invariant")
    return errs


def load_baselines() -> dict:
    if not LEDGER.exists():
        return {}
    return json.loads(LEDGER.read_text()).get("system_md_baselines", {})


def save_baselines(counts: dict, total: int, reason: str | None) -> None:
    data = json.loads(LEDGER.read_text()) if LEDGER.exists() else {}
    data["system_md_baselines"] = {"total": total, "sections": counts, "reason": reason}
    LEDGER.write_text(json.dumps(data, indent=2) + "\n")


def main() -> int:
    argv = sys.argv[1:]
    lines = SYSTEM_MD.read_text(encoding="utf-8").splitlines()
    secs = sections(lines)
    counts = {name: b - a for name, a, b in secs}
    total = len(lines)
    errs: list[str] = []
    warns: list[str] = []

    # Length: two thresholds. The warning names where the next extraction goes.
    biggest_ref = max(((n, c) for n, c in counts.items() if has(n, REFERENCE_HEADINGS)),
                      key=lambda t: t[1], default=None)
    hint = (f" — extraction candidate: '{biggest_ref[0]}' ({biggest_ref[1]} lines) "
            f"→ docs/ with an index left behind") if biggest_ref else ""
    if total > CAP_LINES:
        errs.append(f"SYSTEM.md is {total} lines (> {CAP_LINES}). Groom or extract before "
                    f"feature work; raise the cap only after that fails, with "
                    f"--reason — prove incompressibility before buying budget{hint}")
    elif total > CAP_LINES * WARN_AT:
        warns.append(f"SYSTEM.md is {total}/{CAP_LINES} lines ({total/CAP_LINES:.0%}) — "
                     f"plan an extraction now, not under fail pressure{hint}")

    for name, a, b in secs:
        body = lines[a:b]
        errs += check_accretion(name, body, a, "SYSTEM.md")
        if "deferred" in name.lower():
            e, w = check_deferred(body, a)
            errs += e; warns += w

    if LEVEL in ("medium", "large"):
        budget_lines = int(CAP_LINES * SECTION_BUDGET)
        for name, n in counts.items():
            if has(name, LEDGER_HEADINGS) or name == "(preamble)":
                continue
            if n > budget_lines:
                errs.append(f"'{name}' is {n} lines (> {budget_lines} budget). Groom it, "
                            f"or extract it to the reference tier under docs/ and leave "
                            f"an index — never split the orientation tier.")

    if LEVEL == "large":
        # The reference tier carries the same contract as the root file.
        for pattern in REFERENCE_GLOBS:
            for f in sorted(ROOT.glob(pattern)):
                rlines = f.read_text(encoding="utf-8").splitlines()
                errs += check_accretion(f.name, rlines, 0, f.relative_to(ROOT).as_posix())
        errs += check_enforcement()

    base = load_baselines()
    if base.get("sections"):
        for name, n in counts.items():
            b = base["sections"].get(name)
            if b and n > b * 1.25:
                warns.append(f"'{name}' is {n} lines, >25% over its baseline of {b}. "
                             f"Integrate, don't append — or re-baseline with a reason.")

    if "--update-baselines" in argv:
        reason = argv[argv.index("--reason") + 1] if "--reason" in argv else None
        if LEVEL == "large" and not reason:
            print('FAIL: re-baselining requires --reason "<text>" — every movement of '
                  'a baseline needs an auditable justification', file=sys.stderr)
            return 1
        save_baselines(counts, total, reason)
        print(f"baselines updated in {LEDGER.name} (reason: {reason})")
        return 0

    for w in warns:
        print(f"WARN: {w}")
    for e in errs:
        print(f"FAIL: {e}")
    if errs:
        print("\nSYSTEM.md header contract: integrate don't append; ledgers shrink; "
              "caps are earned.", file=sys.stderr)
        return 1

    ref = sum(len(f.read_text(encoding="utf-8").splitlines())
              for pattern in REFERENCE_GLOBS for f in sorted(ROOT.glob(pattern)))
    print(f"check_system_md: OK ({LEVEL}) — {total}/{CAP_LINES} lines in the orientation "
          f"tier, {ref} more in the reference tier, {len(secs) - 1} sections, "
          f"{len(warns)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
