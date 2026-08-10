"""Before/after calibration harness for the ATS engine.

`ats_snapshot.py` prints a human-readable ranking table; this script writes a
MACHINE-readable snapshot and diffs two of them, so a scoring change can be
measured instead of argued about.

Usage (from backend/, dev DB running):
    DATABASE_URL=postgresql://app:app@127.0.0.1:55432/maestro_cs \\
        python -m scripts.ats_calibration snapshot before.json
    # ... make the scoring change ...
    DATABASE_URL=... python -m scripts.ats_calibration snapshot after.json
    python -m scripts.ats_calibration diff before.json after.json
"""
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

# Behavioral row fields only. Deliberately the SAME set test_golden.py asserts
# exactly (plus contribution), so a calibration diff and the golden test agree on
# what "behavior changed" means.
_ROW_FIELDS = ("matched", "match_form", "placement", "fix_hint", "contribution")

# Pin the clock. score_resume defaults as_of to date.today(), so an unpinned
# snapshot would drift with the calendar via recency decay and report scoring
# changes that are really just the passage of time.
CALIBRATION_AS_OF = date(2026, 7, 1)


@dataclass
class DriftReport:
    pairs_compared: int = 0
    composite_deltas: list[tuple[str, float]] = field(default_factory=list)
    newly_matched: list[tuple[str, str]] = field(default_factory=list)
    newly_absent: list[tuple[str, str]] = field(default_factory=list)
    # Rows whose contribution DROPPED. This is the non-regression gate: enabling a
    # new evidence channel must never lower an existing row (the semantic stage
    # picks a single argmax, so a short new chunk can steal attribution from a
    # dated bullet and demote that row's placement tier).
    contribution_regressions: list[tuple[str, str, float, float]] = field(default_factory=list)
    # Drops grouped by "match_form before->after". A changed form is usually a
    # DELIBERATE reclassification (fuzzy->broader when a scoring rule is retuned);
    # a drop with the form UNCHANGED means the same kind of match silently got
    # weaker, which is the shape a real regression takes. Without this split, an
    # intended downgrade buries a genuine bug in the same total.
    drops_by_transition: dict[str, int] = field(default_factory=dict)


def diff_snapshots(before: dict, after: dict) -> DriftReport:
    before_pairs = before.get("pairs") or {}
    after_pairs = after.get("pairs") or {}
    common = sorted(set(before_pairs) & set(after_pairs))

    report = DriftReport(pairs_compared=len(common))
    for key in common:
        old, new = before_pairs[key], after_pairs[key]
        delta = round(new["composite"] - old["composite"], 4)
        if delta:
            report.composite_deltas.append((key, delta))

        old_rows = old.get("rows") or {}
        new_rows = new.get("rows") or {}
        for skill in sorted(set(old_rows) & set(new_rows)):
            was, now = old_rows[skill], new_rows[skill]
            if not was["matched"] and now["matched"]:
                report.newly_matched.append((key, skill))
            elif was["matched"] and not now["matched"]:
                report.newly_absent.append((key, skill))
            if now["contribution"] < was["contribution"]:
                report.contribution_regressions.append(
                    (key, skill, was["contribution"], now["contribution"])
                )
                transition = f"{was['match_form']}->{now['match_form']}"
                report.drops_by_transition[transition] = (
                    report.drops_by_transition.get(transition, 0) + 1
                )
    return report


@dataclass
class Violation:
    mutation: str
    before: float
    after: float
    detail: str


def _absent_skills(result: Any) -> list[str]:
    return [r["jd_skill"] for r in result.skill_table if not r["matched"]]


def _skills_at(result: Any, placement: str) -> list[str]:
    return [r["jd_skill"] for r in result.skill_table if r.get("placement") == placement]


def add_certification(resume: dict, result: Any) -> tuple[dict, str] | None:
    """Model the user holding a credential the JD names and adding it.

    Truthful BY ASSUMPTION — the point is not that they hold it, but that IF
    they do, recording it must not cost them. Targets a skill the engine
    currently reports absent, which is the exact row the gap builder would tell
    them to act on.
    """
    absent = _absent_skills(result)
    if not absent:
        return None
    mutated = json.loads(json.dumps(resume))
    mutated.setdefault("certifications", []).append(absent[0])
    return mutated, f"added certification {absent[0]!r}"


