from dataclasses import dataclass
from typing import Any

from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session

from app.models.job import Job
from app.models.job_skill import JobSkill


@dataclass(frozen=True, slots=True)
class JobFilters:
    role_category: str | None = None
    level: str | None = None
    employment_type: str | None = None
    country: str | None = None
    salary_currency: str | None = None


def _apply(stmt, filters: JobFilters):
    if filters.role_category:
        stmt = stmt.where(Job.role_category == filters.role_category)
    if filters.level:
        stmt = stmt.where(Job.level == filters.level)
    if filters.employment_type:
        stmt = stmt.where(Job.employment_type == filters.employment_type)
    if filters.country:
        stmt = stmt.where(Job.country == filters.country)
    if filters.salary_currency:
        stmt = stmt.where(Job.salary_currency == filters.salary_currency)
    return stmt


def _count_by(db, column, filters: JobFilters, *, coalesce="unstated"):
    key = func.coalesce(column, coalesce)
    stmt = _apply(
        select(key.label("key"), func.count().label("count")).select_from(Job),
        filters,
    ).group_by(key).order_by(func.count().desc(), key)
    return [{"key": str(k), "count": int(c)} for k, c in db.execute(stmt).all()]


def compute_signals(o: dict[str, Any]) -> list[dict[str, str]]:
    total = o["meta"]["total_jobs"]
    if not total:
        return []
    signals: list[dict[str, str]] = []

    opt = {r["key"]: r["count"] for r in o["work_auth"]["opt"]}
    accept = opt.get("yes", 0) + opt.get("stem_opt_ok", 0)
    signals.append({
        "title": f"{round(accept / total * 100)}% of JDs explicitly accept OPT",
        "detail": f"{accept} of {total} say yes or STEM-OPT; the rest are 'no' or unstated.",
    })

    if o["locations"]:
        top = o["locations"][0]
        signals.append({
            "title": f"Top location: {top['key']} ({top['count']})",
            "detail": "Highest concentration of JDs by location.",
        })

    if o["top_required_skills"]:
        s = o["top_required_skills"][0]
        signals.append({
            "title": f"{s['skill_name']} required in {round(s['n'] / total * 100)}% of JDs",
            "detail": f"Most-required skill — {s['n']} of {total} JDs.",
        })

    paid = [r for r in o["salary_by_role"] if r.get("avg_max")]
    if paid:
        best = max(paid, key=lambda r: r["avg_max"])
        cur = best.get("currency") or o["meta"].get("salary_year_currency")
        cur_bit = f" {cur}" if cur else ""
        signals.append({
            "title": f"Best-paying track: {best['role_category']}",
            "detail": (
                f"~{round(best['avg_max'] / 1000)}k{cur_bit} avg max across "
                f"{best['n']} disclosed JDs."
            ),
        })

    without = o["meta"].get("jobs_without_salary") or 0
    if without:
        signals.append({
            "title": f"{round(without / total * 100)}% of JDs state no salary",
            "detail": (
                f"{without} of {total} omit pay numbers — normal "
                "(~40%+ US / ~88% DE; IL may only hyperlink a pay page)."
            ),
        })

    wm = {r["key"]: r["count"] for r in o["work_mode"]}
    remote = wm.get("remote", 0)
    rpct = round(remote / total * 100)
    if rpct < 20:
        signals.append({
            "title": f"Remote roles are scarce ({rpct}%)",
            "detail": f"Only {remote} of {total} JDs are remote.",
        })

    return signals[:5]


def _salary_year_stats(db, filters: JobFilters):
    has_salary = or_(Job.salary_min.is_not(None), Job.salary_max.is_not(None))
    currency_rows = [
        {"key": (c or "unknown"), "count": int(n)}
        for c, n in db.execute(
            _apply(
                select(Job.salary_currency, func.count())
                .select_from(Job)
                .where(Job.salary_period == "year", has_salary)
                .group_by(Job.salary_currency),
                filters,
            )
        ).all()
    ]
    distinct = sorted({r["key"] for r in currency_rows if r["key"] != "unknown"})
    mixed = len(distinct) > 1
    year_currency = None
    avg_min = avg_max = None
    if not mixed:
        year_currency = distinct[0] if distinct else None
        avg_min, avg_max = db.execute(
            _apply(
                select(func.avg(Job.salary_min), func.avg(Job.salary_max))
                .select_from(Job)
                .where(Job.salary_period == "year"),
                filters,
            )
        ).one()
    return currency_rows, mixed, year_currency, avg_min, avg_max


