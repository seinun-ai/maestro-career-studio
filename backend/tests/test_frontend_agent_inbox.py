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
    titles = re.findall(r"<Lane\s+(?:ref=\{\w+\}\s+)?title=\{`([^$`]+) · \$\{", _SECTION)
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
        "Applications per day: {cap.reserved_last_24h} of {cap.max_per_day} used in the last 24 hours"
    )
    # One line, seen and spoken the same: "today" was a rolling window, so it says the last 24 hours.
    assert "sr-only" not in cap and "Cap today" not in cap
    hook = _read("hooks/use-proposal-funnel.ts")
    assert 'queryKey: ["proposals", "funnel"]' in hook
    pipeline = _read("components/analytics/agent-pipeline-card.tsx")
    assert "useProposalFunnel()" in pipeline
    assert "useQuery(" not in pipeline  # one definition of the funnel query


def test_the_pipeline_card_says_queued_and_connected_agents():
    """A5 rows 31 and 32: the stage the inbox calls Queued, and no swarm."""
    pipeline = _read("components/analytics/agent-pipeline-card.tsx")
    assert '{ key: "accepted", label: "Queued"' in pipeline
    # The funnel counts where each job IS (current statuses), not how far it once got.
    assert "Where your connected agents' jobs stand now." in pipeline
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
                  'title: "Job title A–Z"', 'company: "Company A–Z"'):
        assert label in _SECTION, label
    # It sorts by job title, not by the Role filter's role category: its label says so.
    assert 'case "title":\n        return (a.job.title ?? "").localeCompare(b.job.title ?? "");' in _SECTION
    assert "Role A–Z" not in _SECTION


def test_the_filters_share_a_line_on_a_phone_where_they_fit():
    """At 375 min-w-[10rem] put the four pills one per line. Below sm they
    take their own width and grow into the line: two to a line at 375, and a
    long value (a board's host) wraps to its own line instead of clipping."""
    toolbar = _toolbar()
    assert '<div className="flex flex-wrap items-center gap-1.5">' in toolbar
    for cls, label in re.findall(r'<SelectTrigger\s+className="([^"]*)"\s+aria-label="([^"]+)"', toolbar):
        classes = cls.split()
        assert {"shrink-0", "grow", "sm:grow-0"} <= set(classes), label
        assert not [c for c in classes if c.startswith("min-w-")], label  # only from sm up


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
    assert rule.startswith('html:has([data-slot="bulk-bar"]):has([data-slot="list-toolbar"] ~ :focus-within) {')  # M24
    rule = rule[: rule.index("}")]
    assert "scroll-padding-bottom: 5rem;" in rule


# ── A6: the empty state ─────────────────────────────────────────────────────


def _github_slug(heading: str) -> str:
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def test_an_empty_inbox_says_where_proposals_come_from():
    empty = _SECTION[_SECTION.index("if (items.length === 0) {") : _SECTION.index("const rowProps")]
    assert 'title="No proposals yet"' in empty
    assert "The app never proposes jobs itself." in empty
    assert "href={JOB_HUNT_SKILL_URL}" in empty
    assert "href={AGENT_APPLICATIONS_URL}" in empty
    assert empty.count('target="_blank" rel="noopener noreferrer"') == 2
    assert '<Link href={CONNECTED_AGENTS_SETTINGS} className={buttonVariants({ variant: "ghost" })}>' in empty
    assert "ListToolbar" not in empty and "ListCapNotice" not in empty


def test_the_empty_states_links_are_announced_as_links():
    """I1: `Button nativeButton={false} render={<a>}` gives a link role="button"."""
    empty = _SECTION[_SECTION.index("if (items.length === 0) {") : _SECTION.index("const rowProps")]
    assert "nativeButton={false}" not in empty and "<Button" not in empty
    assert (
        '<a href={JOB_HUNT_SKILL_URL} target="_blank" rel="noopener noreferrer" '
        'className={cn(buttonVariants(), "h-auto min-h-8 max-w-full py-1.5 whitespace-normal")}>'
    ) in empty
    assert (
        '<a href={AGENT_APPLICATIONS_URL} target="_blank" rel="noopener noreferrer" '
        'className={buttonVariants({ variant: "ghost" })}>'
    ) in empty


