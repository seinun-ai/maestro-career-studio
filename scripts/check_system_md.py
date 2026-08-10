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

# The grooming spec targets 1,300 lines with a 1,400 FAIL ceiling. The
# 2026-08-08 retroactive grooming pass stopped at 1,482 (owner call:
# diminishing returns vs. rule preservation), so the ceiling is parked at
# 1,500. Tighten to 1400 after the next grooming pass gets under it.
MAX_TOTAL_LINES = 1500
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
