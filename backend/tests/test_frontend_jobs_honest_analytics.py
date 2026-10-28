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
from app.services import rates

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


def test_the_interview_share_says_what_it_counts():
    # The current-count tile ("At interview or later ... there now") went with the Overview tab (design refresh
    # Task 5.2). The funnel reads the dated events (search_summary INTERVIEW_STATUSES: reached interviewing or
    # later), so its words say "reached", and of what the share is.
    counted = _read("components/analytics/how-counted.tsx")
    assert '["Interview", "Reached an interview or later. Its share is of the applications that heard back."],' in counted
    assert '["Offer", "Reached an offer. Its share is of the applications that reached an interview."],' in counted
    lib = _read("lib/search-summary.ts")
    assert 'label: "Interview",' in lib and 'unit: ["reply", "replies"],' in lib


def test_a_share_reads_as_counts_below_the_minimum():
    # Owner decision D7: below rates.MIN_RATE_N the server sends no rate, and the share says "1 of 3".
    words = _read("lib/rates.ts")
    assert f"export const MIN_RATE_N = {rates.MIN_RATE_N};" in words
    assert "return { value: `${r.count} of ${r.of}${noun}`, range: null };" in words
    assert "return r.rate !== null && r.of >= MIN_RATE_N;" in words
    assert "A rate shows from {summary.min_rate_n}" in _read("components/analytics/applications-funnel.tsx")


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


def test_skills_by_role_shows_counts_below_twenty_jobs_in_a_role():
    """D7 on the heatmap: each row carries its role's job count (`of`, routers/explore.py) and a cell reads
    "2 of 3" while the role has fewer than rates.MIN_RATE_N jobs, a share only from there
    (components/charts/heatmap-chart.test.mjs renders it)."""
    from tests.node_ts import run_node_render_test

    src = Path(explore.__file__).read_text(encoding="utf-8")
    assert '"count": row.n,' in src and '"of": role_totals.get(row.role_category, 0),' in src
    heatmap = _read("components/charts/heatmap-chart.tsx")
    assert "const words = rateWords(share).value;" in heatmap and "const counts = of < MIN_RATE_N;" in heatmap
    assert "toFixed(0)}%" not in heatmap
    result = run_node_render_test("components/charts/heatmap-chart.test.mjs")
    assert result.returncode == 0, result.stdout + result.stderr


def test_job_market_captions_are_accurate():
    market = _read("components/explore/explore-overview.tsx")
    assert "Sorted from each job description into one of these levels." in market
    assert "As written in each job." not in market
    # Yearly pay by role moved to Jobs you saved: each role counts its jobs that list pay, and the card says how
    # many of all saved jobs list pay.
    saved = _read("components/analytics/jobs-you-saved.tsx")
    assert '{count(r.n, "job", "jobs")}' in saved
    assert "{overview.meta.jobs_with_salary} of {overview.meta.total_jobs} list pay" in saved


def test_job_market_money_has_one_format():
    market = _read("components/explore/explore-overview.tsx")
    saved = _read("components/analytics/jobs-you-saved.tsx")
    for src in (market, saved):
        assert "const fmtK" not in src
        assert "salary_by_role" not in src
    # Yearly pay by role arrives in your home currency (plan Task 3.9), worded by the one formatter: "≈" when any
    # of a role's pay was converted, and no server-worded money ("$150K") anywhere on the page.
    assert "formatPay({ min, max, currency: home, period: null }, { home })?.primary" in saved
    assert "{homePay(r.avg_min, r.avg_max, pay.currency, r.converted_count > 0)}" in saved
    assert "${converted ? APPROX : \"\"}${text}" in saved
    # The average-pay tile (one mean, or "Mixed currencies") went: pay by role in one currency says it (Task 5.2).
    assert "salary_year_avg" not in market and "salary_year_avg" not in saved


def test_job_market_places_and_skills_read_as_words():
    market = _read("components/explore/explore-overview.tsx")
    assert "label: placeName(r.key)" in market
    # Country keys are ISO codes, and a job naming no one country reads "Not stated".
    assert 'label: r.key === "unknown" ? "Not stated" : countryName(r.key),' in market
    # Work mode and the skills jobs ask for moved to Jobs you saved (Task 5.2): words, never the stored key.
    saved = _read("components/analytics/jobs-you-saved.tsx")
    assert "label: humanizeEnum(r.key) ?? r.key" in saved
    assert "name={skillName(row.skill_name)}" in saved
    places = _read("lib/place-name.ts")
    assert 'CA: "California",' in places and '(no city)' in places
    assert not re.search(r"^import (?!type )", places, re.M)


def test_the_country_filter_offers_one_code_per_country_in_words():
    page = _read("app/analytics/page.tsx")
    assert "if (job.country_code) countries.add(job.country_code);" in page
    assert "options.countries,\n        countryName,\n      )}" in page


@pytest.mark.parametrize(
    "rel",
    ["components/charts/top-skills-chart.tsx", "components/charts/heatmap-chart.tsx", "components/analytics/gap-tiers-panel.tsx"],
)
def test_skill_names_are_cased_one_way(rel: str):
    # The name a row or tile shows, not only its tooltip.
    shown = {
        "components/charts/top-skills-chart.tsx": "{skillName(skill.skill_name)}\n",
        "components/charts/heatmap-chart.tsx": "{skillName(skill)}\n",
        "components/analytics/gap-tiers-panel.tsx": '<span className="text-title-small">{skillName(row.skill)}</span>',
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
    # Card subtitles left Analytics (Task 5.2): the title says it, and the ATS lead explains the score once.
    assert "<CardTitle>Match score over time</CardTitle>" in fit
    assert "(how an applicant tracking system" not in fit


def test_skill_gaps_say_one_thing_per_tier():
    panel = _read("components/analytics/gap-tiers-panel.tsx")
    assert '{isSurface ? "A gap in" : "Missing in"} {row.n_jobs}' in panel
    assert "“Use the job description&apos;s wording when your experience backs it up”" in panel


def test_the_job_market_has_no_opt_tile():
    # For everyone (design refresh Task 5.2): one country's student work permit left Analytics. The job page
    # still explains it where a US job states it (job-extracted-fields.tsx).
    market = _read("components/explore/explore-overview.tsx")
    assert "OPT" not in market and "work_auth.opt" not in market
    assert 'label="OPT (US student work permit) accepted"' in _read("components/job-extracted-fields.tsx")