def test_the_empty_state_links_point_at_real_headings():
    """Every guide link in lib/agent-links.ts (the empty state's two and the
    Connected agents card's three). A renamed section fails here instead of
    breaking a link."""
    links = _read("lib/agent-links.ts")
    assert not re.search(r"^import ", links, re.M)
    readme = (_ROOT / "README.md").read_text(encoding="utf-8")
    heading = re.search(r"^### (Going all the way: .+)$", readme, re.M).group(1)
    assert f"/README.md#{_github_slug(heading)}`" in links
    guide = (_ROOT / "docs/GETTING_STARTED.md").read_text(encoding="utf-8")
    step = re.search(r"^## (5\. Connect .+)$", guide, re.M).group(1)
    assert f"/docs/GETTING_STARTED.md#{_github_slug(step)}`" in links
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
    # After the lanes' ternary, not inside it: a filter that hides every row still says the list was cut (M10).
    assert "          </section>\n        </>\n      )}\n\n      <ListCapNotice" in _SECTION


# ── A9: who proposed it ─────────────────────────────────────────────────────


def test_every_proposal_surface_names_who_filed_it():
    row = _SECTION[_SECTION.index("function ProposalRow(") :]
    assert "const byLine = proposalByLine(proposal.proposed_by, proposal.status);" in row
    assert 'const meta = [byLine, formatTimeAgo(proposal.created_at)].filter(Boolean).join(" · ");' in row
    # It truncates in a narrow row: the whole of it on hover.
    assert '<div className="text-muted-foreground truncate text-xs" title={meta}>' in row
    assert '<CardTitle>{proposalByLine(data.proposed_by, data.status) ?? "Agent inbox"}</CardTitle>' in _PANEL
    assert "Proposed {formatShortDate(data.created_at)}" in _PANEL and '<Fact label="Proposed">' not in _PANEL
    assert "? proposalByLine(job.proposal_proposed_by, proposalStatus) : null;" in _JOB
    pill = _JOB[_JOB.index("title={proposalBy ?? undefined}") :]
    assert pill.index('<span className="sr-only">{proposalBy}, status </span>') < pill.index(
        "{STATUS_LABELS[proposalStatus]}"
    )


def test_the_tracker_mark_names_the_filer_in_words_a_reader_hears():
    # Only a saved job carries its newest proposal's filer (M7). An application is "agent"
    # only because a proposal was linked to it (routers/proposals.py
    # `_validate_and_stamp_application`): "Found by a connected agent" was false for one you made.
    assert (
        'r.kind === "saved"\n                    ? agentMarkLabel(r.job.proposal_proposed_by)\n'
        "                    : LINKED_APPLICATION_MARK;"
    ) in _TRACKER
    assert 'export const LINKED_APPLICATION_MARK = "Linked to a proposal in Agent inbox";' in _name()
    assert "Found by agent" not in _TRACKER
    mark = _TRACKER[_TRACKER.index("title={mark}") :]
    assert mark.index('aria-hidden="true"') < mark.index('<span className="sr-only">{mark}</span>')


def test_the_filer_words_live_in_one_mapper():
    _NAME = _name()
    assert not re.search(r"^import ", _NAME, re.M)
    assert 'if (proposedBy === "you") return NEVER_QUEUED.has(status) ? "Proposed by you" : "Queued by you";' in _NAME
    assert 'const NEVER_QUEUED = new Set(["pending_review", "needs_decision", "expired"]);' in _NAME
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
    assert "export function queuedToast({ proposedBy, status }: QueueResult): string {" in _NAME
    toast = _NAME[_NAME.index("export function queuedToast(") :]
    assert '"Queued in your Agent inbox."' in toast
    assert "proposed it first" in toast
    for src in (_JOB, _TRACKER):
        assert "toast.success(queuedToast(queue))" in src
        assert "Queued for the next apply run" not in src


def _promote() -> str:
    api = _read("lib/api.ts")
    promote = api[api.index("export async function promoteJobToAgentQueue") :]
    return promote[: promote.index("\n}\n")]


