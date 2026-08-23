import math
from typing import Any, Literal

SkillBucket = Literal["core", "preferred_top", "below_threshold"]
SkillTier = Literal["top", "below"]

TOP_TIER_FRACTION = 0.30


def _is_core(n: int, n_required: int, n_preferred: int) -> bool:
    if n_required <= 0:
        return False
    if n_required >= n_preferred:
        return True
    return n_required / n >= 0.5


def classify_skill_rows(
    rows: list[dict[str, Any]],
    *,
    total_jobs: int,
    top_tier_fraction: float = TOP_TIER_FRACTION,
) -> list[dict[str, Any]]:
    if not rows:
        return []

    sorted_rows = sorted(rows, key=lambda row: (-row["n"], row["skill_name"]))
    total_skills = len(sorted_rows)
    top_count = max(1, math.ceil(total_skills * top_tier_fraction))

    classified: list[dict[str, Any]] = []
    for rank, row in enumerate(sorted_rows, start=1):
        in_top_tier = rank <= top_count
        n = row["n"]
        n_required = row.get("n_required", 0)
        n_preferred = row.get("n_preferred", 0)
        n_mentioned = row.get("n_mentioned", 0)

        if in_top_tier and _is_core(n, n_required, n_preferred):
            bucket: SkillBucket = "core"
        elif in_top_tier:
            bucket = "preferred_top"
        else:
            bucket = "below_threshold"

        pct_jobs = round((n / total_jobs) * 100, 2) if total_jobs else 0.0
        rank_percentile = round(((total_skills - rank + 1) / total_skills) * 100, 2)

        classified.append(
            {
                **row,
                "n_required": n_required,
                "n_preferred": n_preferred,
                "n_mentioned": n_mentioned,
                "pct_jobs": pct_jobs,
                "rank": rank,
                "rank_percentile": rank_percentile,
                "tier": "top" if in_top_tier else "below",
                "bucket": bucket,
                "low_sample": n < 5,
            }
        )

    return classified
