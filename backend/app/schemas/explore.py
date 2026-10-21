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
    low_sample: bool = False


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


class PayByRoleRow(BaseModel):
    """One role's yearly pay, in `PayByRole.currency`: `n` jobs that list it, `converted_count`
    of them posted in another currency (shown with "≈"), the currencies they were posted in."""

    role_category: str
    n: int
    avg_min: float | None = None
    avg_max: float | None = None
    converted_count: int = 0
    posted_currencies: list[str] = []


class HiddenRole(BaseModel):
    role_category: str
    n: int


class PayByRole(BaseModel):
    """Yearly pay by role in your home currency (`explore_overview._pay_by_role`): numbers only,
    worded by the browser (`lib/money.ts`). `rate_date` is the ECB rate date when any pay was
    converted; `posted_currencies` counts the converted jobs by the currency they were posted in;
    `unconverted` counts jobs left out because their currency has no rate or they name none."""

    currency: str
    rate_date: str | None = None
    min_jobs: int
    roles: list[PayByRoleRow]
    hidden_roles: list[HiddenRole] = []
    converted_count: int = 0
    posted_currencies: list[CountRow] = []
    unconverted: int = 0


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
    # Set on a signal that names pay: the figure as a number in `currency` (your home currency),
    # worded by the browser, and whether any of it was converted (shown with "≈").
    currency: str | None = None
    amount: float | None = None
    converted: bool = False


class ExploreOverviewResponse(BaseModel):
    meta: OverviewMeta
    role_mix: list[CountRow]
    level_breakdown: list[CountRow]
    work_mode: list[CountRow]
    top_required_skills: list[SkillCountRow]
    pay_by_role: PayByRole
    salary_by_currency: list[CountRow] = []
    locations: list[CountRow]
    countries: list[CountRow] = []
    work_auth: WorkAuthBreakdown
    signals: list[OverviewSignal]
