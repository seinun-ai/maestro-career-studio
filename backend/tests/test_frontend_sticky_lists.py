"""Pins for sticky list chrome (a list's toolbar and its table header) and the
notice at the end of a capped list.
Design: docs/plans/2026-09-23-ux-ia-appendix-b-sticky-and-cap.md."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND = _ROOT / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


def _body(src: str, start: str) -> str:
    """From `start` to the end of that top-level function (a `}` alone at column 0)."""
    i = src.index(start)
    return src[i : src.index("\n}\n", i)]


_TABLE = _read("components/ui/table.tsx")
_TOOLBAR = _read("components/list-toolbar.tsx")
_CSS = _read("app/globals.css")

_SCROLL_CHAIN = [
    ("components/ui/sidebar.tsx", "function SidebarProvider("),
    ("components/ui/sidebar.tsx", "function SidebarInset("),
    ("components/sidebar-reveal-trigger.tsx", "export function SidebarGutter("),
    ("components/page-shell.tsx", "export function PageShell("),
]


# ── The window is the only scroller ─────────────────────────────────────────


@pytest.mark.parametrize("rel,start", _SCROLL_CHAIN)
def test_the_window_stays_the_only_scroller(rel: str, start: str):
    """position: sticky sticks to the nearest scrolling ancestor. The list
    toolbar and header rely on that being the window: an overflow class on any
    shell element between them and <html> pins them to a box that never
    scrolls, and they silently stop sticking."""
    found = re.findall(r"\boverflow-[\w-]+", _body(_read(rel), start))
    assert found == [], f"{rel} {start}: {found}"


def test_layout_and_document_do_not_scroll_themselves():
    assert not re.search(r"\boverflow-[\w-]+", _read("app/layout.tsx"))
    for sel in ("  html {", "  body {"):
        i = _CSS.index(sel)
        assert "overflow" not in _CSS[i : _CSS.index("}", i)], sel


# ── Table: a min width, and a header that sticks while the table fits ───────

_WIDTH_ENTRY = re.compile(
    r'"(\d+rem)": \{\s*'
    r'table: "min-w-\[(\d+rem)\]",\s*'
    r'fits: "@min-\[(\d+rem)\]/table:overflow-x-clip",\s*'
    r'head: "@min-\[(\d+rem)\]/table:tall:sticky",\s*\}'
)


def test_a_table_sticks_from_exactly_its_own_min_width():
    entries = _WIDTH_ENTRY.findall(_TABLE)
    assert len(entries) >= 2, "MIN_WIDTH entries not found"
    for widths in entries:
        assert len(set(widths)) == 1, widths
    block = _TABLE[_TABLE.index("const MIN_WIDTH = {") : _TABLE.index("} as const")]
    assert block.count('table: "min-w-[') == len(entries)  # no entry the regex skipped


def test_the_container_scrolls_sideways_until_the_table_fits():
    table = _body(_TABLE, "function Table(")
    assert '"relative w-full overflow-x-auto", sticky?.fits' in table
    assert '"@container/table w-full"' in table
    assert "StickyHeadContext.Provider value={sticky.head}" in table


def test_every_table_with_a_min_width_gets_it():
    """Sticky or not: the width keeps the columns from crushing at narrow
    widths, and it is what a sticky table measures its fit against."""
    table = _body(_TABLE, "function Table(")
    assert "const width = minWidth ? MIN_WIDTH[minWidth] : undefined" in table
    assert 'className={cn("w-full caption-bottom text-sm", width?.table, className)}' in table


def test_only_a_table_that_asks_for_it_sticks():
    """A min width alone is not a sticky header: the Referrals-style opt-in
    (`stickyHeader`) is what turns the scope, the clip and the class on."""
    table = _body(_TABLE, "function Table(")
    assert "const sticky = stickyHeader && width ? width : undefined" in table
    assert "if (!sticky) return table" in table


def test_a_sticky_header_carries_the_sticky_class_itself():
    """The context's class (`@min-[..]/table:tall:sticky`) is what makes the
    header stick; everything else in the array only dresses it."""
    head = _body(_TABLE, "function TableHeader(")
    assert re.search(r"sticky\s*\?\s*\[\s*sticky,\n", head)


def test_a_sticky_header_is_opaque_ruled_stacked_and_placed_under_the_toolbar():
    head = _body(_TABLE, "function TableHeader(")
    for part in (
        "React.useContext(StickyHeadContext)",
        'data-sticky={sticky ? "" : undefined}',
        '"top-(--list-sticky-top,0px) z-10"',
        '"[&_th]:bg-background"',
        '"[&_tr]:border-b-0 [&_th]:shadow-[inset_0_-1px_0_var(--color-border)]"',
        ': "[&_tr]:border-b"',
    ):
        assert part in head, part


def test_the_table_frame_clips_without_becoming_a_scroller():
    frame = _body(_read("components/empty-state.tsx"), "export function TableFrame(")
    assert '"animate-fade-rise overflow-clip rounded-xl border"' in frame
    assert "overflow-hidden" not in frame


# ── ListToolbar, the tall: variant, and focus clearance ──────────────────────


def test_the_tall_threshold_is_one_number_and_screen_only():
    """One query for the three places that ask it. `screen and`: nothing
    sticks in print. A `print:static` beside `tall:sticky` lost to it in
    Chromium (the custom variant's rule comes later in the stylesheet), so a
    printed page carried a stuck bar mid-page."""
    query = r"(screen and \(min-height: [\d.]+rem\))"
    css = re.search(r"@custom-variant tall \(@media " + query + r"\);", _CSS)
    assert css, "the tall variant"
    ts = re.search(r'export const TALL_QUERY = "' + query + r'";', _TOOLBAR)
    assert ts and ts.group(1) == css.group(1)
    head = re.search(
        r"@media " + query + r' \{\s*html:has\(\[data-slot="table-header"\]\[data-sticky\]\)',
        _CSS,
    )
    assert head and head.group(1) == css.group(1)


def test_the_toolbar_sticks_on_the_page_colour_above_the_list():
    for part in ("tall:sticky", "tall:top-0", "tall:z-30", "bg-background", "-my-3", "py-3"):
        assert part in _TOOLBAR, part


def test_the_toolbar_is_a_search_landmark_not_a_toolbar_role():
    """HTML's element for search and filtering controls (planner decision 17,
    O6). Not role="toolbar": that role promises arrow-key roving, and these
    controls are separate Tab stops."""
    body = _body(_TOOLBAR, "export function ListToolbar(")
    ret = body[body.index("\n  return (\n") :]
    assert ret.startswith("\n  return (\n    <search\n")
    assert "</search>" in ret
    assert "role=" not in ret


def test_the_toolbar_publishes_its_height():
    body = _body(_TOOLBAR, "export function ListToolbar(")
    assert 'const STICKY_TOP_VAR = "--list-sticky-top";' in _TOOLBAR
    assert "new ResizeObserver(write)" in body
    assert "window.matchMedia(TALL_QUERY)" in body
    assert 'tall.addEventListener("change", write)' in body
    assert "Math.floor(el.getBoundingClientRect().height)" in body
    assert "root.style.setProperty(STICKY_TOP_VAR, written)" in body
    assert "--list-sticky-top" in _body(_TABLE, "function TableHeader(")


def _toolbar_body() -> str:
    return _body(_TOOLBAR, "export function ListToolbar(")


def test_the_toolbar_measures_the_element_it_renders():
    body = _toolbar_body()
    assert "const el = ref.current;" in body
    assert re.search(r"<search\n\s*ref=\{ref\}\n", body)


def test_the_toolbar_measures_now_and_on_every_resize():
    """Once on mount, so the header's first paint already sits under the
    toolbar, then on every change of the toolbar's own size (it wraps, and a
    filter label carries a count)."""
    body = _toolbar_body()
    assert "    write();\n    const observer = new ResizeObserver(write);\n" in body
    assert "observer.observe(el);" in body


def test_below_the_tall_query_the_toolbar_publishes_zero():
    """Nothing sticks below TALL_QUERY, so the header sits at the top and the
    focus clearance is the header alone."""
    assert re.search(
        r"written = tall\.matches\s*\?\s*`\$\{Math\.floor\(el\.getBoundingClientRect\(\)\.height\)\}px`"
        r'\s*:\s*"0px";',
        _toolbar_body(),
    )


def test_the_toolbar_stops_listening_when_it_unmounts():
    body = _toolbar_body()
    cleanup = body[body.index("return () => {") :]
    assert 'tall.removeEventListener("change", write);' in cleanup


def test_the_toolbar_takes_back_only_its_own_height():
    body = _body(_TOOLBAR, "export function ListToolbar(")
    cleanup = body[body.index("return () => {") :]
    assert "observer.disconnect()" in cleanup
    assert "=== written) root.style.removeProperty(STICKY_TOP_VAR)" in cleanup


_PAD = "scroll-padding-top: calc(var(--list-sticky-top, 0px) + var(--list-head-h, 0px));"
_IN_LIST = (
    'html:has([data-slot="list-toolbar"] ~ :focus-within,\n'
    '    [data-slot="table-header"][data-sticky] ~ [data-slot="table-body"] :focus) {'
)


def test_focus_scrolled_into_view_clears_the_sticky_chrome():
    """WCAG 2.4.11 (C43). Browser-verified in Chromium: without it, Shift+Tab
    onto a row under a stuck header leaves that row under it."""
    rule = _CSS[_CSS.index(_IN_LIST) :]
    assert rule[: rule.index("}")].count(_PAD) == 1
    assert re.search(
        r'html:has\(\[data-slot="table-header"\]\[data-sticky\]\) \{\s*--list-head-h: 3rem;', _CSS
    )


def test_only_focus_in_the_list_is_cleared():
    """The padding counts the toolbar's own height, so on html it treated a
    control IN the stuck toolbar, a portalled popup or a dialog as under the
    chrome. Browser-verified in Chromium: focusing the status filter while
    scrolled moved the page up about 400px, and opening it about 370px more.
    Nothing before the toolbar or outside the page can sit under it, so the
    padding applies only while focus is after a ListToolbar or in a sticky
    table's body."""
    html = _CSS[_CSS.index("  html {") :]
    assert "scroll-padding" not in html[: html.index("}")]
    assert _CSS.count("scroll-padding-top") == 1


