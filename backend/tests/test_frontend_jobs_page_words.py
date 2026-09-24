"""Pins: the tracker is called Jobs, and its source filter Tracked · Yours · Agents.

The owner's call (SYSTEM.md §11 item 36, resolved 2026-09-24): the page lists
saved jobs as well as applications, so it and its sidebar item read "Jobs";
the source segment that used to read "All" hid every job an agent found and
nobody proposed or applied to (those live under Agents), so it reads "Tracked".
"Tracked" is EXACTLY the old "All" set (your saved jobs plus every application,
agent ones included), so only words change here. The URL `/applications`, the
`?status=`/`?source=` deep links and the `cs-tracker-*` session keys stay, so
every bookmark and the job page's prev/next keep working.

Analytics shares the toggle and keeps "All": its activity query applies no
source filter at all (`explore_activity`, `source=None`), so there "All" is
every application, which is what the word says. "Yours" replaces "You" on both.

"Application" still means an actual application (tailored or applied):
"Your applications" in the status filter, the cap notice's noun, "Applications
per day", the Referrals and Analytics counts. The vocabulary ratchet refuses
"Applications" as a PAGE name (test_frontend_vocabulary.py).
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND = _ROOT / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


def _flat(src: str) -> str:
    return " ".join(src.split())


_TRACKER = _read("app/applications/page.tsx")
_TOGGLE = _read("components/source-toggle.tsx")


def test_the_page_and_its_sidebar_item_are_called_jobs():
    assert '{ href: "/applications", label: "Jobs", icon: Inbox },' in _read("components/app-sidebar.tsx")
    assert 'title="Jobs"' in _TRACKER
    # What it lists, truthfully: Tracked is the default and holds exactly this.
    assert 'subtitle="Jobs you saved and every application. Jobs a connected agent found are under Agents."' in _TRACKER


def test_every_way_back_names_jobs():
    for rel in ("app/error.tsx", "app/not-found.tsx", "app/applications/[id]/page.tsx"):
        src = _read(rel)
        assert '<Link href="/applications">Back to Jobs</Link>' in src, rel
        assert "Back to applications" not in src, rel
    job = _read("app/jobs/[id]/page.tsx")
    assert 'fromProposals ? "Back to Agent inbox" : "Back to Jobs"' in job
    assert '<Link href="/applications">Back to Jobs</Link>' in job
    assert '"Previous job in Jobs"' in job and '"Next job in Jobs"' in job
    assert "job in list" not in job


def test_a_saved_job_says_where_it_went():
    summary = _flat(_read("components/job-extraction-summary.tsx"))
    assert 'Saved to{" "} <Link href="/applications?status=saved" className="underline"> Jobs </Link> .' in summary
    assert "Saved jobs appear on the Jobs page, ready to score." in _read("app/new/page.tsx")


def test_the_empty_and_failed_states_name_jobs():
    flat = _flat(_TRACKER)
    assert '? "No jobs yet"' in flat
    assert 'title="Couldn\'t load your jobs."' in flat
    # An application is still an application.
    assert "<SelectLabel>Your applications</SelectLabel>" in flat


def test_the_source_segments_read_tracked_yours_agents_on_jobs_only():
    assert 'export const SOURCES = ["all", "user", "agent"] as const;' in _TOGGLE
    assert '{s === "all" ? allLabel : s === "user" ? "Yours" : "Agents"}' in _TOGGLE
    assert 'allLabel = "All",' in _TOGGLE
    assert 'allLabel="Tracked"' in _TRACKER
    # Analytics' All is every application (no source filter), so it keeps the word.
    analytics = _read("components/analytics/analytics-overview.tsx")
    assert "<SourceToggle value={source} onChange={setSource} />" in analytics


def test_tracked_is_exactly_the_old_all_set():
    """Words only: saved jobs come from YOUR source unless Agents is on, and
    the application rows are filtered by source only off Tracked."""
    assert 'const savedSource = source === "agent" ? "agent" : "user";' in _TRACKER
    assert 'if (source === "all") return allRows;' in _TRACKER
    assert '(r) => r.kind === "saved" || r.app.source === source,' in _TRACKER


def test_links_and_session_memory_keep_their_names():
    for key in ('"cs-tracker-filter"', '"cs-tracker-source"', '"cs-tracker-seq"'):
        assert key in _TRACKER, key
    assert 'router.replace(qs ? `/applications?${qs}` : "/applications", { scroll: false });' in _TRACKER
    assert 'return v === "user" || v === "agent" ? v : "all";' in _TRACKER
    assert 'readSequence(fromProposals ? "cs-proposals-seq" : "cs-tracker-seq")' in _read("app/jobs/[id]/page.tsx")
    assert 'return from === "proposals" ? "/proposals" : "/applications";' in _read("lib/nav.ts")
