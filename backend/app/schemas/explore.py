from typing import Any, Literal

from pydantic import BaseModel


class TopSkillRow(BaseModel):
    skill_name: str
    skill_category: str | None = None
    n: int
    n_required: int
    n_preferred: int
    n_mentioned: int
    pct_jobs: float
    rank: int
    rank_percentile: float
    tier: Literal["top", "below"]
    bucket: Literal["core", "preferred_top", "below_threshold"]


class TopSkillsMeta(BaseModel):
    total_jobs: int
    total_skills: int
    top_count: int
    top_tier_fraction: float


class TopSkillsResponse(BaseModel):
    meta: TopSkillsMeta
    top: list[TopSkillRow]
    rest: list[TopSkillRow]

    @classmethod
    def from_classified(
        cls,
        classified: list[dict[str, Any]],
        *,
        total_jobs: int,
        top_tier_fraction: float,
        limit: int,
    ) -> "TopSkillsResponse":
        top_rows = sorted(
            (row for row in classified if row["tier"] == "top"),
            key=lambda row: row["rank"],
        )
        rest_rows = sorted(
            (row for row in classified if row["tier"] == "below"),
            key=lambda row: row["rank"],
        )
        return cls(
            meta=TopSkillsMeta(
                total_jobs=total_jobs,
                total_skills=len(classified),
                top_count=len(top_rows),
                top_tier_fraction=top_tier_fraction,
            ),
            top=[TopSkillRow.model_validate(row) for row in top_rows[:limit]],
            rest=[TopSkillRow.model_validate(row) for row in rest_rows[:limit]],
        )


class CountRow(BaseModel):
    key: str
    count: int


class SkillCountRow(BaseModel):
    skill_name: str
    n: int


class SalaryByRoleRow(BaseModel):
    role_category: str
    currency: str | None = None
    n: int
    avg_min: float | None = None
    avg_max: float | None = None


class WorkAuthBreakdown(BaseModel):
    opt: list[CountRow]
    sponsorship: list[CountRow]


class OverviewMeta(BaseModel):
    total_jobs: int
    since: str | None = None
    role_category_count: int
    salary_year_avg_min: float | None = None
    salary_year_avg_max: float | None = None
    salary_year_currency: str | None = None
    salary_mixed_currencies: bool = False
    jobs_with_salary: int = 0
    jobs_without_salary: int = 0


class OverviewSignal(BaseModel):
    title: str
    detail: str


class ExploreOverviewResponse(BaseModel):
    meta: OverviewMeta
    role_mix: list[CountRow]
    level_breakdown: list[CountRow]
    work_mode: list[CountRow]
    top_required_skills: list[SkillCountRow]
    salary_by_role: list[SalaryByRoleRow]
    salary_by_currency: list[CountRow] = []
    locations: list[CountRow]
    countries: list[CountRow] = []
    work_auth: WorkAuthBreakdown
    signals: list[OverviewSignal]
