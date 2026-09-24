"""Analytics and the shared job words say only what is true (IA wave 3, lane 7 review).

Split from test_frontend_jobs_honest_words.py by surface. The `lib/` helpers
have node tests, which are not in CI, so the branches that carry a claim are
pinned here too.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.routers import explore

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


def test_interview_rate_says_it_is_a_current_count():
    # explore_activity: "currently at interview+ per submitted".
    overview = _read("components/analytics/analytics-overview.tsx")
    assert 'label="At interview or later"' in overview
    assert "`now, of ${totals.submitted} applications`" in overview
    assert "Reached interviews" not in overview


def test_the_cap_line_says_one_window():
    cap = _read("components/proposals/cap-today.tsx")
    assert "Applications per day: {cap.reserved_last_24h} of {cap.max_per_day} used in the last 24 hours" in cap
    assert "Cap today" not in cap and "sr-only" not in cap


def test_the_heatmap_says_it_shows_the_top_30_percent():
    src = Path(explore.__file__).read_text(encoding="utf-8")
    assert 'skill_rows = [row for row in classified if row["tier"] == "top"]' in src
    heatmap = _read("components/charts/heatmap-chart.tsx")
    assert 'top_tier_only: "true"' in heatmap
    assert "Shows the top 30% of skills, the ones jobs ask for most." in heatmap


def test_job_market_captions_are_accurate():
    market = _read("components/explore/explore-overview.tsx")
    assert "Sorted from each job description into one of these levels." in market
    assert "As written in each job." not in market
    assert '{r.n} {r.n === 1 ? "job" : "jobs"} with pay listed' in market


def test_job_market_money_has_one_format():
    market = _read("components/explore/explore-overview.tsx")
    assert "const fmtK" not in market
    assert "formatSalary(min, max, null, currency ?? null)" in market
    assert "{payRange(r.avg_min, r.avg_max, r.currency)}" in market
    assert "payRange(o.meta.salary_year_avg_min, o.meta.salary_year_avg_max, o.meta.salary_year_currency)" in market


def test_job_market_places_and_skills_read_as_words():
    market = _read("components/explore/explore-overview.tsx")
    assert "label: placeName(r.key)" in market and "label: countryName(r.key)" in market
    assert "label: skillName(s.skill_name)" in market
    places = _read("lib/place-name.ts")
    assert 'CA: "California",' in places and '(no city)' in places
    assert not re.search(r"^import (?!type )", places, re.M)


@pytest.mark.parametrize(
    "rel",
    ["components/charts/top-skills-chart.tsx", "components/charts/heatmap-chart.tsx", "components/analytics/gap-tiers-panel.tsx"],
)
def test_skill_names_are_cased_one_way(rel: str):
    # The name a row or tile shows, not only its tooltip.
    shown = {
        "components/charts/top-skills-chart.tsx": "{skillName(skill.skill_name)}\n",
        "components/charts/heatmap-chart.tsx": "{skillName(skill)}\n",
        "components/analytics/gap-tiers-panel.tsx": '<span className="text-sm font-medium">{skillName(row.skill)}</span>',
    }
    assert shown[rel] in _read(rel)


def test_skill_name_casing_rules():
    lib = _read("lib/skill-name.ts")
    for pair in ('pytorch: "PyTorch"', '"a/b"', 'mlflow: "MLflow"'):
        assert pair in lib, pair
    assert "KNOWN[name.trim().toLowerCase()]" in lib
    assert not re.search(r"^import (?!type )", lib, re.M)


@pytest.mark.parametrize("rel", ["components/charts/ats-over-time-chart.tsx", "components/charts/role-mix-chart.tsx"])
def test_weekly_charts_say_week_of(rel: str):
    chart = _read(rel)
    assert "<XAxis dataKey=\"week\" tickFormatter={weekTick} />" in chart
    assert "labelFormatter={weekLabel}" in chart
    assert "return `Week of ${formatShortDate(value)}`;" in _read("lib/format-date.ts")


def test_resume_fit_words():
    cards = _read("components/analytics/base-summary-cards.tsx")
    assert "Health not checked yet" in cards and "No health check" not in cards
    fit = _read("app/analytics/page.tsx")
    assert "Weekly average ATS score.\n" in fit
    assert "(how an applicant tracking system" not in fit


def test_skill_gaps_say_one_thing_per_tier():
    panel = _read("components/analytics/gap-tiers-panel.tsx")
    assert '{isSurface ? "A gap in" : "Missing in"} {row.n_jobs}' in panel
    assert "“Use the job description&apos;s wording when your experience backs it up”" in panel


def test_the_job_market_opt_tile_explains_opt():
    market = _read("components/explore/explore-overview.tsx")
    assert 'label="OPT (US student work permit)"' in market
