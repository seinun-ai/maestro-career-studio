"""Pins: the Agent inbox (docs/plans/2026-09-23-ux-ia-appendix-a-agent-inbox.md).

The page is named for what it is, keeps one number from the funnel, filters
in one row like Applications, says who can file a proposal when there are
none, admits a cut list, and names who filed each proposal. Node tests cover
lib/needs-you.ts, lib/inbox-filter.ts and lib/agent-name.ts; they are not in
CI, so the branches that matter are pinned here.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND = _ROOT / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


_PAGE = _read("app/proposals/page.tsx")
_SECTION = _read("components/proposals/proposals-section.tsx")
_JOB = _read("app/jobs/[id]/page.tsx")
_PANEL = _read("components/proposals/proposal-agent-panel.tsx")
_TRIAGE = _read("components/proposals/triage-actions.tsx")
_TRACKER = _read("app/applications/page.tsx")


def _name() -> str:
    return _read("lib/agent-name.ts")


# ── A1: the page is called Agent inbox ──────────────────────────────────────


def test_the_inbox_is_called_agent_inbox_wherever_it_is_named():
    assert 'title="Agent inbox"' in _PAGE
    assert "Jobs your connected agents found. Nothing is submitted without your yes." in _PAGE
    assert 'fromProposals ? "Back to Agent inbox" : "Back to applications"' in _JOB
    assert '"Previous job in Agent inbox"' in _JOB
    assert '"Next job in Agent inbox"' in _JOB
    assert "Open Agent inbox" in _PANEL
    assert 'title="Couldn\'t load your Agent inbox."' in _SECTION


def test_the_old_names_are_gone():
    for rel, src in (("page", _PAGE), ("job", _JOB), ("panel", _PANEL), ("section", _SECTION)):
        for old in ("Agent Proposals", "Agent proposals", "agent proposals", "Back to proposals",
                    "proposal in list", "All proposals"):
            assert old not in src, f"{rel}: {old!r}"


def test_the_url_and_its_session_keys_stay():
    """Deep links, ?from=proposals and cs-proposals-seq are the frozen surface."""
    assert 'const SEQUENCE_STORE_KEY = "cs-proposals-seq";' in _SECTION
    assert "href={`/jobs/${proposal.job_id}?from=proposals`}" in _SECTION
    assert 'readSequence(fromProposals ? "cs-proposals-seq" : "cs-tracker-seq")' in _JOB


def test_the_lanes_use_the_owners_words():
    """Needs you · To review · Queued · Applying · History (planner decision 20)."""
    titles = re.findall(r"<Lane title=\{`([^$`]+) · \$\{", _SECTION)
    assert titles == ["Needs you", "To review", "Queued", "Applying"]
    assert "Nothing to review." in _SECTION
    history = _SECTION.index("History ·")
    assert _SECTION.index('title={`Applying · ') < history
    for old in ("Triage ·", "In flight ·", "pending triage"):
        assert old not in _SECTION, old


# ── A2: the funnel leaves; Cap today stays in the header ────────────────────


def test_the_funnel_strip_is_gone():
    assert not (_FRONTEND / "components/proposals/funnel-strip.tsx").exists()
    for root in ("app", "components"):
        for path in (_FRONTEND / root).rglob("*.tsx"):
            assert "FunnelStrip" not in path.read_text(encoding="utf-8"), path


def test_the_header_keeps_only_cap_today():
    assert "<CapToday />" in _PAGE
    cap = _read("components/proposals/cap-today.tsx")
    assert "useProposalFunnel()" in cap
    # The failure is its own state, decided before the readout.
    assert cap.index("if (isLoadFailure(query))") < cap.index(
        "Cap today {cap.reserved_last_24h}/{cap.max_per_day}"
    )
    assert "used in the last 24 hours" in cap  # "today" is a rolling window
    # Seen, not read twice: the ratio is hidden and the words are spoken.
    readout = cap[cap.index("Cap today {") - 200 :]
    assert readout.index('aria-hidden="true"') < readout.index("Cap today {")
    hook = _read("hooks/use-proposal-funnel.ts")
    assert 'queryKey: ["proposals", "funnel"]' in hook
    pipeline = _read("components/analytics/agent-pipeline-card.tsx")
    assert "useProposalFunnel()" in pipeline
    assert "useQuery(" not in pipeline  # one definition of the funnel query


def test_the_pipeline_card_says_queued_and_connected_agents():
    """A5 rows 31 and 32: the stage the inbox calls Queued, and no swarm."""
    pipeline = _read("components/analytics/agent-pipeline-card.tsx")
    assert '{ key: "accepted", label: "Queued"' in pipeline
    assert "Jobs your connected agents saved, and how far each one got." in pipeline
    assert "hunt swarm" not in pipeline
    assert 'label: "Accepted"' not in pipeline


# ── A3: a toolbar like Applications' ────────────────────────────────────────


def _toolbar() -> str:
    return _SECTION[_SECTION.index("<ListToolbar>") : _SECTION.index("</ListToolbar>")]


def test_the_toolbar_is_one_row_like_applications():
    toolbar = _toolbar()
    triggers = re.findall(
        r'<SelectTrigger\s+className="([^"]*)"\s+aria-label="([^"]+)"', toolbar
    )
    assert [label for _, label in triggers] == ["Sort", "Role", "Job board", "Minimum score"]
    assert all("h-8" in cls.split() and "rounded-full" in cls.split() for cls, _ in triggers)
    # No caption stacked over a control, and no free-number field.
    assert "grid gap-1" not in toolbar
    assert "<Input" not in toolbar
    assert 'placeholder="e.g. 50"' not in _SECTION


def test_the_sort_values_describe_themselves():
    for label in ('score: "Best score first"', 'newest: "Newest first"',
                  'role: "Role A–Z"', 'company: "Company A–Z"'):
        assert label in _SECTION, label


def test_the_search_box_is_the_shared_one():
    assert '<ListSearch label="Search the Agent inbox" value={q} onChange={setQ} />' in _toolbar()


def test_the_role_filter_names_roles_not_keys():
    assert "{roleLabel(r)}" in _SECTION
    assert 'role === "all" ? "All roles" : roleLabel(role)' in _SECTION
    assert not re.search(r"^\s*\{r\}\s*$", _SECTION, re.M)


def test_filtering_is_one_pure_function():
    lib = _read("lib/inbox-filter.ts")
    assert not re.search(r"^import (?!type )", lib, re.M)  # node --test loads it
    assert "export const SCORE_FLOORS = [50, 60, 70, 80] as const;" in lib
    assert "`${p.job.company ?? \"\"} ${p.job.title ?? \"\"}`.toLowerCase().includes(needle)" in lib
    assert "const needle = q.trim().toLowerCase();" in lib
    assert "if (score == null || score < minScore) return false;" in lib
    assert "filterProposals(items, { q, role, board, minScore })" in _SECTION
    for helper in ("function filterProposals", "function chosenScore", "function boardHost"):
        assert helper not in _SECTION, helper  # one definition, in the lib


def test_a_filter_that_hides_everything_says_so():
    assert "const nothingMatches = filtered.length === 0;" in _SECTION
    main = _SECTION[_SECTION.index("</ListToolbar>") :]
    assert main.index("{nothingMatches ? (") < main.index('title="Nothing matches these filters"')


def test_the_toolbar_sticks_and_the_lanes_are_its_later_siblings():
    """B8 and lane 2's selector contract: globals.css clears focus only for
    `[data-slot="list-toolbar"] ~ :focus-within`, so every lane must be a later
    sibling of the toolbar, never inside it or a wrapper around both."""
    root = _SECTION[_SECTION.index('<div className="flex flex-col gap-6 pb-20">') :]
    assert root.index("<ListToolbar>") < root.index("</ListToolbar>") < root.index("{nothingMatches ? (")
    assert root.index("{nothingMatches ? (") < root.index("<Lane")
    assert "ListToolbar" not in _SECTION[_SECTION.index("function Lane(") :]
    # The lanes sit in a fragment, so they stay siblings of the toolbar.
    assert root[root.index("{nothingMatches ? (") :].index(") : (\n        <>") > 0


def test_the_bulk_bar_leaves_room_below_a_focused_row():
    """O7: the fixed bulk bar covered a focused row (WCAG 2.4.11). Scoped like
    the toolbar's clearance, so focus in the toolbar or a dialog never jumps."""
    assert 'data-slot="bulk-bar"' in _TRIAGE[_TRIAGE.index("export function BulkBar(") :]
    css = _read("app/globals.css")
    rule = css[css.index('html:has([data-slot="bulk-bar"])') :]
    rule = rule[: rule.index("}")]
    assert ':has([data-slot="list-toolbar"] ~ :focus-within)' in rule
    assert "scroll-padding-bottom: 5rem;" in rule