def test_a_focused_lane_after_the_toolbar_is_cleared_too():
    """A later sibling of the toolbar that takes focus ITSELF (a lane root
    with tabIndex=-1, as the Agent inbox hands focus to) is in the list too,
    and so is anything inside one. Browser-checked in Chromium: `~ * :focus`
    missed the sibling itself, and `~ :is(:focus, * :focus)` matched only
    the sibling (both arms test the sibling), dropping every row in it."""
    assert '[data-slot="list-toolbar"] ~ :focus-within' in _CSS


_SLOT_OWNERS = {
    "list-toolbar": ("components/list-toolbar.tsx", "export function ListToolbar("),
    "table-header": ("components/ui/table.tsx", "function TableHeader("),
    "table-body": ("components/ui/table.tsx", "function TableBody("),
}


def test_every_slot_the_css_names_is_rendered_by_its_owner():
    """globals.css keys the head height and the focus clearance on data-slot
    values. Renamed on one side only, the rule silently matches nothing."""
    named = set(re.findall(r'\[data-slot="([\w-]+)"\]', _CSS))
    assert named == set(_SLOT_OWNERS)
    for slot, (rel, start) in _SLOT_OWNERS.items():
        assert f'data-slot="{slot}"' in _body(_read(rel), start), slot


# ── Applications and Referrals adopt them ────────────────────────────────────

