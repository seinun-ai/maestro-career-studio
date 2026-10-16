#!/usr/bin/env python3
"""Machine gate for SYSTEM.md — enforces the header contract (contract v5).

Generated from the `bootstrap-system-md` skill's v5 gate template, adapted to
this repo; rationale and the repo's adaptations: docs/system-md-contract.md.
What it defends, in the order the failures actually happen:

  * ACCRETION — the contract works too well and agents honour it by appending
    dated paragraphs instead of rewriting descriptions. Caught by grepping for
    `(YYYY-MM-DD` outside the ledgers, and by the size cap.
  * METRIC GAMING — a line cap is met by widening lines: 200-character bullets
    cost the same tokens and read worse. The cap is therefore in BYTES; lines
    are reported, never gated; prose lines over LONG_LINE chars are a WARN.
  * SPRAWL — one section swallows the file. Caught by a per-section byte budget
    (a share of the CAP, not of the total — see the rationale doc for why).
  * DEFERRED EXTRACTION — the largest reference-shaped section is named as the
    extraction candidate at the WARN threshold; a candidate that persists across
    the last two recorded baselines FAILS, because a warning that persists is
    no longer advice.
  * STALENESS — the doc keeps promising behaviour the code dropped. Caught by
    the enforcement map: every invariant names a file and a symbol that must
    still exist. An invariant id with no pin at all is a WARN: it reads as
    checked and is not.
  * LEDGER ROT — shipped work left in the deferred ledger (FAIL); deferred
    items without a "do when" trigger (WARN).
  * A HAND-MAINTAINED STAMP — the header's "Last revision" line is written by
    this script from git (`--stamp`), so nothing depends on a human remembering.

FAIL (exit 1) on any FAIL line. Re-baselining requires `--update-baselines
--reason "<text>"`; a cap or budget moved without an auditable reason is the
doc-shaped version of re-baselining past a regression.

Stdlib only. Run from anywhere inside the repo:

    python3 scripts/check_system_md.py [--stamp] [--update-baselines --reason "..."]
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date
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
REFERENCE_GLOBS = ("docs/entities/*.md", "docs/agent-surfaces.md", "docs/frontend-conventions.md")

LEVEL = "large"

# The cap is in BYTES. Converted from the v4 gate's CAP_LINES = 1000 at the
# file's bytes-per-line ratio on the day of the v5 upgrade (124.15 B/line →
# 124,200 B) plus the 1,521 B of contract scaffolding that upgrade itself added
# (header, routing table, ledger rules), rounded up to the hundred, so the
# upgrade is size-neutral against the old cap. Recorded as the baseline reason.
# It moves only after a grooming or extraction pass that failed to get under it.
CAP_BYTES = 125_800
WARN_AT = 0.90
LONG_LINE = 160                  # readability WARN on prose lines (tables and code exempt)

# Budget is a share of THE CAP, not of the current total. A share-of-total
# budget tightens every remaining section the moment you extract one — the
# extraction the contract prescribes makes the file smaller, so every survivor's
# share rises and sections that never grew start failing. Measured here: after
# moving §4 and §8 to the reference tier, §6 went from 10% to 20% without a line
# being added. Against the cap the number means "bytes", and it is stable.
SECTION_BUDGET = 0.25
BUDGET_NOTE = (
    "0.25 rather than the template's 0.15 because this repo's orientation tier "
    "carries two irreducibly large sections (§6 invariants, §7 agent surfaces) "
    "and the contract forbids splitting orientation content. Recorded, not "
    "silently widened."
)

REFERENCE_HEADINGS = ("entities", "agent surfaces", "conventions")   # reference-shaped: extraction candidates
LEDGER_HEADINGS = ("deferred", "gotchas", "migrations & deprecation")
STALE_STAMP_DAYS = 30

DATE_RX = re.compile(r"\(20\d\d-\d\d-\d\d")
SHIPPED_RX = re.compile(r"\b(SHIPPED|DONE)\b")
INV_ID_RX = re.compile(r"\{#(inv-[a-z0-9-]+)\}")
ITEM_RX = re.compile(r"^\s*\d+\.\s")
TRIGGER_RX = re.compile(r"\bdo when\b", re.I)
STAMP_RX = re.compile(r"^(> Last revision: ).*$", re.M)
STAMP_DATE_RX = re.compile(r"^> Last revision: (20\d\d-\d\d-\d\d)", re.M)
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


def is_ledger(name: str) -> bool:
    return has(name, LEDGER_HEADINGS)


def nbytes(lines: list[str]) -> int:
    return sum(len(ln.encode("utf-8")) + 1 for ln in lines)


def fmt_lines(nums: list[int], n: int = 5) -> str:
    shown = ", ".join(str(x) for x in nums[:n])
    return shown + (f", … (+{len(nums) - n})" if len(nums) > n else "")


def git_last_change() -> tuple[str, str]:
    """(YYYY-MM-DD, short sha) of the last commit touching SYSTEM.md."""
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "log", "-1", "--format=%cs %h", "--", SYSTEM_MD.name],
            capture_output=True, text=True, check=True).stdout.strip()
        d, _, sha = out.partition(" ")
        return (d or date.today().isoformat()), sha
    except Exception:
        return date.today().isoformat(), ""


def check_accretion(name: str, body: list[str], offset: int, where: str) -> list[str]:
    if is_ledger(name):
        return []
    return [f"date in descriptive section '{name}' ({where} line {j}): integrate, "
            f"don't append — history lives in git log"
            for j, ln in enumerate(body, offset + 1) if DATE_RX.search(ln)]


def check_long_lines(lines: list[str]) -> list[str]:
    in_code, long = False, []
    for j, ln in enumerate(lines, 1):
        if ln.startswith("```"):
            in_code = not in_code
        if in_code or ln.lstrip().startswith("|"):
            continue
        if len(ln) > LONG_LINE:
            long.append(j)
    if not long:
        return []
    return [f"{len(long)} prose line(s) over {LONG_LINE} chars (lines {fmt_lines(long)}) — reflow; "
            f"width is not compression"]


def check_deferred(body: list[str], offset: int) -> tuple[list[str], list[str]]:
    """Shipped markers FAIL; items (multi-line blocks) without a trigger WARN."""
    errs = [f"shipped item still in the deferred ledger (line {j}): delete it, git remembers"
            for j, ln in enumerate(body, offset + 1) if SHIPPED_RX.search(ln)]
    items: list[tuple[str, int, list[str]]] = []
    for j, ln in enumerate(body, offset + 1):
        if ITEM_RX.match(ln):
            items.append((ln.split(".")[0].strip(), j, [ln]))
        elif items and ln.strip() and not ln.startswith("#"):
            items[-1][2].append(ln)
        elif not ln.strip():
            pass
    missing = [num for num, _, block in items if not TRIGGER_RX.search("\n".join(block))]
    warns = []
    if missing:
        warns.append(f"{len(missing)} of {len(items)} deferred item(s) have no 'do when' trigger "
                     f"(items {fmt_lines(missing, 8)}) — add one or delete; 30 days without one is deletion")
    if len(items) > 7:
        warns.append(f"{len(items)} deferred items in the file; the contract keeps ≤7 here and overflows "
                     f"the rest to docs/deferred.md (items keep their numbers)")
    return errs, warns


def check_enforcement(text: str) -> tuple[list[str], list[str]]:
    """Every documented invariant must still have something enforcing it."""
    # Only the sections carry invariants; the header's `{#inv-slug}` example is not one.
    body = text[text.index("\n## "):] if "\n## " in text else text
    doc_ids = set(INV_ID_RX.findall(body))
    if not ENFORCEMENT_MAP.exists():
        return [], [f"no {ENFORCEMENT_MAP.name}: {len(doc_ids)} invariant ids read as checked and are not"]
    doc = json.loads(ENFORCEMENT_MAP.read_text())
    pins = doc.get("invariants", doc)          # also accepts the flat template shape
    errs, warns = [], []

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

    acknowledged = set(doc.get("unpinned", {}).get("ids", []))
    for inv in sorted(acknowledged - doc_ids):
        errs.append(f"unpinned list names {inv}, which is not in SYSTEM.md — "
                    f"drop it from the list or restore the invariant")
    pinned = {k for k in pins if not k.startswith("_")}
    for inv in sorted(doc_ids - pinned):
        tag = " (acknowledged in the unpinned list)" if inv in acknowledged else " — NOT in the unpinned list either"
        warns.append(f"invariant {inv} has an id but no enforcement pin{tag}: it reads as checked and is "
                     f"not; pin it or demote it to a convention note")
    return errs, warns


def check_stamp(text: str) -> list[str]:
    m = STAMP_DATE_RX.search(text)
    if not STAMP_RX.search(text):
        return ["header has no '> Last revision:' line for --stamp to write"]
    if not m:
        return ["revision stamp not yet gate-written — run `python3 scripts/check_system_md.py --stamp`"]
    last, _ = git_last_change()
    try:
        age = (date.fromisoformat(last) - date.fromisoformat(m.group(1))).days
    except ValueError:
        return []
    if age > STALE_STAMP_DAYS:
        return [f"revision stamp {m.group(1)} is {age} days older than the last commit touching "
                f"SYSTEM.md ({last}) — run --stamp"]
    return []


def load_baselines() -> dict:
    if not LEDGER.exists():
        return {}
    return json.loads(LEDGER.read_text()).get("system_md_baselines", {})


def save_baselines(sizes: dict, total: int, nlines: int, cands: list[str], reason: str) -> None:
    data = json.loads(LEDGER.read_text()) if LEDGER.exists() else {}
    data["system_md_baselines"] = {
        "cap_bytes": CAP_BYTES, "total_bytes": total, "lines": nlines,
        "sections_bytes": sizes, "extraction_candidates": cands, "reason": reason,
    }
    LEDGER.write_text(json.dumps(data, indent=2) + "\n")


def main() -> int:
    argv = sys.argv[1:]
    text = SYSTEM_MD.read_text(encoding="utf-8")

    if "--stamp" in argv:
        d, sha = git_last_change()
        new = STAMP_RX.sub(lambda m: m.group(1) + f"{d} {sha} (gate-written)".rstrip(), text, count=1)
        if new == text:
            print("no '> Last revision:' line found to stamp" if not STAMP_RX.search(text)
                  else "stamp already current")
            return 0
        SYSTEM_MD.write_text(new, encoding="utf-8")
        print(f"stamp written: {d} {sha}")
        return 0

    lines = text.splitlines()
    secs = sections(lines)
    sizes = {name: nbytes(lines[a:b]) for name, a, b in secs}
    total = nbytes(lines)
    errs: list[str] = []
    warns: list[str] = []

    base = load_baselines()
    legacy_base = bool(base) and "total_bytes" not in base
    prev_cands: list[str] = base.get("extraction_candidates", [])

    # Byte cap, two thresholds; name the extraction candidate.
    ref = [(n, s) for n, s in sizes.items() if has(n, REFERENCE_HEADINGS) and n != "(preamble)"]
    cand = max(ref, key=lambda t: t[1])[0] if ref else None
    hint = (f" — extraction candidate: '{cand}' ({sizes[cand]:,} B) → docs/ with an index left behind"
            if cand else "")
    warned = total > CAP_BYTES * WARN_AT
    if total > CAP_BYTES:
        errs.append(f"SYSTEM.md is {total:,} B (> cap {CAP_BYTES:,} B; {len(lines)} lines). Groom or "
                    f"extract before feature work; the cap may be raised only immediately after a pass "
                    f"that failed to get under it, with --reason{hint}")
    elif total > CAP_BYTES * WARN_AT:
        warns.append(f"{total:,}/{CAP_BYTES:,} B ({total / CAP_BYTES:.0%}, {len(lines)} lines) — plan "
                     f"an extraction now, not under fail pressure{hint}")
    # The candidate is recorded, and escalates, only while the warning actually fires: an extracted
    # section stays the largest reference-shaped one left and must not re-name itself at the next baseline.
    if cand and warned and prev_cands[-2:] == [cand, cand]:
        errs.append(f"'{cand}' has been the extraction candidate across the last two baselines — "
                    f"a warning that persists is no longer advice; extract it or record why not")

    warns += check_long_lines(lines)

    for name, a, b in secs:
        body = lines[a:b]
        errs += check_accretion(name, body, a, "SYSTEM.md")
        if "deferred" in name.lower():
            e, w = check_deferred(body, a)
            errs += e
            warns += w

    budget_bytes = int(CAP_BYTES * SECTION_BUDGET)
    for name, s in sizes.items():
        if is_ledger(name) or name == "(preamble)":
            continue
        if s > budget_bytes:
            errs.append(f"'{name}' is {s:,} B (> {budget_bytes:,} B, {SECTION_BUDGET:.0%} of the cap). "
                        f"Groom it, or extract it to the reference tier under docs/ and leave an "
                        f"index — never split the orientation tier.")

    # The reference tier carries the same contract as the root file.
    ref_bytes = 0
    for pattern in REFERENCE_GLOBS:
        for f in sorted(ROOT.glob(pattern)):
            rlines = f.read_text(encoding="utf-8").splitlines()
            ref_bytes += nbytes(rlines)
            errs += check_accretion(f.name, rlines, 0, f.relative_to(ROOT).as_posix())

    e, w = check_enforcement(text)
    errs += e
    warns += w
    warns += check_stamp(text)

    if legacy_base:
        warns.append("baselines in .slopledger.json are line-based (v4 gate) — re-baseline with "
                     "--update-baselines --reason to start byte history")
    elif base.get("sections_bytes"):
        for name, s in sizes.items():
            b0 = base["sections_bytes"].get(name)
            if b0 and s > b0 * 1.25:
                warns.append(f"'{name}' is {s:,} B, >25% over its baseline of {b0:,} B. "
                             f"Integrate, don't append — or re-baseline with a reason.")

    if "--update-baselines" in argv:
        if "--reason" not in argv:
            print('FAIL: re-baselining requires --reason "<text>" — every movement of '
                  'a baseline needs an auditable justification', file=sys.stderr)
            return 1
        reason = argv[argv.index("--reason") + 1]
        hist = (prev_cands + [cand])[-3:] if (cand and warned) else prev_cands
        save_baselines(sizes, total, len(lines), hist, reason)
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

    print(f"check_system_md: OK ({LEVEL}) — {total:,}/{CAP_BYTES:,} B ({total / CAP_BYTES:.0%}), "
          f"{len(lines)} lines in the orientation tier, {ref_bytes:,} B in the reference tier, "
          f"{len(secs) - 1} sections, {len(warns)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
