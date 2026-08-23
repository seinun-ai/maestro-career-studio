"""Aggregations over persisted ats_scores rows (gaps_json + composites).

Each function pulls candidate rows with one filtered query, then aggregates the
nested JSONB gap arrays / joined composites in Python. Endpoints in
app/routers/explore.py wrap these and return plain JSON lists.
"""
from collections import Counter, defaultdict
from collections.abc import Iterator
from typing import Any

from sqlalchemy import Date, func, select
from sqlalchemy.orm import Session, aliased

from app.models.application import Application
from app.models.ats_score import AtsScore
from app.models.job import Job

LOW_SAMPLE_THRESHOLD = 5


def _low_sample(n: int) -> bool:
    return n < LOW_SAMPLE_THRESHOLD


def _apply_job_filters(stmt, role_category, level, employment_type):
    if role_category:
        stmt = stmt.where(Job.role_category == role_category)
    if level:
        stmt = stmt.where(Job.level == level)
    if employment_type:
        stmt = stmt.where(Job.employment_type == employment_type)
    return stmt


def _most_common(counter: Counter) -> Any:
    """Most-frequent value; alphabetical (by str) tie-break for determinism."""
    if not counter:
        return None
    return sorted(counter.items(), key=lambda kv: (-kv[1], str(kv[0])))[0][0]


def _best_base_gap_rows(
    db: Session, role_category, level, employment_type
) -> list[tuple[Any, dict]]:
    """(job_id, gaps_json) for the best-scoring base row per job.

    Every job is scored against every selectable base (score_all_bases), so
    pooling rows lets a weak secondary base manufacture gaps for skills the
    user's real resume covers — analytics must read only the base you would
    actually send. Base-phase rows are upsert singletons per (job, target),
    so "best" is a plain max-composite pick; ties break on target_id asc for
    deterministic reruns.
    """
    stmt = (
        select(
            AtsScore.job_id,
            AtsScore.target_id,
            AtsScore.composite,
            AtsScore.gaps_json,
        )
        .join(Job, Job.id == AtsScore.job_id)
        .where(
            AtsScore.phase == "base",
            AtsScore.target_type == "base_resume",
            AtsScore.gaps_json.is_not(None),
        )
    )
    stmt = _apply_job_filters(stmt, role_category, level, employment_type)

    best: dict[Any, tuple[tuple[float, str], dict]] = {}
    for job_id, target_id, composite, gaps in db.execute(stmt).all():
        # The SQL is_not(None) does NOT catch these: SQLAlchemy writes a Python
        # None into JSONB as the JSON scalar `null`, not SQL NULL, so such rows
        # survive the WHERE and would blow up gaps.get() below. Guard before the
        # pick, never after — a null-gaps row must not win and erase the job.
        if not gaps:
            continue
        key = (-float(composite), str(target_id))
        if job_id not in best or key < best[job_id][0]:
            best[job_id] = (key, gaps)
    return [(job_id, gaps) for job_id, (_, gaps) in best.items()]


def _skill_gap_occurrences(gaps: dict) -> Iterator[tuple[str | None, dict, str]]:
    """(category_key, gap, jd_skill) for the skill-kind gaps in one gaps_json.

    requirement-kind gaps (the weak_coverage category) are excluded: their
    jd_skill is a whole JD sentence, not a skill name, so it can neither be
    ranked as demand nor matched against the Career KB. weak_coverage keeps its
    own surface in the gap workflow.

    Shared by gap_frequency and explore_build_areas.build_areas so the two
    analytics surfaces cannot drift on what counts as a skill gap.
    """
    for category in gaps.get("categories") or []:
        cat_key = category.get("key")
        for gap in category.get("gaps") or []:
            if gap.get("kind") != "skill":
                continue
            skill = gap.get("jd_skill")
            if not skill:
                continue
            yield cat_key, gap, skill


def _is_hygiene_wording(cat_key: str | None, gap: dict) -> bool:
    """Whether this occurrence is a HYGIENE mirror_wording gap (zero headroom).

    gap_analysis._skill_gap stamps score_effect on mirror_wording gaps only:
    ``hygiene`` when the resume already matches the skill at FULL keyword credit
    (match_credit >= 1.0), ``adds_credit`` when it sits below full credit and the
    literal JD token would earn real credit. Both parts of the test matter — a
    bare score_effect check would misread a future category that reuses the
    field, and a bare category check would swallow the effective sibling.

    Shared by gap_frequency and explore_build_areas.build_areas so the two
    analytics surfaces can never drift on which occurrences count as demand.
    """
    return cat_key == "mirror_wording" and gap.get("score_effect") == "hygiene"


