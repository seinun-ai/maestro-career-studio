"""The first-read pass's findings (plan 2026-09-23-ux-ia-copy, Task 25): a reviewer who
had not seen the audits read every screen as a new user. Each pin is one sentence
that read wrong, and what it says now. The node tests (lib/*.test.ts) hold the
helpers' cases; they are not in CI, so the wiring is pinned here."""

from __future__ import annotations

from pathlib import Path

from tests.node_ts import ts_map

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


def test_first_run_says_the_key_comes_first():
    tracker = _read("app/applications/page.tsx")
    assert '? "Add an API key first, then add a job."' in tracker
    assert "const needsKey = setup.data?.model_key.done === false;" in tracker
    assert '<Link href={anchorHref("/settings", "api-keys")}>' in tracker


def test_the_tracker_names_its_status_filter():
    tracker = _read("app/applications/page.tsx")
    assert "{`Status: ${filterLabel(filter)} · ${countOf(filter)}`}" in tracker


def test_the_resume_tab_says_what_a_draft_lacks():
    panel = _read("components/application-panel.tsx")
    assert '{pdfReady ? "PDF ready" : hasDraft ? "Not yet a PDF" : "Not started"}' in panel


def test_dates_read_as_words():
    chips = _read("components/gap-analysis/resolution-controls.tsx")
    assert "{formatResumeMonth(date)}" in chips
    assert ts_map("./lib/format-date.ts", "formatResumeMonth", ["2021-02", "02/2021", "Jul 2022", "Present"]) == [
        "Feb 2021", "Feb 2021", "Jul 2022", "Present"]
    dates = _read("lib/format-date.ts")
    assert 'return date.toLocaleString("en-US", {' in dates and "date.toLocaleString();" not in dates
    autofill = _read("components/settings/autofill-section.tsx")
    assert "You agreed on {formatAbsoluteDateTime(consent.acknowledged_at)}" in autofill


def test_analytics_says_each_thing_once_in_one_format():
    overview = _read("components/analytics/analytics-overview.tsx")
    # One label for the Skill gaps destination, and no tag repeating the card's title.
    assert overview.count("See all skill gaps <ArrowRight") == 2
    assert "              Skill gaps <ArrowRight" not in overview
    quick = overview[overview.index("Quick wins from your career history") :]
    assert "In your career history" not in quick
    market = _read("components/explore/explore-overview.tsx")
    assert "<p className=\"text-foreground text-sm font-medium\">{signalTitle(s.title, o)}</p>" in market
    assert "return title.replace(`: ${place} (`, `: ${placeName(place)} (`);" in market
    assert "return title.replace(`: ${skill} (`, `: ${skillName(skill)} (`);" in market
    assert "accept OPT or STEM OPT (24 more months for science and tech degrees)" in market


def test_the_inbox_names_its_own_numbers():
    cap = _read("components/proposals/cap-today.tsx")
    assert 'label="Couldn\'t load Applications per day. Try again"' in cap
    assert "Couldn't load the daily cap" not in cap and '"Retry loading' not in cap
    triage = _read("components/proposals/triage-actions.tsx")
    assert 'description: "This also deletes the screenshots your agent took.",' in triage