_TRACKER = _read("app/applications/page.tsx")
_REFERRALS = _read("app/referrals/page.tsx")
_SEARCH = _read("components/list-search.tsx")


def test_every_call_site_width_is_in_the_map_and_nowhere_else():
    keys = {w[0] for w in _WIDTH_ENTRY.findall(_TABLE)}
    for root in ("app", "components"):
        for p in sorted((_FRONTEND / root).rglob("*.tsx")):
            src = p.read_text(encoding="utf-8")
            for w in re.findall(r'<Table\b[^>]*\bminWidth="([^"]+)"', src):
                assert w in keys, f"{p}: minWidth={w} has no MIN_WIDTH entry"
            # One source for the number: a call site never restates it.
            assert not re.search(r'<Table\b[^>]*className="[^"]*min-w-\[', src), p


def test_the_tracker_toolbar_and_header_stick():
    assert "<ListToolbar>" in _TRACKER
    # A direct child of the page's <main>: no wrapper that could scroll or end early.
    shell = _TRACKER[_TRACKER.index("<PageShell>") : _TRACKER.index("<ListToolbar>")]
    assert "<div" not in shell
    assert '<Table minWidth="52rem" stickyHeader className="table-fixed">' in _TRACKER


def test_referrals_header_sticks():
    assert '<Table minWidth="48rem" stickyHeader className="table-fixed">' in _REFERRALS