def gap_frequency(
    db: Session,
    role_category: str | None = None,
    level: str | None = None,
    employment_type: str | None = None,
    *,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """"What you keep lacking": skill-kind gaps across base-phase base_resume rows.

    n_jobs counts DISTINCT job_id; because the sweep reads only the
    best-scoring base per job (see _best_base_gap_rows), each job contributes
    at most one occurrence per skill.
    category / requirement_level are the most-common enclosing values.

    Only skill-kind gaps count (see _skill_gap_occurrences), and hygiene
    mirror_wording occurrences are skipped (see _is_hygiene_wording) — a skill
    that only ever gaps that way has no effective demand and gets no row.
    """
    job_ids: dict[str, set] = defaultdict(set)
    points: dict[str, list[float]] = defaultdict(list)
    categories: dict[str, Counter] = defaultdict(Counter)
    req_levels: dict[str, Counter] = defaultdict(Counter)

    for job_id, gaps in _best_base_gap_rows(
        db, role_category, level, employment_type
    ):
        for cat_key, gap, skill in _skill_gap_occurrences(gaps):
            # Hygiene wording occurrences are not demand: the resume already
            # matches the skill at FULL keyword credit, so mirroring the literal
            # JD token buys recruiter Boolean search and ZERO composite — there
            # is no headroom for a "what you keep lacking" list to report, and
            # _potential_points would still hand a skills-list-only row a
            # nonzero score that ranks it on both sort axes. The reason is score
            # movement, NOT that tailoring auto-resolves them:
            # kb_resolver._wording_auto_resolution keys on diagnostic.fix_hint
            # and never reads score_effect, so tailoring auto-mirrors BOTH kinds.
            # build_areas skips the same occurrences (shared predicate) and keeps
            # them as its wording-tier footnote; here they simply drop out.
            if _is_hygiene_wording(cat_key, gap):
                continue
            job_ids[skill].add(job_id)
            points[skill].append(float(gap.get("potential_points") or 0.0))
            if cat_key is not None:
                categories[skill][cat_key] += 1
            req_level = gap.get("requirement_level")
            if req_level is not None:
                req_levels[skill][req_level] += 1

    rows = [
        {
            "skill": skill,
            "n_jobs": len(ids),
            "avg_potential_points": round(
                sum(points[skill]) / len(points[skill]), 1
            )
            if points[skill]
            else 0.0,
            "category": _most_common(categories[skill]),
            "requirement_level": _most_common(req_levels[skill]),
            "low_sample": _low_sample(len(ids)),
        }
        for skill, ids in job_ids.items()
    ]
    rows.sort(
        key=lambda r: (-r["n_jobs"], -r["avg_potential_points"], r["skill"])
    )
    return rows[:limit]


def ats_over_time(
    db: Session,
    role_category: str | None = None,
    level: str | None = None,
    employment_type: str | None = None,
) -> list[dict[str, Any]]:
    """Weekly avg ATS composite + count, split by phase and Job.role_category."""
    week_start = func.date_trunc("week", AtsScore.created_at).cast(Date).label("week_start")
    stmt = (
        select(
            week_start,
            AtsScore.phase,
            Job.role_category,
            func.avg(AtsScore.composite).label("avg_composite"),
            func.count().label("n"),
        )
        .join(Job, Job.id == AtsScore.job_id)
        .where(Job.role_category.is_not(None))
        .group_by(week_start, AtsScore.phase, Job.role_category)
        .order_by(week_start, Job.role_category, AtsScore.phase)
    )
    stmt = _apply_job_filters(stmt, role_category, level, employment_type)

    return [
        {
            "week_start": row.week_start.isoformat(),
            "phase": row.phase,
            "role_category": row.role_category,
            "avg_composite": round(float(row.avg_composite), 1),
            "n": int(row.n),
            "low_sample": _low_sample(int(row.n)),
        }
        for row in db.execute(stmt).all()
    ]


def tailoring_lift(
    db: Session,
    role_category: str | None = None,
    level: str | None = None,
    employment_type: str | None = None,
) -> list[dict[str, Any]]:
    """Composite lift (tailored - base) per role, plus an overall "all" row.

    Joins the LATEST tailored AtsScore row per application to that application's
    base row (same job_id, target_id == application.base_resume, base phase).
    Re-tailoring appends a new tailored row under the same application_id, so we
    keep only the most recent (created_at desc, id desc — the same tiebreak as
    ats_score._latest_row). Applications missing either phase never join and are
    skipped.
    """
    # Rank tailored rows within each application; row_number 1 is the latest.
    ranked = (
        select(
            AtsScore.application_id.label("application_id"),
            AtsScore.composite.label("tailored_composite"),
            func.row_number()
            .over(
                partition_by=AtsScore.application_id,
                order_by=(AtsScore.created_at.desc(), AtsScore.id.desc()),
            )
            .label("rn"),
        )
        .where(AtsScore.phase == "tailored", AtsScore.application_id.is_not(None))
        .subquery()
    )

    base = aliased(AtsScore)
    stmt = (
        select(
            Job.role_category,
            base.composite.label("base_composite"),
            ranked.c.tailored_composite.label("tailored_composite"),
        )
        .select_from(ranked)
        .join(Application, Application.id == ranked.c.application_id)
        .join(
            base,
            (base.job_id == Application.job_id)
            & (base.target_id == Application.base_resume)
            & (base.phase == "base")
            & (base.target_type == "base_resume"),
        )
        .join(Job, Job.id == Application.job_id)
        .where(ranked.c.rn == 1)
    )
    stmt = _apply_job_filters(stmt, role_category, level, employment_type)

    per_role: dict[Any, list[tuple[float, float]]] = defaultdict(list)
    overall: list[tuple[float, float]] = []
    for role, base_composite, tailored_composite in db.execute(stmt).all():
        pair = (float(base_composite), float(tailored_composite))
        # Skip role-less jobs in the per-role bars (mirrors ats_over_time, and the
        # frontend types role_category as a non-null string); they still count in
        # the overall "all" row.
        if role is not None:
            per_role[role].append(pair)
        overall.append(pair)

    def _summarize(role_key: Any, pairs: list[tuple[float, float]]) -> dict[str, Any]:
        n = len(pairs)
        avg_base = sum(b for b, _ in pairs) / n
        avg_tailored = sum(t for _, t in pairs) / n
        avg_lift = sum(t - b for b, t in pairs) / n
        return {
            "role_category": role_key,
            "n": n,
            "avg_base": round(avg_base, 1),
            "avg_tailored": round(avg_tailored, 1),
            "avg_lift": round(avg_lift, 1),
            "low_sample": _low_sample(n),
        }

    rows = [
        _summarize(role, pairs)
        for role, pairs in sorted(per_role.items(), key=lambda kv: str(kv[0]))
    ]
    if overall:
        rows.append(_summarize("all", overall))
    return rows