def test_a_queue_accepts_only_from_where_the_backend_does():
    """I2: an agent's proposal that needs you, or is already queued or being
    applied to, came back from the POST; accepting it was an illegal
    transition ("cannot go needs_decision -> accepted") and the job stayed
    unqueued with no refresh."""
    from app.services.proposals import ALLOWED

    assert {src for src, nxt in ALLOWED.items() if "accepted" in nxt} == {"pending_review"}
    promote = _promote()
    assert 'if (prop.status === "pending_review") {' in promote
    guarded = promote[promote.index('if (prop.status === "pending_review") {') :]
    guarded = guarded[: guarded.index("\n  }\n")]
    assert 'method: "PATCH"' in guarded
    assert "return" not in guarded  # M23: the PATCH is never skipped for an agent's proposal
    assert "return { proposedBy: prop.proposed_by, status: prop.status };" in promote


def test_the_queue_toast_words_every_open_status():
    """Whatever the POST can hand back (an open proposal) has words."""
    from app.services.proposals import OPEN_STATUSES

    toast = _name()
    already = toast[toast.index("const ALREADY:") :]
    already = already[: already.index("\n};\n")]
    worded = dict(re.findall(r'^  (\w+): "([^"]+)",$', already, re.M))
    assert set(worded) == set(OPEN_STATUSES) - {"pending_review"}
    assert worded == {"needs_decision": "it needs you", "needs_human": "it needs you",
                      "accepted": "it's already queued", "approved": "it's being applied to"}


def test_a_queue_refreshes_whatever_happened():
    """A failed or declined accept still filed or found a proposal: the page
    must show it."""
    for src in (_JOB, _TRACKER):
        promote = src[src.index("=> promoteJobToAgentQueue(") :]
        promote = promote[: promote.index("\n  });")]
        settled = promote[promote.index("onSettled: () => {") :]
        assert 'qc.invalidateQueries({ queryKey: ["proposals"] });' in settled
        assert "onSuccess: (queue) => toast.success(queuedToast(queue))," in promote


def test_queue_is_the_word_for_what_becomes_queued():
    """Decision 19, D2.7 and D2.2: the row's, the bar's and the job header's
    button make a Queued chip, so they say Queue."""
    row = _SECTION[_SECTION.index("function ProposalRow(") :]
    assert 'label="Queue"' in row and 'label="Accept"' not in row
    bar = _TRIAGE[_TRIAGE.index("export function BulkBar(") :]
    assert "\n          Queue\n        </Button>" in bar and "Accept" not in bar
    assert "\n                Queue\n              </Button>" in _JOB
    assert "\n                Accept\n              </Button>" not in _JOB


def test_history_and_the_pipeline_use_the_owners_chip_words():
    """D §0: Applied (not Submitted), Check if sent (not Submission uncertain), Found (not Captured)."""
    chip = _read("components/status-chip.tsx")
    assert 'submitted: { label: "Applied",' in chip
    assert 'submission_uncertain: { label: "Check if sent",' in chip
    pipeline = _read("components/analytics/agent-pipeline-card.tsx")
    assert '{ key: "captured", label: "Found" },' in pipeline
    assert '{ key: "submitted", label: "Applied" },' in pipeline
    for old in ('"Captured"', '"Submitted"'):
        assert old not in pipeline, old
    for old in ('label: "Submitted"', 'label: "Submission uncertain"'):
        assert old not in chip, old


def test_a_row_checkbox_names_its_job():
    row = _SECTION[_SECTION.index("function ProposalRow(") :]
    assert 'aria-label={`Select ${job.title ?? "Untitled role"}${job.company ? ` at ${job.company}` : ""}`}' in row


def test_queue_and_accept_say_queued():
    """Decision 19: the result of Accept is a Queued chip, so its words say Queued."""
    assert 'toast.success("Queued. A connected agent can apply to it now.")' in _JOB
    assert "Accepted —" not in _JOB
    assert '{promote.isPending ? "Queueing…" : "Queue in Agent inbox"}' in _JOB
    assert 'label="Queue in Agent inbox"' in _TRACKER
    assert "<SelectLabel>Agent inbox</SelectLabel>" in _TRACKER
    for old in ("Queue for agent apply", "Agent lane<"):
        assert old not in _TRACKER, old