# ── A6: the empty state ─────────────────────────────────────────────────────


def _github_slug(heading: str) -> str:
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def test_an_empty_inbox_says_where_proposals_come_from():
    empty = _SECTION[_SECTION.index("if (items.length === 0) {") : _SECTION.index("const rowProps")]
    assert 'title="No proposals yet"' in empty
    assert "never from the app itself. Nothing is submitted without your yes." in empty
    assert "href={JOB_HUNT_SKILL_URL}" in empty
    assert "href={AGENT_APPLICATIONS_URL}" in empty
    assert empty.count('target="_blank" rel="noopener noreferrer"') == 2
    assert "<Link href={CONNECTED_AGENTS_SETTINGS}>" in empty
    assert "ListToolbar" not in empty and "ListCapNotice" not in empty


def test_the_empty_state_links_point_at_real_headings():
    links = _read("lib/agent-links.ts")
    assert not re.search(r"^import ", links, re.M)
    readme = (_ROOT / "README.md").read_text(encoding="utf-8")
    heading = re.search(r"^### (Going all the way: .+)$", readme, re.M).group(1)
    assert f"/README.md#{_github_slug(heading)}`" in links
    assert (_ROOT / "docs/skills/README.md").exists()
    assert "/docs/skills/README.md`" in links
    assert 'export const CONNECTED_AGENTS_SETTINGS = "/settings?tab=agents";' in links
    tabs = _read("lib/settings-tabs.ts")
    assert 'value: "agents",' in tabs, "the Connected agents tab id moved"


