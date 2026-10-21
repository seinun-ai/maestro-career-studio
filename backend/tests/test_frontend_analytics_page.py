"""Analytics is one page (design refresh, Task 5.2): no tabs, a period control and the source toggle, a funnel
lead with honest rates, and the detail folded. Source pins: the frontend has no component runner, so the
`lib/` halves run under node here as well."""

from __future__ import annotations

import re
from pathlib import Path

from app.services import rates, search_summary
from tests._jsx_pins import open_tag, squash
from tests.node_ts import run_node_test

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_PAGE = "app/analytics/page.tsx"
_FUNNEL = "components/analytics/applications-funnel.tsx"
_TILES = "components/analytics/search-tiles.tsx"
_BY_RESUME = "components/analytics/by-resume-card.tsx"
_WEEKS = "components/analytics/each-week-chart.tsx"
_SAVED = "components/analytics/jobs-you-saved.tsx"
_RATE_LABEL = "components/analytics/rate-label.tsx"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


# An import, or a re-export (`components/visual/index.ts` re-exports each primitive).
_IMPORT = re.compile(
    r'^(?:import\s+(?:[^;]*?\s+from\s+)?|export\s+(?:type\s+)?(?:\*|\{[^}]*\})\s+from\s+)"([^"]+)";', re.M | re.S
)


def _resolve(spec: str, importer: Path) -> Path | None:
    if spec.startswith("@/"):
        base = _FRONTEND / spec[2:]
    elif spec.startswith("."):
        base = (importer.parent / spec).resolve()
    else:
        return None  # a package
    for candidate in (base, Path(f"{base}.tsx"), Path(f"{base}.ts"), base / "index.ts", base / "index.tsx"):
        if candidate.is_file():
            return candidate
    return None


def _rendered_files() -> set[str]:
    """Every frontend module the Analytics page reaches through its imports."""
    seen: set[Path] = set()
    todo = [_FRONTEND / _PAGE]
    while todo:
        path = todo.pop()
        if path in seen:
            continue
        seen.add(path)
        for spec in _IMPORT.findall(path.read_text(encoding="utf-8")):
            target = _resolve(spec, path)
            if target is not None and target not in seen:
                todo.append(target)
    return {p.relative_to(_FRONTEND).as_posix() for p in seen}


_ANALYTICS_DIRS = ("app/analytics/", "components/analytics/", "components/explore/", "components/charts/")


def _analytics_own_files() -> list[str]:
    """The page's own files: the ones under Analytics' folders (shared modules such as the job page's field
    labels are reached for a helper, not rendered)."""
    return sorted(p for p in _rendered_files() if p.startswith(_ANALYTICS_DIRS))