def test_a_bulk_queue_that_partly_fails_says_queue():
    """The toast names the verb the inbox uses (Queue), and a server reason
    only when it is a sentence for the user (D §2.7)."""
    bulk = _TRIAGE[_TRIAGE.index("onSuccess: (data, vars) => {") :]
    bulk = bulk[: bulk.index("onError")]
    assert '"queue" : "skip"' in bulk
    assert "`Couldn't ${verb} ${failed.length} of ${vars.ids.length}. ${why}`" in bulk
    assert 'const why = isPlainSentence(sample) ? sample : "Try again.";' in bulk
    assert "could not be" not in bulk
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
    lanes = _read("lib/inbox-lanes.ts")
    assert "export const NEEDS_YOU_STATUSES = INBOX_LANES.needs_you;" in lanes
    assert 'inLane(filtered, "needs_you")' in _SECTION
    hook = _read("hooks/use-needs-you-count.ts")
    assert 'import { NEEDS_YOU_STATUSES } from "@/lib/inbox-lanes";' in hook
    assert '`/api/proposals?status=${NEEDS_YOU_STATUSES.join(",")}&limit=1`' in hook
    assert "select: (page) => page.total" in hook
    # Under ["proposals"]: every triage invalidation refreshes the count.
    assert 'queryKey: ["proposals", "needs-you-count"]' in hook


def test_the_count_polls_every_minute_only_while_seen():
    """A connected agent changes proposals from outside the tab. React Query
    pauses the poll while the tab is hidden (M4), and the count always runs (M5)."""
    hook = _read("hooks/use-needs-you-count.ts")
    assert "refetchInterval: 60_000" in hook
    assert "refetchIntervalInBackground" not in hook and "enabled:" not in hook


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


# ── Lanes: one table, every status in exactly one lane ──────────────────────


def _ts_strings(body: str) -> list[str]:
    return re.findall(r'"([a-z_]+)"', body)


def _frontend_statuses() -> list[str]:
    types = _read("lib/types.ts")
    return _ts_strings(re.search(r"const PROPOSAL_STATUSES = \[([^\]]*)\] as const;", types).group(1))


def _lane_table() -> dict[str, list[str]]:
    lanes = _read("lib/inbox-lanes.ts")
    table = lanes[lanes.index("export const INBOX_LANES") :]
    table = table[: table.index("\n};\n")]
    return {lane: _ts_strings(body) for lane, body in re.findall(r"^  (\w+): \[([^\]]*)\],$", table, re.M)}


def test_every_status_is_in_exactly_one_lane():
    """A status in no lane never shows (M2); in two it shows twice (M1, M3)."""
    from app.models.application_proposal import PROPOSAL_STATUSES

    statuses = _frontend_statuses()
    assert sorted(statuses) == sorted(PROPOSAL_STATUSES)  # types.ts mirrors the backend
    table = _lane_table()
    assert list(table) == ["needs_you", "triage", "queued", "in_flight", "history"]
    members = [s for lane in table.values() for s in lane]
    assert sorted(members) == sorted(statuses), "a status is in no lane, or in two"


def test_the_lanes_hold_the_owners_statuses():
    table = _lane_table()
    assert table["needs_you"] == ["needs_decision", "needs_human"]
    assert table["triage"] == ["pending_review"]
    assert table["queued"] == ["accepted"]
    assert table["in_flight"] == ["approved"]


def test_a_status_this_build_does_not_know_is_in_no_lane():
    """Rather than a wrong one (a newer backend)."""
    laneof = _read("lib/inbox-lanes.ts")
    laneof = laneof[laneof.index("export function laneOf(") :]
    assert laneof[: laneof.index("\n}\n")].endswith("  }\n  return null;")


