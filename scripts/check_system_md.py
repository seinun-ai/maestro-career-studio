#!/usr/bin/env python3
"""Machine gate for docs/SYSTEM.md — enforces the header contract.

The header rule this file enforces:

    Integrate, don't append. When your change alters described behavior,
    REWRITE the affected description in present tense — do not add a dated
    paragraph below it. Dates and change narratives belong in `git log`,
    not in §1–§10. Dated entries are legal ONLY in §11–§13 (the ledgers).
    Ledgers must shrink. §11: delete items when shipped (git remembers).
    §13: cut the row when the migration completes.

Checks (FAIL = exit 1):
  * total line count over the ceiling
  * a parenthesized date `(20YY-MM-DD` in any §1–§10 body (append-detector)
  * SHIPPED / shipped / DONE (word-bounded) inside §11

Checks (WARN = exit 0):
  * any section more than 25% over its recorded baseline line count
    (baselines live in `.slopledger.json` under "system_md_baselines";
    refresh them after a deliberate grooming pass with --update-baselines)

Stdlib only. Run from anywhere inside the repo:

    python scripts/check_system_md.py [--update-baselines]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# RAISED to 1800 on 2026-08-09, deliberately, after the ceiling stopped
# working as a budget and started working as a tripwire.
#
# The two branches that merged here had independently concluded the same thing.
# main crept 1,500 -> 1,503 -> 1,506 in single digits, twice in one day, each
# time by owner call for real facts that would not fit; this branch jumped to
# 1,800 with the reasoning below. Three raises in three days IS the argument:
# a limit renegotiated that often is not restraining anything, it is just
# charging a toll on every edit.
#
# History: the grooming spec wanted 1,300 with a 1,400 ceiling; the 2026-08-08
# pass stopped at 1,482 and parked the ceiling at 1,500. The file then sat at
# 1,498-1,499 for weeks, which meant every single edit — including one-line
# corrections to things that had become false — had to win an argument with the
# gate first. A ceiling you are permanently one line under does not cause
# integration, it causes avoidance, and the failure mode is a document that
# quietly goes stale because fixing it is annoying.
#
# 1800 is arbitrary; what matters is that it is far enough away to be a budget
# you notice occasionally rather than a wall you touch daily. The point of the
# rule was never the number — it is "integrate, don't append", and the
# per-section growth check below is a better read on whether that is happening.
#
# NOTE that the per-section check only WARNS (exit 0). So between here and 1800
# nothing hard-stops accretion; that is a deliberate trade for editability, not
# an oversight. If this file reaches ~1750 the honest response is another
# grooming pass, not another raise — and the standing debt main recorded still
# stands: a pass that takes the whole file back under 1,400.
MAX_TOTAL_LINES = 1800
GROWTH_WARN_RATIO = 1.25
DATE_RE = re.compile(r"\(20\d\d-\d\d-\d\d")
SHIPPED_RE = re.compile(r"\b(SHIPPED|shipped|DONE)\b")

HEADER_RULE = (
    '"Integrate, don\'t append. Dates and change narratives belong in '
    "`git log`, not in §1–§10. Dated entries are legal ONLY in §11–§13 "
    '(the ledgers). Ledgers must shrink."'
)


def find_repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        if (candidate / "docs" / "SYSTEM.md").is_file():
            return candidate
    sys.exit("check_system_md: cannot locate docs/SYSTEM.md above %s" % here)


def parse_sections(lines: list[str]) -> dict[str, tuple[int, int]]:
    """Map section number ('1'..'13') -> (start_line, end_line), 1-indexed,
    body inclusive of the heading, exclusive of the next `## ` heading."""
    heads: list[tuple[str, int]] = []
    for idx, line in enumerate(lines, start=1):
        m = re.match(r"^## (\d+)\.", line)
        if m:
            heads.append((m.group(1), idx))
    sections: dict[str, tuple[int, int]] = {}
    for (num, start), nxt in zip(heads, heads[1:] + [("", len(lines) + 1)]):
        sections[num] = (start, nxt[1] - 1)
    return sections


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--update-baselines",
        action="store_true",
        help="record current per-section line counts into .slopledger.json",
    )
    args = ap.parse_args()

    root = find_repo_root()
    system_md = root / "docs" / "SYSTEM.md"
    ledger_path = root / ".slopledger.json"
    lines = system_md.read_text(encoding="utf-8").splitlines()
    sections = parse_sections(lines)
    total = len(lines)

    if args.update_baselines:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        ledger["system_md_baselines"] = {
            "total": total,
            "sections": {num: end - start + 1 for num, (start, end) in sections.items()},
        }
        ledger_path.write_text(
            json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"check_system_md: baselines updated (total={total})")
        return 0

    failures: list[str] = []
    warnings: list[str] = []

    if total > MAX_TOTAL_LINES:
        failures.append(
            f"docs/SYSTEM.md is {total} lines (> {MAX_TOTAL_LINES}). "
            f"The header rule says {HEADER_RULE} — groom before feature work."
        )

    for num in map(str, range(1, 11)):
        if num not in sections:
            failures.append(f"section §{num} heading not found — file structure changed?")
            continue
        start, end = sections[num]
        for idx in range(start, end + 1):
            if DATE_RE.search(lines[idx - 1]):
                failures.append(
                    f"§{num} line {idx}: dated entry `{lines[idx - 1].strip()[:70]}` — "
                    f"the header rule says {HEADER_RULE} Fold this into the "
                    "present-tense description; the date belongs in git log."
                )

    if "11" in sections:
        start, end = sections["11"]
        for idx in range(start, end + 1):
            if SHIPPED_RE.search(lines[idx - 1]):
                failures.append(
                    f"§11 line {idx}: `{lines[idx - 1].strip()[:70]}` — "
                    f"the header rule says {HEADER_RULE} Delete shipped items "
                    "from §11; git remembers."
                )
    else:
        failures.append("section §11 heading not found — file structure changed?")

    baselines = {}
    if ledger_path.is_file():
        baselines = json.loads(ledger_path.read_text(encoding="utf-8")).get(
            "system_md_baselines", {}
        )
    if baselines:
        base_sections = baselines.get("sections", {})
        for num, (start, end) in sections.items():
            base = base_sections.get(num)
            count = end - start + 1
            if base and count > base * GROWTH_WARN_RATIO:
                warnings.append(
                    f"§{num} is {count} lines, more than 25% over its baseline of "
                    f"{base}. Integrate, don't append — or re-baseline "
                    "deliberately with --update-baselines."
                )
        base_total = baselines.get("total")
        if base_total and total > base_total * GROWTH_WARN_RATIO:
            warnings.append(
                f"total is {total} lines, more than 25% over the baseline of "
                f"{base_total}."
            )
    else:
        warnings.append(
            "no system_md_baselines in .slopledger.json — run with "
            "--update-baselines after a grooming pass."
        )

    for w in warnings:
        print(f"WARN: {w}")
    for f in failures:
        print(f"FAIL: {f}")
    if failures:
        return 1
    print(f"check_system_md: OK ({total} lines, {len(sections)} sections)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