# ── A7: a cut list says so ──────────────────────────────────────────────────


def test_the_inbox_asks_for_one_limit_and_names_the_server_total():
    assert "const PROPOSALS_LIMIT = 500;" in _SECTION
    assert "`/api/proposals?limit=${PROPOSALS_LIMIT}`" in _SECTION
    assert "limit=500" not in _SECTION
    router = (_ROOT / "backend/app/routers/proposals.py").read_text(encoding="utf-8")
    le = int(re.search(r"limit: Annotated\[int, Query\(ge=1, le=(\d+)\)\]", router).group(1))
    assert 500 <= le


def test_the_inbox_says_at_its_end_when_the_list_was_cut():
    notice = _SECTION.index(
        '<ListCapNotice loaded={items.length} limit={PROPOSALS_LIMIT} total={data?.total} noun="proposals" />'
    )
    assert _SECTION.index("History ·") < notice < _SECTION.index("<BulkBar")


# ── A9: who proposed it ─────────────────────────────────────────────────────


def test_every_proposal_surface_names_who_filed_it():
    assert "{proposalByLine(proposal.proposed_by)} · {formatTimeAgo(proposal.created_at)}" in _SECTION
    assert "<CardTitle>{proposalByLine(data.proposed_by)}</CardTitle>" in _PANEL
    assert '<Fact label="Date">' in _PANEL and '<Fact label="Proposed">' not in _PANEL
    assert "title={proposalByLine(job.proposal_proposed_by)}" in _JOB
    pill = _JOB[_JOB.index("title={proposalByLine(job.proposal_proposed_by)}") :]
    assert pill.index('<span className="sr-only">') < pill.index("{STATUS_LABELS[proposalStatus]}")
    assert "{proposalByLine(job.proposal_proposed_by)}, status" in pill


def test_the_tracker_mark_names_the_filer_in_words_a_reader_hears():
    assert "agentMarkLabel(" in _TRACKER
    assert "Found by agent" not in _TRACKER
    mark = _TRACKER[_TRACKER.index("title={mark}") :]
    assert mark.index('aria-hidden="true"') < mark.index('<span className="sr-only">{mark}</span>')


def test_the_filer_words_live_in_one_mapper():
    _NAME = _name()
    assert not re.search(r"^import ", _NAME, re.M)
    assert 'if (proposedBy === "you") return "Queued by you";' in _NAME
    assert '`Proposed by ${agentDisplayName(proposedBy) ?? "a connected agent"}`' in _NAME
    assert 'return name ? `Proposed by ${name}` : "Found by a connected agent";' in _NAME
    # Known clients by product, an unknown one title-cased, never a slug.
    for known in ('"Claude"', '"Codex"', '"ChatGPT"'):
        assert known in _NAME, known
    assert ".split(/[-_\\s]+/)" in _NAME


def test_the_types_carry_the_filer_optionally():
    types = _read("lib/types.ts")
    job = types[types.index("export interface Job {") :]
    assert "proposal_proposed_by?: string | null;" in job[: job.index("\n}\n")]
    proposal = types[types.index("export interface Proposal {") :]
    assert "proposed_by?: string | null;" in proposal[: proposal.index("\n}\n")]