def test_every_status_has_a_chip_label_in_lane_order():
    """STATUS_ORDER is the lane table flattened, and every status has a chip (M19)."""
    lanes = _read("lib/inbox-lanes.ts")
    assert (
        "export const STATUS_ORDER: readonly ProposalStatus[] = (Object.keys(INBOX_LANES) as InboxLane[]).flatMap("
        in lanes
    )
    assert "STATUS_ORDER.map((k) => [k, PROPOSAL_STATUS_CHIP[k].label])" in _SECTION
    chip = _read("components/status-chip.tsx")
    chip = chip[chip.index("export const PROPOSAL_STATUS_CHIP") :]
    chip = chip[: chip.index("\n};\n")]
    assert sorted(re.findall(r"^  (\w+): ", chip, re.M)) == sorted(_frontend_statuses())


def test_the_lanes_are_read_from_the_one_table():
    """Each lane filters through `inLane`, never its own list (M6)."""
    for lane in ("needs_you", "triage", "queued", "in_flight", "history"):
        assert _SECTION.count(f'inLane(filtered, "{lane}")') == 1, lane
    assert '"all", ...INBOX_LANES.history' in _SECTION  # the History filter's chips
    for old in ("const NEEDS_YOU", "const TRIAGE", "const QUEUED", "const IN_FLIGHT", "const HISTORY",
                "export const STATUS_ORDER", ".includes(p.status)"):
        assert old not in _SECTION, old


# ── A selection acts only on rows the user can see ──────────────────────────


def test_bulk_actions_use_only_the_rows_shown():
    """A5 found by reading: a filter or the search hid selected rows, and the
    bulk bar still queued or skipped them."""
    assert "const selectedShown = useMemo(() => selectedAmong(triage, selected), [triage, selected]);" in _SECTION
    bar = _SECTION[_SECTION.index("<BulkBar") :]
    bar = bar[: bar.index("/>")]
    assert "selectedCount={selectedShown.length}" in bar
    assert 'actions.bulk({ ids: selectedShown, status: "accepted" });' in _SECTION
    assert 'actions.bulk({ ids: selectedShown, status: "rejected", reason });' in _SECTION
    assert "[...selected]" not in _SECTION and "selected.size" not in _SECTION
    # Node tests are not in CI: the lib's one line, pinned here.
    lib = _read("lib/inbox-lanes.ts")
    assert "return shown.filter((item) => selected.has(item.id)).map((item) => item.id);" in lib


def test_a_row_acted_on_alone_leaves_the_selection():
    done = _SECTION[_SECTION.index("onDone: (ids) => {") :]
    done = done[: done.index("\n    },\n")]
    assert "for (const id of ids) copy.delete(id);" in done


# ── One request per click, and focus never falls to <body> ─────────────────


def _row() -> str:
    return _SECTION[_SECTION.index("function ProposalRow(") :]


def test_the_inbox_starts_triage_only_through_the_guard():
    """A double click on a row's or the bar's Queue sent two PATCHes, the second
    "cannot go accepted -> accepted". The raw mutations stay in the hook
    (test_frontend_single_flight.py pins the guard there)."""
    ret = _TRIAGE[_TRIAGE.index("  return {\n    transition: transitionOnce,") :]
    ret = ret[: ret.index("\n  };\n")]
    assert "bulk: bulkOnce," in ret and "remove: removeOnce," in ret
    assert "pending: transition.isPending || bulk.isPending || remove.isPending," in ret
    for src in (_SECTION, _JOB):
        assert ".transition.mutate" not in src and ".bulk.mutate" not in src and ".remove.mutate" not in src


def test_row_actions_keep_focus_while_they_run():
    """A natively disabled row button dropped focus to <body> while it ran."""
    row = _row()
    buttons = re.findall(r"<IconButton\b.*?\n\s*/>", row, re.S)
    assert len(buttons) == 5
    for button in buttons:
        assert "focusableWhenDisabled" in button, button
        assert "data-disabled:pointer-events-none data-disabled:opacity-50" in button, button
        assert re.search(r'data-row-action="(queue|keep|skip|delete)"', button), button