def test_the_tracker_search_is_the_shared_list_search():
    """One list search box (planner decision 16, Q12): Applications and the
    Agent inbox render the same component, so the two never drift."""
    assert 'placeholder="Search company or role…"' in _SEARCH
    assert "aria-label={label}" in _SEARCH
    toolbar = _TRACKER[_TRACKER.index("<ListToolbar>") : _TRACKER.index("</ListToolbar>")]
    assert '<ListSearch label="Search applications" value={q} onChange={setQ} />' in toolbar
    # No second copy of the box left behind in the page.
    assert "placeholder=" not in _TRACKER
    assert "<Input" not in _TRACKER


# ── A capped list says so ───────────────────────────────────────────────────


def _backend_fn(rel: str, fn: str) -> str:
    src = (_ROOT / "backend" / rel).read_text(encoding="utf-8")
    i = src.index(f"def {fn}(")
    return src[i : src.index("\n\n\n", i)]


def _backend_limit(rel: str, fn: str) -> tuple[int, int]:
    """(le=, default) of the endpoint's `limit` query parameter."""
    m = re.search(
        r"limit: Annotated\[int, Query\(ge=1, le=(\d+)\)\] = (\d+)", _backend_fn(rel, fn)
    )
    assert m, f"{fn}: limit parameter"
    return int(m.group(1)), int(m.group(2))


def test_the_cap_rule_is_pure_and_exact_when_the_server_counts():
    src = _read("lib/list-cap.ts")
    assert "import " not in src  # node --test runs it as-is (appendix F finding 7)
    assert "return total != null ? total > loaded : loaded >= limit;" in src
    assert (_FRONTEND / "lib/list-cap.test.ts").is_file()


def test_a_whole_list_shows_no_notice():
    body = _body(_read("components/list-cap-notice.tsx"), "export function ListCapNotice(")
    assert "const sentence = listCapSentence(cap);\n  if (!sentence) return null;\n  return (" in body


def test_the_notice_is_plain_text_not_a_live_region():
    src = _read("components/list-cap-notice.tsx")
    assert "listCapSentence(cap)" in src and "<p" in src
    assert "role=" not in src and "aria-live" not in src


def test_the_tracker_asks_for_one_limit_the_api_accepts():
    m = re.search(r"^const LIST_LIMIT = (\d+);", _TRACKER, re.M)
    assert m, "LIST_LIMIT"
    limit = int(m.group(1))
    # Above the API's max, the request is a 422 and the tracker shows its error.
    assert limit <= _backend_limit("app/routers/applications.py", "list_applications")[0]
    assert limit <= _backend_limit("app/routers/jobs.py", "list_jobs")[0]
    assert "/api/applications?limit=${LIST_LIMIT}" in _TRACKER
    assert "/api/jobs?without_application=true&source=${savedSource}&limit=${LIST_LIMIT}" in _TRACKER
    assert "limit=500" not in _TRACKER


def test_a_busy_hunt_cannot_push_the_users_saved_jobs_out():
    """Planner decision 17 (O4): one mixed page of 500 saved jobs counted agent
    captures, so an active hunt pushed the user's own saved jobs out of it.
    The user's saved jobs and the agents' captures are fetched apart, keyed
    by the source the toggle shows."""
    assert 'const savedSource = source === "agent" ? "agent" : "user";' in _TRACKER
    assert 'queryKey: ["jobs", "without-application", savedSource],' in _TRACKER
    # The server filters now; the client no longer splits one mixed page.
    assert 'job.source !== "agent"' not in _TRACKER
    assert 'job.source === "agent"' not in _TRACKER
    assert 'source: Literal["user", "agent"] | None' in _backend_fn("app/routers/jobs.py", "list_jobs")


