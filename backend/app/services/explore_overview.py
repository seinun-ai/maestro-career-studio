from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session

from app.models.job import Job
from app.models.job_skill import JobSkill
from app.schemas.job_extraction import level_key, work_mode_key
from app.services import countries, fx_rates, money, money_settings, role_categories

# A role's yearly pay shows only from this many jobs that list it (converted into your currency);
# fewer are named under `hidden_roles` with their count.
MIN_ROLE_JOBS = 5


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
        # Any spelling of a country filters on its code ("Germany" and "DE" are one filter).
        stmt = stmt.where(Job.country_code == (countries.normalize(filters.country) or filters.country))
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


def _count_by_key(db, columns, to_key, filters: JobFilters, *, missing: str) -> list[dict[str, Any]]:
    """Counts per normalised key: one bar per value however it was spelled. Captures store keys,
    and this folds any row written another way ("Onsite", "USA") into its key, `missing` when
    there is none."""
    stmt = _apply(select(*columns, func.count()).select_from(Job), filters).group_by(*columns)
    counts: Counter[str] = Counter()
    for *values, n in db.execute(stmt).all():
        counts[to_key(*values) or missing] += int(n)
    return [{"key": k, "count": c} for k, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def _country_key(code: str | None, country: str | None) -> str | None:
    return code or countries.for_job(country, None)


def compute_signals(o: dict[str, Any]) -> list[dict[str, Any]]:
    """The first five insights; `candidate_signals` is every one that fires."""
    return candidate_signals(o)[:5]


def _jobs(n: int) -> str:
    """"1 job", "3 jobs": a count and its noun agree (appendix D §1)."""
    return f"{n} {'job' if n == 1 else 'jobs'}"


def _best_paying_signal(o: dict[str, Any]) -> dict[str, Any] | None:
    """The best-paying role, by the average top of its pay range in your currency.

    Pay is compared only once converted into the home currency (`pay_by_role`: ECB reference
    rates; a job whose currency has no rate is left out, never compared as posted), and only
    among the roles that show (enough jobs list pay). The signal carries the figure as a number
    with its currency; the browser words it (`lib/money.ts`), with "≈" when any of it was
    converted."""
    pay = o.get("pay_by_role") or {}
    # Reserved buckets are not a role: "Best-paying role: Unknown" says nothing.
    paid = [
        r for r in pay.get("roles") or []
        if r.get("avg_max") and r["role_category"] not in role_categories.RESERVED
    ]
    if not paid:
        return None
    best = max(paid, key=lambda r: r["avg_max"])
    return {
        "title": f"Best-paying role: {role_categories.label_for(best['role_category'])}",
        "detail": (
            f"Average top of the pay range, from {_jobs(best['n'])} that "
            f"{'lists' if best['n'] == 1 else 'list'} pay."
        ),
        "currency": pay.get("currency"),
        "amount": best["avg_max"],
        "converted": bool(best.get("converted_count")),
    }


def candidate_signals(o: dict[str, Any]) -> list[dict[str, Any]]:
    total = o["meta"]["total_jobs"]
    if not total:
        return []
    signals: list[dict[str, Any]] = []

    # No OPT signal: the Job market tab's own tile shows that share, and `work_auth.opt` carries
    # the counts for every other reader. A signal said it a second time on the same screen.

    if o["locations"]:
        top = o["locations"][0]
        signals.append({
            "title": f"Most common location: {top['key']} ({_jobs(top['count'])})",
            "detail": "More jobs list this location than any other.",
        })

    if o["top_required_skills"]:
        s = o["top_required_skills"][0]
        signals.append({
            # Skill names are stored casefolded, so the name never leads the title.
            "title": f"Most required skill: {s['skill_name']} ({round(s['n'] / total * 100)}% of jobs)",
            "detail": f"Required in {s['n']} of {_jobs(total)}, more than any other skill.",
        })

    best_paying = _best_paying_signal(o)
    if best_paying:
        signals.append(best_paying)

    without = o["meta"].get("jobs_without_salary") or 0
    if without:
        signals.append({
            "title": f"{round(without / total * 100)}% of jobs don't list pay",
            "detail": (
                f"{without} of {total} leave pay out. That is common, so it is not a red flag."
            ),
        })

    wm = {r["key"]: r["count"] for r in o["work_mode"]}
    remote = wm.get("remote", 0)
    rpct = round(remote / total * 100)
    if rpct < 20:
        signals.append({
            "title": f"Remote roles are scarce ({rpct}%)",
            "detail": f"Only {remote} of {_jobs(total)} {'is' if remote == 1 else 'are'} remote.",
        })

    return signals


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


def _average(values: list[Decimal]) -> float | None:
    return float(sum(values) / len(values)) if values else None


def _pay_by_role(db, filters: JobFilters, home: str, rates: dict[str, Any] | None) -> dict[str, Any]:
    """Yearly pay by role in the home currency (owner decision D8).

    Every yearly job that lists a top of its range is converted into `home` on the ECB
    reference rates (`money.convert`); a job whose currency has no rate, or that names none, is
    counted in `unconverted` and left out, never compared as posted. A role shows from
    `MIN_ROLE_JOBS` converted jobs; fewer are listed in `hidden_roles` with their count. The
    payload carries numbers only; the browser words them (`lib/money.ts`).
    """
    rc_key = func.coalesce(Job.role_category, "unknown")
    rows = db.execute(
        _apply(
            select(rc_key, Job.salary_currency, Job.salary_min, Job.salary_max)
            .select_from(Job)
            .where(Job.salary_period == "year", Job.salary_max.is_not(None)),
            filters,
        )
    ).all()
    by_role: dict[str, list[tuple[Decimal | None, Decimal, str]]] = defaultdict(list)
    unconverted = 0
    for role, currency, low, high in rows:
        code = currency.strip().upper() if currency else None
        top = money.convert(Decimal(str(high)), code, home, rates) if code else None
        if top is None:
            unconverted += 1
            continue
        bottom = money.convert(Decimal(str(low)), code, home, rates) if low is not None else None
        by_role[str(role)].append((bottom, top, code))

    shown, hidden = [], []
    converted: Counter[str] = Counter()
    for role, jobs in by_role.items():
        posted = [code for *_, code in jobs]
        if len(jobs) < MIN_ROLE_JOBS:
            hidden.append({"role_category": role, "n": len(jobs)})
            continue
        converted.update(code for code in posted if code != home)
        shown.append({
            "role_category": role,
            "n": len(jobs),
            "avg_min": _average([low for low, _top, _code in jobs if low is not None]),
            "avg_max": _average([top for _low, top, _code in jobs]),
            "converted_count": sum(1 for code in posted if code != home),
            "posted_currencies": sorted(set(posted)),
        })
    shown.sort(key=lambda r: (-r["avg_max"], r["role_category"]))
    hidden.sort(key=lambda r: (-r["n"], r["role_category"]))
    return {
        "currency": home,
        "rate_date": rates.get("date") if rates and converted else None,
        "min_jobs": MIN_ROLE_JOBS,
        "roles": shown,
        "hidden_roles": hidden,
        "converted_count": sum(converted.values()),
        "posted_currencies": [{"key": k, "count": n} for k, n in
                              sorted(converted.items(), key=lambda kv: (-kv[1], kv[0]))],
        "unconverted": unconverted,
    }


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
    overview = {
        **block,
        "role_mix": _count_by(db, Job.role_category, filters, coalesce="unknown"),
        "level_breakdown": _count_by_key(db, (Job.level,), level_key, filters, missing="unstated"),
        "work_mode": _count_by_key(db, (Job.work_mode,), work_mode_key, filters, missing="unstated"),
        "top_required_skills": top_required_skills,
        "pay_by_role": _pay_by_role(db, filters, money_settings.home_currency(db), fx_rates.current(db)),
        "locations": locations,
        # ISO codes; "unknown" when a job names no one country (the web app says "Not stated").
        "countries": _count_by_key(
            db, (Job.country_code, Job.country), _country_key, filters, missing="unknown"
        ),
        "work_auth": {
            "opt": _count_by(db, Job.opt_accepted, filters),
            "sponsorship": _count_by(db, Job.work_authorization, filters),
        },
        "signals": [],
    }
    overview["signals"] = compute_signals(overview)
    return overview