def test_a_queue_that_joins_an_agents_proposal_says_whose_it_stays():
    """The POST keeps the first filer, so a web Queue on a job an agent had
    just proposed still reads "Proposed by <agent>". The toast says so."""
    _NAME = _name()
    assert 'export function queuedToast(proposedBy: string | null | undefined): string {' in _NAME
    toast = _NAME[_NAME.index("export function queuedToast(") :]
    assert '"Queued in your Agent inbox."' in toast
    assert "proposed it first" in toast
    api = _read("lib/api.ts")
    promote = api[api.index("export async function promoteJobToAgentQueue") :]
    promote = promote[: promote.index("\n}\n")]
    assert "return prop.proposed_by;" in promote
    for src in (_JOB, _TRACKER):
        assert "toast.success(queuedToast(proposedBy))" in src
        assert "Queued for the next apply run" not in src


def test_queue_and_accept_say_queued():
    """Decision 19: the result of Accept is a Queued chip, so its words say Queued."""
    assert 'toast.success("Queued. A connected agent can apply to it now.")' in _JOB
    assert "Accepted —" not in _JOB
    assert '{promote.isPending ? "Queueing…" : "Queue in Agent inbox"}' in _JOB
    assert 'label="Queue in Agent inbox"' in _TRACKER
    assert "<SelectLabel>Agent inbox</SelectLabel>" in _TRACKER
    for old in ("Queue for agent apply", "Agent lane<"):
        assert old not in _TRACKER, old


def test_a_bulk_queue_that_partly_fails_says_queued():
    bulk = _TRIAGE[_TRIAGE.index("onSuccess: (data, vars) => {") :]
    bulk = bulk[: bulk.index("onError")]
    assert '"queued" : "skipped"' in bulk
    assert "could not be ${verb}: ${sample}" in bulk
    assert " — " not in bulk


def test_a_narrow_row_wraps_instead_of_hiding_its_title():
    """Browser-found at 768 and 375: the row was `flex` with a `flex-1`
    (basis 0) text block beside shrink-0 chips, so the title and by-line
    shrank to a few letters, or to nothing, in the To review lane."""
    row = _SECTION[_SECTION.index("function ProposalRow(") :]
    link = row[row.index("<Link") : row.index("</Link>")]
    own = re.search(r'className="([^"]*)"', link).group(1).split()  # the Link's own classes
    assert "flex-wrap" in own and "flex-1" in own
    assert '<div className="min-w-0 grow basis-[10rem]">' in link
    assert '<div className="min-w-0 flex-1">' not in link


# ── A4: a Needs-you count on the sidebar item ───────────────────────────────


def _sidebar() -> str:
    return _read("components/app-sidebar.tsx")


def test_the_sidebar_names_the_inbox_and_the_assistant():
    """A1 and decision 5: the inbox item and the in-app chat's item."""
    sidebar = _sidebar()
    assert '{ href: "/proposals", label: "Agent inbox", icon: Bot },' in sidebar
    assert '{ href: "/chat", label: "Assistant", icon: MessageSquare },' in sidebar
    for old in ('label: "Agent Proposals"', 'label: "Chat"'):
        assert old not in sidebar, old


def test_needs_you_is_one_list_of_statuses():
    lib = _read("lib/needs-you.ts")
    assert (
        'export const NEEDS_YOU_STATUSES: readonly ProposalStatus[] = ["needs_decision", "needs_human"];'
        in lib
    )
    assert "const NEEDS_YOU = NEEDS_YOU_STATUSES;" in _SECTION
    hook = _read("hooks/use-needs-you-count.ts")
    assert '`/api/proposals?status=${NEEDS_YOU_STATUSES.join(",")}&limit=1`' in hook
    assert "select: (page) => page.total" in hook
    # Under ["proposals"]: every triage invalidation refreshes the count.
    assert 'queryKey: ["proposals", "needs-you-count"]' in hook
    assert "refetchInterval: 60_000" in hook


def test_the_badge_hides_at_zero_and_caps_at_99():
    lib = _read("lib/needs-you.ts")
    assert "if (count == null || !Number.isFinite(count) || count < 1) return null;" in lib
    assert 'text: n > 99 ? "99+" : String(n),' in lib
    assert '`${n} ${n === 1 ? "needs" : "need"} you`' in lib


def test_the_count_is_in_the_link_name_and_not_read_twice():
    sidebar = _sidebar()
    assert "const needsYou = needsYouBadge(useNeedsYouCount());" in sidebar
    assert 'badges={{ "/proposals": needsYou }}' in sidebar
    # The words are the link's name. Browser-found: an sr-only span, out of
    # flow, made Chrome's name "Agent inbox , 3 need you".
    assert "aria-label={badge ? `${item.label}, ${badge.spoken}` : undefined}" in sidebar
    assert '<span className="min-w-0 truncate">{item.label}</span>' in sidebar
    pill = sidebar[sidebar.index("{badge ? (") :]
    assert pill.index('aria-hidden="true"') < pill.index("{badge.text}")