def test_the_agents_list_is_fetched_before_the_first_switch():
    """Hover or focus on the Agents segment prefetches its saved jobs through
    the same query definition the list uses, so switching shows rows, not a
    skeleton."""
    toggle = _read("components/source-toggle.tsx")
    assert "onPointerEnter={() => onPreview?.(s)}" in toggle
    assert "onFocus={() => onPreview?.(s)}" in toggle
    assert "const savedJobs = useQuery(savedJobsQuery(savedSource));" in _TRACKER
    assert 'if (next === "agent") void qc.prefetchQuery(savedJobsQuery("agent"));' in _TRACKER


def _caps() -> str:
    caps = _TRACKER[_TRACKER.index("const caps = [") :]
    return caps[: caps.index("].filter(isListCapped);")]


def test_a_capped_tracker_says_so_at_the_end_of_the_list():
    assert "<ListCapNotice" in _TRACKER[_TRACKER.index("</TableFrame>") :]
    gate = _TRACKER[_TRACKER.index("{!loading && !loadFailed && caps.length > 0 ? (") :]
    assert gate.index("<ListCapNotice") < gate.index("</PageShell>")
    caps = _caps()
    # What is LOADED, before any filter: never `filtered` or `sourceScopedRows`.
    assert "apps.data?.length ?? 0" in caps and "savedJobs.data?.length ?? 0" in caps
    assert "filtered" not in caps and "sourceScoped" not in caps


def test_each_cap_is_measured_against_the_limit_it_asked_for():
    """The rule is `loaded >= limit`: a limit other than the one sent would
    say rows are missing when none are, or miss a full page."""
    caps = _caps()
    assert caps.count("limit: LIST_LIMIT") == 2
    assert caps.count("limit:") == 2


def test_each_cap_names_the_rows_it_counts():
    caps = _caps()
    assert 'noun: "applications" }' in caps
    assert 'noun: savedSource === "agent" ? "jobs from connected agents" : "saved jobs",' in caps


def test_the_tracker_renders_each_cap_once_as_computed():
    """One notice, at the end, with the cap unchanged: a `loaded` override
    (say, the filtered count) would make it lie under a filter."""
    assert _TRACKER.count("<ListCapNotice") == 1
    assert re.search(
        r"\{caps\.map\(\(cap\) => \(\s*<ListCapNotice key=\{cap\.noun\} \{\.\.\.cap\} />\s*\)\)\}",
        _TRACKER,
    )


def test_the_draft_inbox_asks_for_its_limit_explicitly():
    """listKbDrafts sends KB_DRAFTS_LIMIT, one the API accepts, instead of
    relying on the server's default page, and the inbox reads the same
    constant. The API returns the OLDEST drafts first."""
    api = _read("lib/api.ts")
    m = re.search(r"^export const KB_DRAFTS_LIMIT = (\d+);", api, re.M)
    assert m, "KB_DRAFTS_LIMIT"
    assert int(m.group(1)) <= _backend_limit("app/routers/career_kb.py", "list_points")[0]
    assert "apiFetch<KBInboxPoint[]>(`/api/kb/points?state=draft&limit=${KB_DRAFTS_LIMIT}`)" in api
    assert ".order_by(KBPoint.created_at, KBPoint.id)" in _backend_fn(
        "app/routers/career_kb.py", "list_points"
    )


def test_the_draft_inbox_says_when_it_is_cut_off():
    """Planner decision 17 (O8). Oldest first, so the rows left out are the
    newer ones, and the notice says so. Not after a failed load: no rows
    loaded is not a cut-off list."""
    src = _read("components/career/inbox-panel.tsx")
    assert re.search(r'import \{[^}]*\bKB_DRAFTS_LIMIT\b[^}]*\} from "@/lib/api";', src)
    assert "const KB_DRAFTS_LIMIT" not in src
    assert re.search(
        r"\{!isLoading && !error \? \(\s*"
        r'<ListCapNotice loaded=\{drafts\.length\} limit=\{KB_DRAFTS_LIMIT\} noun="draft bullets" order="oldest" />',
        src,
    )