def _salary_by_role_rows(db, filters: JobFilters) -> list[dict]:
    rc_key = func.coalesce(Job.role_category, "unknown")
    cur_key = func.coalesce(Job.salary_currency, "unknown")
    rows = db.execute(
        _apply(
            select(
                rc_key.label("rc"),
                cur_key.label("cur"),
                func.count().label("n"),
                func.avg(Job.salary_min),
                func.avg(Job.salary_max),
            )
            .select_from(Job)
            .where(Job.salary_period == "year", Job.salary_max.is_not(None)),
            filters,
        ).group_by(rc_key, cur_key).order_by(func.avg(Job.salary_max).desc(), rc_key, cur_key)
    ).all()
    return [
        {
            "role_category": rc,
            "currency": None if cur == "unknown" else cur,
            "n": int(n),
            "avg_min": float(amin) if amin is not None else None,
            "avg_max": float(amax) if amax is not None else None,
        }
        for rc, cur, n, amin, amax in rows
    ]


def _overview_meta(db, filters: JobFilters) -> dict[str, Any]:
    total = int(db.scalar(_apply(select(func.count()).select_from(Job), filters)) or 0)
    since_dt = db.scalar(_apply(select(func.min(Job.created_at)).select_from(Job), filters))
    role_cat_count = int(
        db.scalar(
            _apply(
                select(func.count(distinct(Job.role_category)))
                .select_from(Job)
                .where(Job.role_category.is_not(None)),
                filters,
            )
        )
        or 0
    )
    has_salary = or_(Job.salary_min.is_not(None), Job.salary_max.is_not(None))
    jobs_with = int(
        db.scalar(_apply(select(func.count()).select_from(Job).where(has_salary), filters)) or 0
    )
    currency_rows, mixed, year_currency, avg_min, avg_max = _salary_year_stats(db, filters)
    return {
        "meta": {
            "total_jobs": total,
            "since": since_dt.isoformat() if since_dt else None,
            "role_category_count": role_cat_count,
            "salary_year_avg_min": float(avg_min) if avg_min is not None else None,
            "salary_year_avg_max": float(avg_max) if avg_max is not None else None,
            "salary_year_currency": year_currency,
            "salary_mixed_currencies": mixed,
            "jobs_with_salary": jobs_with,
            "jobs_without_salary": total - jobs_with,
        },
        "salary_by_currency": currency_rows,
    }


def _top_skills_and_locations(db, filters: JobFilters, top_n_skills: int, top_n_locations: int):
    top_required_skills = [
        {"skill_name": n, "n": int(c)}
        for n, c in db.execute(
            _apply(
                select(JobSkill.skill_name, func.count(distinct(JobSkill.job_id)).label("n"))
                .join(Job, Job.id == JobSkill.job_id)
                .where(JobSkill.requirement_level == "required")
                .group_by(JobSkill.skill_name)
                .order_by(func.count(distinct(JobSkill.job_id)).desc(), JobSkill.skill_name),
                filters,
            ).limit(top_n_skills)
        ).all()
    ]
    loc_key = func.coalesce(Job.state, Job.city, Job.country)
    locations = [
        {"key": str(k), "count": int(c)}
        for k, c in db.execute(
            _apply(
                select(loc_key.label("key"), func.count().label("count"))
                .select_from(Job)
                .where(loc_key.is_not(None)),
                filters,
            ).group_by(loc_key).order_by(func.count().desc(), loc_key).limit(top_n_locations)
        ).all()
        if k
    ]
    return top_required_skills, locations


def build_overview(
    db: Session,
    filters: JobFilters | None = None,
    *,
    top_n_skills: int = 10,
    top_n_locations: int = 8,
) -> dict[str, Any]:
    filters = filters or JobFilters()
    block = _overview_meta(db, filters)
    top_required_skills, locations = _top_skills_and_locations(
        db, filters, top_n_skills, top_n_locations
    )
    countries = [
        r
        for r in _count_by(db, Job.country, filters, coalesce="unknown")
        if r["key"] != "unknown" or r["count"] > 0
    ]
    overview = {
        **block,
        "role_mix": _count_by(db, Job.role_category, filters, coalesce="unknown"),
        "level_breakdown": _count_by(db, Job.level, filters),
        "work_mode": _count_by(db, Job.work_mode, filters),
        "top_required_skills": top_required_skills,
        "salary_by_role": _salary_by_role_rows(db, filters),
        "locations": locations,
        "countries": countries,
        "work_auth": {
            "opt": _count_by(db, Job.opt_accepted, filters),
            "sponsorship": _count_by(db, Job.work_authorization, filters),
        },
        "signals": [],
    }
    overview["signals"] = compute_signals(overview)
    return overview