def test_a_row_that_leaves_its_lane_hands_focus_on():
    """The next row's same control, else the previous row's, else the lane."""
    assert (
        'next: focusSuccessor(from.closest(\'[data-slot="card"]\'), `[data-row-action="${action}"]`),'
        in _SECTION
    )
    effect = _SECTION[_SECTION.index("const l = leaving.current;") :]
    effect = effect[: effect.index("}, [items, barShown]);")]
    assert 'l.kind === "bar" ? barShown : items.some((p) => p.id === l.id && laneOf(p.status) === l.lane)' in effect
    assert "focusIfDropped(l.next());" in effect
    lane = _SECTION[_SECTION.index("function Lane(") :]
    assert "<section ref={ref} tabIndex={-1} aria-labelledby={headingId}" in lane
    assert "<h2 id={headingId}" in lane


def test_the_bulk_bar_hands_focus_to_the_lane_when_it_leaves():
    assert _SECTION.count('leaving.current = { kind: "bar", next: () => toReview.current };') == 1
    assert _SECTION.count("leaveBar();") == 3  # Queue, Skip and Clear
    assert '<Lane ref={toReview} title={`To review · ' in _SECTION
    bar = _TRIAGE[_TRIAGE.index("export function BulkBar(") :]
    assert bar.count("focusableWhenDisabled") == 3
    assert bar.count("data-disabled:pointer-events-none data-disabled:opacity-50") == 3


def test_the_skip_dialog_keeps_focus_and_hands_it_on():
    dialog = _TRIAGE[_TRIAGE.index("export function DeclineDialog(") : _TRIAGE.index("export function BulkBar(")]
    assert dialog.count("focusableWhenDisabled") == 2  # Cancel and Skip
    assert "<DialogContent size=\"sm\" finalFocus={finalFocus}>" in dialog
    final = _SECTION[_SECTION.index("finalFocus={() => {") :]
    final = final[: final.index("}}")]
    assert "const next = skipReturn.current;" in final
    assert "return next ? finalFocusOn(next()) : true;" in final


def test_a_confirmed_delete_returns_focus_where_the_caller_says():
    remove = _TRIAGE[_TRIAGE.index("const remove = useMutation({") :]
    remove = remove[: remove.index("\n  });")]
    assert "returnFocus: () => (confirmed && next ? next() : null)," in remove
    assert "confirmed = await confirm(" in remove


def test_the_job_header_triage_keeps_focus_in_the_header():
    job = _JOB
    for label in ("Queue", "Skip", "Delete proposal"):
        at = job.index(f"\n                {label}\n              </Button>")
        button = job[job.rfind("<Button", 0, at) : at]
        assert "focusableWhenDisabled" in button, label
        assert "data-disabled:pointer-events-none data-disabled:opacity-50" in button, label
    effect = job[job.index("if (!triaged.current) return;") :]
    effect = effect[: effect.index("}, [triagedStatus]);")]
    assert "focusIfDropped(actionsRef.current && focusTarget(actionsRef.current));" in effect


# ── The node-tested rules, pinned for CI (node tests are not in CI) ─────────


def test_the_mapper_never_names_you_or_a_generic_client():
    """M13, and the Python MCP SDK's default name "mcp" (it says nothing about who it is)."""
    name = _name()
    assert 'if (!name || name.toLowerCase() === "you") return null;' in name
    assert 'const GENERIC_WORDS = new Set(["mcp", "client"]);' in name
    assert "if (words.every((word) => GENERIC_WORDS.has(word))) return null;" in name


def test_known_clients_match_whole_words_only():
    """"precursor-bot" is not Cursor; "openai-agents" is not ChatGPT."""
    name = _name()
    assert "const words = name.toLowerCase().split(/[^\\p{L}\\p{N}]+/u).filter(Boolean);" in name
    assert "if (words.includes(word)) return label;" in name
    assert 'const KNOWN_NAMES: Readonly<Record<string, string>> = { "openai-mcp": "ChatGPT" };' in name
    words = name[name.index("const KNOWN_WORDS") :]
    assert "openai" not in words[: words.index("\n];\n")]