def dual_place_skill(resume: dict, result: Any) -> tuple[dict, str] | None:
    """Surface a skill an existing DATED entry already evidences into the skills
    list. This is the most common fix the gap builder emits (`dual_place`), so if
    it ever fails to pay, the product is recommending a losing move."""
    candidates = _skills_at(result, "experience_only") or _skills_at(result, "undated_only")
    if not candidates:
        return None
    mutated = json.loads(json.dumps(resume))
    groups = mutated.get("skills") or []
    if not groups:
        mutated["skills"] = [{"category": "Skills", "items": [candidates[0]]}]
    else:
        groups[0].setdefault("items", []).append(candidates[0])
    return mutated, f"surfaced {candidates[0]!r} into the skills list"


def add_uncorroborated_skill(resume: dict, result: Any) -> tuple[dict, str] | None:
    """NOT monotone, on purpose — the L5 stuffing lint is supposed to punish
    padding the skills list with terms no entry backs up. Excluded from
    MONOTONE_MUTATIONS; kept as the non-vacuity control for the checker."""
    mutated = json.loads(json.dumps(resume))
    groups = mutated.get("skills") or []
    filler = "Fortran"
    if not groups:
        mutated["skills"] = [{"category": "Skills", "items": [filler]}]
    else:
        groups[0].setdefault("items", []).append(filler)
    return mutated, f"padded the skills list with {filler!r}"


# Mutations that add ONLY true information through a channel with no honest
# reason to cost points. A drop here is a direction error: the product told the
# user that recording something true made them a worse candidate.
MONOTONE_MUTATIONS = {
    "add_certification": add_certification,
    "dual_place_skill": dual_place_skill,
}


def check_monotonicity(
    resume: dict, jd: dict, *, as_of: date, mutations: dict | None = None
) -> list[Violation]:
    """Apply each mutation and report every composite DROP."""
    from app.services.ats import score_resume

    mutations = MONOTONE_MUTATIONS if mutations is None else mutations
    baseline = score_resume(resume, jd, as_of=as_of)
    violations: list[Violation] = []
    for name, mutate in mutations.items():
        applied = mutate(resume, baseline)
        if applied is None:  # nothing to mutate on this pair
            continue
        mutated, detail = applied
        after = score_resume(mutated, jd, as_of=as_of).composite
        if after < baseline.composite:
            violations.append(
                Violation(mutation=name, before=baseline.composite, after=after, detail=detail)
            )
    return violations


def pair_from_result(result: Any) -> dict:
    """One snapshot entry from an AtsResult. Rows are keyed by jd_skill so a
    reordered skill_table is not a spurious diff."""
    return {
        "composite": result.composite,
        "subscores": dict(result.subscores),
        "rows": {
            row["jd_skill"]: {field_name: row[field_name] for field_name in _ROW_FIELDS}
            for row in result.skill_table
        },
    }


def summarize(report: DriftReport) -> str:
    moved = report.composite_deltas
    lines = [
        f"{report.pairs_compared} pairs compared, {len(moved)} moved",
    ]
    if moved:
        deltas = [d for _, d in moved]
        lines.append(
            f"  composite delta: min {min(deltas):+.1f}  max {max(deltas):+.1f}  "
            f"mean {sum(deltas) / len(deltas):+.2f}"
        )
        for key, delta in sorted(moved, key=lambda kv: -abs(kv[1]))[:10]:
            lines.append(f"    {delta:+7.1f}  {key}")
    lines.append(f"  {len(report.newly_matched)} newly matched, "
                 f"{len(report.newly_absent)} newly absent")
    for key, skill in report.newly_matched[:10]:
        lines.append(f"    + {skill}  ({key})")
    for key, skill in report.newly_absent[:10]:
        lines.append(f"    - {skill}  ({key})")
    if report.contribution_regressions:
        lines.append(f"  {len(report.contribution_regressions)} row(s) lost contribution:")
        for transition, count in sorted(
            report.drops_by_transition.items(), key=lambda kv: -kv[1]
        ):
            before_form, after_form = transition.split("->", 1)
            # same form, less credit => nothing explains it => suspect a bug
            label = "REGRESSION?" if before_form == after_form else "reclassified"
            lines.append(f"    {count:4d}  {transition:24s} {label}")
        for key, skill, was, now in report.contribution_regressions[:5]:
            lines.append(f"      e.g. {skill}: {was} -> {now}  ({key})")
    return "\n".join(lines)