def test_rate_words_node_suite():
    result = run_node_test("lib/rates.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr


def test_search_summary_node_suite():
    result = run_node_test("lib/search-summary.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_rate_floor_is_the_servers():
    # Owner decision D7: one number, said in both places.
    assert f"export const MIN_RATE_N = {rates.MIN_RATE_N};" in _read("lib/rates.ts")
    lib = _read("lib/search-summary.ts")
    assert f"export const QUIET_AFTER_DAYS = {search_summary.QUIET_AFTER_DAYS};" in lib
    assert f"export const MIN_REPLIES_FOR_TIMING = {search_summary.MIN_REPLIES_FOR_TIMING};" in lib


def test_autofill_coverage_left_analytics():
    """D6: the coverage card is a Companion diagnostic (Settings › Advanced › Diagnostics, Task 7.6). Nothing the
    Analytics page renders imports it, directly or through another module."""
    reached = _rendered_files()
    assert _PAGE in reached and _FUNNEL in reached and _SAVED in reached  # the walk follows the page
    assert "components/analytics/autofill-coverage-card.tsx" not in reached
    for rel in _analytics_own_files():
        assert "AutofillCoverageCard" not in _read(rel), rel


def test_opt_appears_nowhere_on_the_page():
    """For everyone: OPT is one country's student work permit, so it has no tile, bar or word here."""
    own = _analytics_own_files()
    assert "components/explore/explore-overview.tsx" in own
    for rel in own:
        src = _read(rel)
        assert not re.search(r"\bOPT\b", src), rel
        assert "work_auth.opt" not in src, rel


def test_rates_render_through_rate_label():
    """D7: a share reads through RateLabel, which says "5 of 12" below 20 and a percent with its range from 20.
    No other analytics file reads a share's rate or range itself."""
    label = _read(_RATE_LABEL)
    assert "export function RateLabel(" in label and "rateWords(value, unit)" in label
    for rel in (_FUNNEL, _TILES, _BY_RESUME):
        assert "<RateLabel" in _read(rel), rel
    for rel in _analytics_own_files():
        if rel == _RATE_LABEL:
            continue
        assert not re.search(r"\b(heard_back|interview|offer|quiet|rate)\.(rate|low|high)\b", _read(rel)), rel


def test_the_page_sends_weeks_and_source():
    page = squash(_read(_PAGE))
    assert "queryKey: summaryKey(period, source)," in page
    assert "queryFn: () => apiFetch<SearchSummary>(summaryPath(period, source))," in page
    assert "<PeriodToggle value={period} onChange={setPeriod} />" in page
    assert "<SourceToggle value={source} onChange={setSource} />" in page
    lib = _read("lib/search-summary.ts")
    assert "new URLSearchParams({ weeks: period, source })" in lib


def test_one_page_with_no_tabs_and_no_subtitle():
    page = _read(_PAGE)
    assert "<Tabs" not in page and "TabsContent" not in page and "?tab=" not in page
    assert "subtitle=" not in open_tag(page, "PageHeader")  # D1: the Lead says what matters


def test_the_lead_is_where_your_applications_went():
    funnel = _read(_FUNNEL)
    assert '<LeadCard eyebrow="Where your applications went"' in funnel
    # The two rules, said once beside the numbers they govern.
    assert "A rate shows from {summary.min_rate_n}" in funnel
    assert "In brackets: the 95% likely range" in funnel
    # Counts roll; a failed or empty read is its own state.
    assert "<NumberRoll value={row.count}" in funnel


def test_the_folds_hold_the_detail():
    page = _read(_PAGE)
    for title in ('title="Match scores in detail"', 'title="Skill gaps"', 'title="Market in detail"',
                  'title="How these are counted"'):
        assert title in page, title
    # The gaps card opens the Skill gaps fold: one control state, no second copy of the panel.
    assert "open={gapsOpen}" in page and "onOpenChange={setGapsOpen}" in page


def test_quick_wins_left_and_gaps_are_one_card():
    for rel in _analytics_own_files():
        assert "Quick wins" not in _read(rel), rel
    saved = _read(_SAVED)
    assert "<CardTitle>Most common gaps</CardTitle>" in saved
    # The career-history evidence the quick wins card listed rides on each gap row instead.
    assert 'row.status === "in_kb"' in saved and "In your career history" in saved
    assert 'row.tier !== "wording"' in saved


def test_jobs_you_saved_reads_pay_in_your_currency():
    saved = _read(_SAVED)
    assert "homePay(r.avg_min, r.avg_max, pay.currency, r.converted_count > 0)" in saved
    # The conversion and the hidden roles are chips under the bars, from the payload's numbers.
    assert "const notes = payNotes(pay);" in saved and "{notes.map((note) => (" in saved
    assert "hidden: under ${pay.min_jobs} jobs`" in saved
    assert "left out: no exchange rate`" in saved
    # The average-pay tile and its "Mixed currencies" are gone: pay by role in one currency replaces them.
    for rel in _analytics_own_files():
        assert "Mixed currencies" not in _read(rel), rel
        assert "salary_year_avg" not in _read(rel), rel


def test_work_mode_is_a_segmented_bar_in_series_colours():
    """A work mode is not a status: its parts take the chart series (colour follows the mode, never its rank),
    and a mode the payload does not state reads Not stated."""
    saved = _read(_SAVED)
    assert '<SegmentedBar name="Work mode"' in saved
    assert 'hybrid: "chart-1", on_site: "chart-2", remote: "chart-3"' in saved
    bar = _read("components/visual/segmented-bar.tsx")
    assert '"chart-1": "bg-chart-1"' in bar


def test_skills_show_the_top_five_and_count_the_rest():
    saved = _read(_SAVED)
    assert "const TOP_SKILLS = 5;" in saved
    # A skill seen in one job is not a pattern (canvas: it leaves Analytics).
    assert ".filter((row) => row.n > 1)" in saved
    assert "data.meta.total_skills - shown.length" in saved


def test_by_resume_names_each_resume_with_its_square():
    card = _read(_BY_RESUME)
    assert "<ResumeTag hue={row.color_hue} className=\"max-w-full\">" in card
    assert "row.name ?? baseName(row.slug)" in card


def test_each_week_draws_applied_and_replies_and_says_what_no_week_holds():
    chart = _read(_WEEKS)
    assert 'dataKey="applied"' in chart and 'dataKey="replies"' in chart
    assert "fill={CHART_COLORS[0]}" in chart and "fill={CHART_COLORS[1]}" in chart
    assert "strokeDasharray" not in chart  # gridlines are solid hairlines
    assert "undated_replies" in chart
