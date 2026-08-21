#!/usr/bin/env python3
"""Machine gate for SYSTEM.md — enforces the header contract.

Generated from the `bootstrap-system-md` skill's gate template, adapted to this
repo. What it defends, in the order the failures actually happen:

  * ACCRETION — the contract works too well and agents honour it by appending
    dated paragraphs instead of rewriting descriptions. Caught by grepping for
    `(YYYY-MM-DD` outside the ledgers, and by the size cap.
  * SPRAWL — one section swallows the file. Caught by a per-section budget.
  * STALENESS — the doc keeps promising behaviour the code dropped. Caught by
    the enforcement map: every §6 invariant names a file and a symbol that must
    still exist.
  * LEDGER ROT — shipped work left in the deferred ledger. Caught by grepping
    §11 for SHIPPED/DONE.

FAIL (exit 1) on any of the above. Re-baselining requires `--update-baselines
--reason "<text>"`; a cap or budget moved without an auditable reason is the
doc-shaped version of re-baselining past a regression.

Stdlib only. Run from anywhere inside the repo:

    python3 scripts/check_system_md.py [--update-baselines --reason "..."]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# ---- CONFIG ----------------------------------------------------------------
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

# Budget is a share of THE CAP, not of the current total. A share-of-total
# budget tightens every remaining section the moment you extract one — the
# extraction the contract prescribes makes the file smaller, so every survivor's
# share rises and sections that never grew start failing. Measured here: after
# moving §4 and §8 to the reference tier, §6 went from 10% to 20% without a line
# being added. Same trap as gating a duplication percentage instead of absolute
# duplicated lines. Against the cap the number means "lines", and it is stable.
SECTION_BUDGET = 0.25            # 250 lines at the current cap
BUDGET_NOTE = (
    "0.25 rather than the template's 0.15 because this repo's orientation tier "
    "carries two irreducibly large sections (§6 invariants, §7 agent surfaces) "
    "and the contract forbids splitting orientation content. Recorded, not "
    "silently widened."
)

LEDGER_HEADINGS = ("deferred", "gotchas", "migrations & deprecation")
DATE_RX = re.compile(r"\(20\d\d-\d\d-\d\d")
SHIPPED_RX = re.compile(r"\b(SHIPPED|DONE)\b")
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


def is_ledger(name: str) -> bool:
    return any(k in name.lower() for k in LEDGER_HEADINGS)


def check_accretion(name: str, body: list[str], offset: int, where: str) -> list[str]:
    if is_ledger(name):
        return []
    return [f"date in descriptive section '{name}' ({where} line {j}): integrate, "
            f"don't append — history lives in git log"
            for j, ln in enumerate(body, offset + 1) if DATE_RX.search(ln)]


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


def save_baselines(counts: dict, total: int, reason: str) -> None:
    data = json.loads(LEDGER.read_text())
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

    if total > CAP_LINES:
        errs.append(f"SYSTEM.md is {total} lines (> {CAP_LINES}). Groom before feature "
                    f"work. The cap may be raised only immediately after a grooming "
                    f"pass that failed to get under it — prove incompressibility "
                    f"before buying budget.")

    for name, a, b in secs:
        body = lines[a:b]
        errs += check_accretion(name, body, a, "SYSTEM.md")
        if "deferred" in name.lower():
            errs += [f"shipped item still in the deferred ledger (line {j}): delete it, "
                     f"git remembers" for j, ln in enumerate(body, a + 1)
                     if SHIPPED_RX.search(ln)]

    budget_lines = int(CAP_LINES * SECTION_BUDGET)
    for name, n in counts.items():
        if is_ledger(name) or name == "(preamble)":
            continue
        if n > budget_lines:
            errs.append(f"'{name}' is {n} lines (> {budget_lines} budget). Groom it, or "
                        f"extract it to the reference tier under docs/ and leave an "
                        f"index — never split the orientation tier.")

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
        if "--reason" not in argv:
            print('FAIL: re-baselining requires --reason "<text>" — every movement of '
                  'a baseline needs an auditable justification', file=sys.stderr)
            return 1
        reason = argv[argv.index("--reason") + 1]
        save_baselines(counts, total, reason)
        print(f"baselines updated in {LEDGER.name} (reason: {reason})")
        return 0

    for w in warns:
        print(f"WARN: {w}")
    for e in errs:
        print(f"FAIL: {e}")
    if errs:
        print("\nSYSTEM.md header contract: integrate don't append; ledgers must "
              "shrink; caps are earned.", file=sys.stderr)
        return 1

    ref = sum(len(( ROOT / f).read_text(encoding="utf-8").splitlines())
              for pattern in REFERENCE_GLOBS for f in sorted(ROOT.glob(pattern)))
    print(f"check_system_md: OK — {total}/{CAP_LINES} lines in the orientation tier, "
          f"{ref} more in the reference tier, {len(secs) - 1} sections, "
          f"{len(warns)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