def build_snapshot() -> dict:
    """Score every active base resume against every job with an extraction."""
    from app.db import SessionLocal
    from app.models.job import Job
    from app.services.ats import score_resume
    from app.services.ats.config import ENGINE_VERSION, load_config
    from app.services.base_resume_data import active_base_resume_slugs, load_base_resume
    from sqlalchemy import select

    pairs: dict[str, dict] = {}
    skipped: list[str] = []
    with SessionLocal() as session:
        jobs = list(session.scalars(select(Job).where(Job.extracted_json.isnot(None))))
        resumes: dict[str, dict] = {}
        for slug in active_base_resume_slugs(session):
            try:
                resumes[slug] = load_base_resume(slug, session)
            except ValueError as exc:  # active row, no data file on this checkout
                skipped.append(f"{slug}: {exc}")
        for job in jobs:
            for slug, resume in resumes.items():
                try:
                    result = score_resume(
                        resume, job.extracted_json, as_of=CALIBRATION_AS_OF
                    )
                except ValueError as exc:  # job has no extracted skills
                    skipped.append(f"{job.id}: {exc}")
                    continue
                pairs[f"{job.id}|{slug}"] = pair_from_result(result)
    return {
        "engine_version": ENGINE_VERSION,
        "config_version": load_config().version,
        "as_of": CALIBRATION_AS_OF.isoformat(),
        # Coverage is reported, never silently truncated: a snapshot that skipped
        # half the corpus must not read as "everything scored".
        "jobs": len(jobs),
        "resumes": len(resumes),
        "skipped": skipped,
        "pairs": pairs,
    }


def run_monotonicity() -> tuple[int, list[str]]:
    """Run the monotonicity property over every corpus (resume, job) pair.

    The hermetic test in tests/test_ats_monotonicity.py pins the property on
    fixtures; this runs it on real resumes against real postings, where the
    mutations land on evidence the fixtures do not have.
    """
    from app.db import SessionLocal
    from app.models.job import Job
    from app.services.base_resume_data import active_base_resume_slugs, load_base_resume
    from sqlalchemy import select

    checked, lines = 0, []
    with SessionLocal() as session:
        jobs = list(session.scalars(select(Job).where(Job.extracted_json.isnot(None))))
        resumes = {}
        for slug in active_base_resume_slugs(session):
            try:
                resumes[slug] = load_base_resume(slug, session)
            except ValueError:
                continue
        for job in jobs:
            for slug, resume in resumes.items():
                try:
                    violations = check_monotonicity(
                        resume, job.extracted_json, as_of=CALIBRATION_AS_OF
                    )
                except ValueError:  # job has no extracted skills
                    continue
                checked += 1
                for v in violations:
                    lines.append(
                        f"  {v.before:.1f} -> {v.after:.1f}  [{v.mutation}] {v.detail}"
                        f"  ({job.id}|{slug})"
                    )
    return checked, lines


def main() -> int:
    args = sys.argv[1:]
    if len(args) == 1 and args[0] == "monotonicity":
        checked, violations = run_monotonicity()
        print(f"{checked} pairs checked, {len(violations)} violation(s)")
        for line in violations:
            print(line)
        return 1 if violations else 0
    if len(args) == 2 and args[0] == "snapshot":
        snapshot = build_snapshot()
        Path(args[1]).write_text(json.dumps(snapshot, indent=1), encoding="utf-8")
        print(f"wrote {len(snapshot['pairs'])} pairs to {args[1]} "
              f"({snapshot['engine_version']} / {snapshot['config_version']})")
        return 0
    if len(args) == 3 and args[0] == "diff":
        before = json.loads(Path(args[1]).read_text(encoding="utf-8"))
        after = json.loads(Path(args[2]).read_text(encoding="utf-8"))
        print(f"{before.get('engine_version')} / {before.get('config_version')}"
              f"  ->  {after.get('engine_version')} / {after.get('config_version')}")
        report = diff_snapshots(before, after)
        print(summarize(report))
        # Non-zero only for SUSPECTED regressions (same match_form, less credit).
        # A deliberate reclassification is expected output, not a failure.
        suspect = any(
            transition.split("->")[0] == transition.split("->")[1]
            for transition in report.drops_by_transition
        )
        return 1 if suspect else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