def test_an_unknown_name_keeps_the_clients_casing():
    """M14 ("iPhone" stays), M15 (acronyms in capitals)."""
    name = _name()
    word = name[name.index("function titleWord(") :]
    word = word[: word.index("\n}\n")]
    assert "if (ACRONYMS.has(word.toLowerCase())) return word.toUpperCase();" in word
    assert "if (word !== word.toLowerCase()) return word;" in word
    assert "return word.charAt(0).toUpperCase() + word.slice(1);" in word


def test_an_unreported_filer_is_never_claimed():
    """M12: an older backend (undefined) gets no by-line, and its Queue toast names no agent."""
    name = _name()
    assert "if (proposedBy === undefined) return null;" in name
    toast = name[name.index("export function queuedToast(") :]
    assert 'proposedBy === undefined || proposedBy === "you"' in toast


def test_the_role_filter_compares_the_role():
    """M11."""
    assert 'if (role !== "all" && p.job.role_category !== role) return false;' in _read("lib/inbox-filter.ts")


def _block(src: str, start: str, end: str) -> str:
    i = src.index(start)
    return src[i : src.index(end, i + len(start))]


def test_a_question_from_the_agent_can_be_answered_here():
    """First-read pass: a Needs-you proposal offered only Skip and Delete. A question
    (`needs_decision`) is answered with Keep it (back to To review: the backend's
    needs_decision → pending_review, services/proposals.py ALLOWED) on the row and the
    job page; a stop (`needs_human`) has no answer here, and the row says so."""
    row = _block(_SECTION, "function ProposalRow(", "\n}\n")
    assert 'const showKeep = lane === "needs_you" && proposal.status === "needs_decision";' in row
    keep = _block(row, "{showKeep ? (", ") : null}")
    # Single-flight (the hook's transitionOnce), and focusable while it runs.
    for attr in ('label="Keep it"', 'data-row-action="keep"', 'onClick={act("keep")}',
                 "disabled={pending}", "focusableWhenDisabled"):
        assert attr in keep, attr
    assert 'else if (action === "keep") actions.transition({ id: p.id, status: "pending_review" });' in _SECTION
    # The agent's words on the row, and how each kind is answered under the lane's heading.
    assert "const needs = lane === \"needs_you\" ? needsYouLine(proposal.status, proposal.reason) : null;" in row
    assert "help={needsYouHelp(needsYou.map((p) => p.status))}" in _SECTION


def test_the_job_page_keeps_a_question_with_the_jobs_application():
    """Keep it links the job's application only for a proposal linked to none."""
    assert 'const showKeep = proposalStatus === "needs_decision";' in _JOB
    job_keep = _block(_JOB, "{showKeep && proposalId ? (", ") : null}")
    for part in ('status: "pending_review",', "applicationId: asked.data?.application ? undefined : application?.id,",
                 "disabled={triagePending || !asked.data}", "triaged.current = true;"):
        assert part in job_keep, part
    assert 'if (became === "pending_review") toast.success("Kept. It\'s back in To review.");' in _JOB


def test_keep_it_patches_to_review_without_consent():
    # The PATCH: no consent for a return to To review, the application when given.
    assert '...(status === "pending_review" ? {} : { consent: { channel: "frontend" } }),' in _TRIAGE
    assert "...(applicationId ? { application_id: applicationId } : {})," in _TRIAGE
    assert "const needs = needsYouLine(data.status, data.reason);" in _PANEL


def test_the_needs_you_help_says_where_a_stop_is_answered():
    from tests.node_ts import ts_map

    decision, human = ts_map("./lib/inbox-lanes.ts", "needsYouHelp", [["needs_decision"], ["needs_human"]])
    assert decision == ["Keep it answers yes: the job goes back to To review. Skip answers no."]
    assert human == ["Where your agent stopped, finish that step in your agent's own chat. "
                     "It carries on from there."]


def test_the_consent_line_is_said_once_on_the_inbox():
    """The header carries it; the empty state doesn't repeat it (first-read pass)."""
    empty = _SECTION[_SECTION.index("if (items.length === 0) {") : _SECTION.index("const rowProps")]
    assert "Nothing is submitted without your yes." not in empty
    assert "<p>Jobs your connected agents found. Nothing is submitted without your yes.</p>" in _PAGE
