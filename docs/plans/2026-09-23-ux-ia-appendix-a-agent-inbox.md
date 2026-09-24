> **Appendix A (Agent inbox) to the UX IA/copy plan.** This is a research brief. It was written read-only
> against `8cac7cf9` (`claude/ux-ia-copy-plan`, equal to local main). It covers owner decisions 1–8 for
> `/proposals` plus the planner's scope addition (**A9, "proposed by"**). Where it offers options, the plan's
> owner decisions are binding. Line numbers are at `8cac7cf9`; re-locate each quote before you edit.

# Implementation brief: A1–A10, the Agent inbox

No repo file was changed except this one. Paths are relative to `frontend/` unless they start with
`backend/`, `docs/`, `README.md` or `SYSTEM.md`.

**Goal (for this appendix).** `/proposals` reads as what it is: an inbox of jobs that a *connected agent*
filed for your yes. It says who filed each one. It filters like Applications. It shows a count in the
sidebar when something needs you. It explains where proposals come from when there are none. It admits
when the list was cut at 500. Every agent-related word in the web app names one kind of agent. The
principles:
- **Words name the actor.** Assistant = the in-app chat. Connected agents = external MCP clients (Claude,
  Codex, the ChatGPT desktop app). Companion = the Chrome extension. Suggested edits = chat's approval
  cards. "Proposal" means only a job an agent filed.
- **Frozen public surface.** The URL `/proposals`, `?from=proposals`, `cs-proposals-seq`, every API path,
  status value, MCP tool name and parameter stay. Only UI words change. The one contract change (A9) is
  additive: a new optional response field, an optional body field that accepts only `"you"`, and a header
  the MCP server already sends for KB writes.
- **Accessibility is not negotiable.** The count is in the link's accessible name. Contrast is computed by
  the pin, not eyeballed. Focus never drops to `<body>`.
- **No new dependencies.** React Compiler lint rules are at error level. `GuardedLink` is the only
  `next/link` importer. Any new submit goes through `useSingleFlight` (this appendix adds none).

**How the numbers were made.** The badge contrast figures in A4 come from the helpers in
`backend/tests/test_frontend_color_roles.py` (`_rgb`, `_hover`, `_HOVER_MIX`, `_palette_ratio`). A scratch
script imported that module, added `orange-300` from the installed `node_modules/tailwindcss/theme.css`
(`oklch(83.7% 0.128 66.29)`), and measured all four sidebar row states in both modes. The FastMCP facts in
A9 were read from the installed `mcp` package (`ServerSession.client_params`, `Context.session`); the lock
pins `mcp==1.29.1` and the local anaconda has 1.26.0, and both expose the same properties. No browser was
driven for this brief. The browser checks below are for the implementer.

---

## Suggested task split

| Task | Sections | Main files | Size | Depends on |
|---|---|---|---|---|
| **T-A1 Proposed-by backend** | A9 (backend + MCP) | model, schemas, `routers/proposals.py`, `routers/jobs.py`, `services/proposals.py`, two migrations, `mcp_server/server.py` + `client.py`, backend tests | M | none |
| **T-A2 The inbox page** | A1, A2, A3, A6, A7, A9 (inbox, Overview card, job header) | `app/proposals/page.tsx`, `components/proposals/*`, new `lib/*` + hooks + `list-search.tsx` + `list-cap-notice.tsx`, `app/jobs/[id]/page.tsx` (strings) | L | T-A1 for real data (types are optional, so it can land first) |
| **T-A3 Sidebar count** | A4 | `components/app-sidebar.tsx`, `lib/needs-you.ts`, `hooks/use-needs-you-count.ts`, colour-roles pin | S | T-A2 shares `lib/needs-you.ts`, so land after it or own the file here |
| **T-A4 Words and the Connected agents card** | A5 (the files T-A2 does not own), A8 | settings, chat, career, analytics files; new `components/settings/connected-agents-card.tsx` | M | the Settings-tabs appendix mounts A8's card |

The tracker's four string edits (A5 rows in `app/applications/page.tsx`, plus A9's tracker mark) touch a
file the **Applications appendix** owns. See *File ownership* at the end.

---

## Global constraints (every task)

- **React Compiler lint runs at error level.** No `setState` in an effect or during render, no
  `ref.current` read during render, no mutation of props or query-cache objects. Everything here is
  derived in render or set from event handlers. `formatTimeAgo` in render has a precedent
  (`career/entity-card.tsx`, `kb-sync-pill.tsx`): the compiler flags a direct `Date.now()` call only.
- **`lib/*.ts` imports only relative paths or bare packages, and only `import type` across lib files.**
  `node --test` loads them with type stripping; `@/` does not resolve there. Test files are excluded from
  `tsc` (`tsconfig.json` `"exclude": ["node_modules", "**/*.test.ts"]`).
- **Node tests are not in CI.** Every `lib/*.ts` behaviour gets a node test *and* a pytest source pin.
- **`GuardedLink as Link`** for every in-app link. External links follow the Settings page's convention
  (`app/settings/page.tsx:41-50`): `<a target="_blank" rel="noopener noreferrer">` rendered through
  `Button … nativeButton={false} render={…}` with a leading icon.
- **Frontend duplication must not rise.** A3 extracts `ListSearch` instead of copying Applications' search
  box, and A2 extracts `useProposalFunnel` instead of a second copy of the funnel `useQuery`. Run
  `slop_scan.py check frontend` (and `backend` for T-A1) and name each surface.
- **MCP contracts are additive; docstrings stay under ~2,000 characters.** A9 changes no docstring that is
  near the budget (`test_registered_tool_docstrings_fit_client_truncation_budget`).
- **SYSTEM.md is at its cap.** Lanes queue SYSTEM.md edits (A10 lists them); `docs/frontend-conventions.md`
  and `docs/entities/others.md` change in the same commit as the code.
- **Mutation-check every pin you add**: break the code it guards, watch exactly that pin fail, restore from
  a backup copy (never `git stash`).

---

## A1. The page is called "Agent inbox" (owner decision 1)

**Keep the URL `/proposals`.** There is no strong reason to move it. `/proposals` is in `lib/nav.ts:14`,
the job page's Back and prev/next (`app/jobs/[id]/page.tsx:175,183,323`), `cs-proposals-seq`
(`proposals-section.tsx:48`), the Overview card's link (`proposal-agent-panel.tsx:172`), two MCP
docstrings (`mcp_server/server.py:1573` "the proposals page", `:1593` "/proposals page or
record_triage") and `docs/skills/agent-apply-execution/SKILL.md:19`. Both docstrings stay true: the page
still lives at `/proposals`. A rename would need a redirect stub (the `/explore` precedent,
`app/explore/page.tsx`) and a docstring edit, and buys nothing a user sees.

### Current code

`components/app-sidebar.tsx:49`
```tsx
      { href: "/proposals", label: "Agent Proposals", icon: Bot },
```

`app/proposals/page.tsx:7-10`
```tsx
      <PageHeader
        title="Agent proposals"
        subtitle="What the hunt found. Submitting still needs your approval."
      />
```

`app/jobs/[id]/page.tsx:289-293`, `:316`, `:545-547`
```tsx
              label={
                fromProposals
                  ? "Previous proposal in list"
                  : "Previous job in list"
              }
…
            label={fromProposals ? "Back to proposals" : "Back to applications"}
…
              label={
                fromProposals ? "Next proposal in list" : "Next job in list"
              }
```

`components/proposals/proposal-agent-panel.tsx:171-177`
```tsx
          <Link
            href={`/proposals`}
            className="text-muted-foreground inline-flex items-center gap-1.5 text-xs underline"
          >
            <Briefcase className="size-3.5" aria-hidden="true" />
            All proposals
          </Link>
```

`components/proposals/proposals-section.tsx:367`
```tsx
          title="Couldn't load agent proposals."
```

### New code

`components/app-sidebar.tsx:49`
```tsx
      { href: "/proposals", label: "Agent inbox", icon: Bot },
```
The icon stays `Bot`: Applications already uses `Inbox`, and two identical icons in one nav group read as
the same place.

`app/proposals/page.tsx` (whole file; the Cap today line is A2)
```tsx
import { CapToday } from "@/components/proposals/cap-today";
import { ProposalsSection } from "@/components/proposals/proposals-section";
import { PageHeader, PageShell } from "@/components/page-shell";

export default function ProposalsPage() {
  return (
    <PageShell>
      <PageHeader
        title="Agent inbox"
        // A node slot: PageHeader renders it in a <div>, so the <p> and the
        // client-side cap line are valid children (page-shell.tsx:96-100).
        subtitle={
          <>
            <p>Jobs your connected agents found. Nothing is submitted without your yes.</p>
            <CapToday />
          </>
        }
      />
      <ProposalsSection />
    </PageShell>
  );
}
```

`app/jobs/[id]/page.tsx`
```tsx
              label={
                fromProposals
                  ? "Previous job in Agent inbox"
                  : "Previous job in list"
              }
…
            label={fromProposals ? "Back to Agent inbox" : "Back to applications"}
…
              label={
                fromProposals ? "Next job in Agent inbox" : "Next job in list"
              }
```

`components/proposals/proposal-agent-panel.tsx:171-177`
```tsx
          <Link
            href="/proposals"
            className="text-muted-foreground inline-flex items-center gap-1.5 text-xs underline"
          >
            <Briefcase className="size-3.5" aria-hidden="true" />
            Open Agent inbox
          </Link>
```

`components/proposals/proposals-section.tsx:367`
```tsx
          title="Couldn't load your Agent inbox."
```

The Overview card's title is A9 (it names who filed the proposal).

### Pins to add (`backend/tests/test_frontend_agent_inbox.py`, new; header shown once here)

```python
"""Pins: the Agent inbox (docs/plans/2026-09-23-ux-ia-appendix-a-agent-inbox.md).

The page is named for what it is, keeps one number from the funnel, filters
in one row like Applications, counts what needs you in the sidebar, says who
can file a proposal when there are none, admits a cut list, and names who
filed each proposal. Node tests cover lib/list-cap.ts, lib/needs-you.ts,
lib/inbox-filter.ts and lib/agent-name.ts; they are not in CI, so the
branches that matter are pinned here.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND = _ROOT / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


_SIDEBAR = _read("components/app-sidebar.tsx")
_PAGE = _read("app/proposals/page.tsx")
_SECTION = _read("components/proposals/proposals-section.tsx")
_JOB = _read("app/jobs/[id]/page.tsx")
_PANEL = _read("components/proposals/proposal-agent-panel.tsx")


def test_the_inbox_is_called_agent_inbox_wherever_it_is_named():
    assert '{ href: "/proposals", label: "Agent inbox", icon: Bot }' in _SIDEBAR
    assert 'title="Agent inbox"' in _PAGE
    assert 'fromProposals ? "Back to Agent inbox" : "Back to applications"' in _JOB
    assert '"Previous job in Agent inbox"' in _JOB
    assert '"Next job in Agent inbox"' in _JOB
    assert "Open Agent inbox" in _PANEL
    assert 'title="Couldn\'t load your Agent inbox."' in _SECTION
    for rel, src in (
        ("app-sidebar", _SIDEBAR), ("page", _PAGE), ("job", _JOB), ("panel", _PANEL),
    ):
        for old in ("Agent Proposals", "Agent proposals", "Back to proposals",
                    "proposal in list", "All proposals"):
            assert old not in src, f"{rel}: {old!r}"


def test_the_url_and_its_session_keys_stay():
    """Deep links, ?from=proposals and cs-proposals-seq are the frozen surface."""
    assert 'href: "/proposals"' in _SIDEBAR
    assert 'const SEQUENCE_STORE_KEY = "cs-proposals-seq";' in _SECTION
    assert "href={`/jobs/${proposal.job_id}?from=proposals`}" in _SECTION
    assert 'readSequence(fromProposals ? "cs-proposals-seq" : "cs-tracker-seq")' in _JOB
```

### Existing pins that change

None. `test_frontend_sidebar_nav.py` pins `navCurrent(`, `aria-current={current}` and the `?from=`
mapping, all unchanged.

### Browser checks

Setup (every section's checks use it): a fresh stack per SYSTEM.md §9 (uvicorn on a free port with its
own SQLite file under the scratchpad, never `data/`; `API_PROXY_BACKEND=… npx next dev -p <port>`).
Seed jobs directly, then file proposals over REST so the A9 header path is exercised:

```bash
cd backend && DATABASE_URL=sqlite:///$SCRATCH/inbox.sqlite3 /opt/anaconda3/bin/python3 - <<'EOF'
import uuid
from app.db import SessionLocal
from app.models.job import Job
rows = [("Acme", "Data Scientist", "agent"), ("Beta", "ML Engineer", "agent"),
        ("Gamma", "Analytics Engineer", "user"), ("Delta", "Data Engineer", "agent")]
with SessionLocal() as db:
    for i, (company, title, source) in enumerate(rows):
        db.add(Job(raw_text=f"JD {i}", raw_text_hash=uuid.uuid4().hex, company=company, title=title,
                   role_category="data_scientist", source=source,
                   source_url=f"https://boards.greenhouse.io/{company.lower()}/{i}"))
    db.commit()
    print({j.company: str(j.id) for j in db.query(Job).all()})
EOF
# One proposal per agent job, as Claude would file it:
curl -s -X POST localhost:$API/api/proposals -H 'content-type: application/json' \
  -H 'X-Maestro-CS-Origin: mcp' -H 'X-Maestro-CS-Origin-Detail: claude-ai' \
  -d '{"job_id":"<Acme id>","fit":{"chosen_base":"<a base slug>","scores":{"<a base slug>":72}}}'
# Put one in Needs you:
curl -s -X POST localhost:$API/api/proposals/<id>/request-decision -H 'content-type: application/json' \
  -d '{"reason":"two bases tie"}'
```

1. **1280, light.** The sidebar reads "Agent inbox". Open it: the `<h1>` reads "Agent inbox" and the
   subtitle is the new sentence. Open a row: the job page's Back button tooltip reads "Back to Agent
   inbox"; the sidebar marks Agent inbox current (`aria-current="true"`, `read_page`). The prev/next
   rails read "Previous job in Agent inbox" / "Next job in Agent inbox".
2. **Keyboard.** From the job page press Tab to Back, Enter: you land on `/proposals`; focus is not on
   `<body>` (`document.activeElement` via `javascript_tool`).
3. **Overview card.** "Open Agent inbox" goes to `/proposals`.
4. **Dark, 768 and 375.** Same words; the sidebar sheet at 375 shows "Agent inbox".

### Risks

- README and GETTING_STARTED still say "Agent Proposals" (A10 lists the edits). A user following the README
  would not find the old name until those land.

---

## A2. The funnel leaves the inbox; "Cap today N/M" stays (owner decision 2)

### Current code

`components/proposals/funnel-strip.tsx` (70 lines) is a Card with six stage counts and a "Cap today"
readout. Its **only consumer** is `proposals-section.tsx`, mounted three times:

`components/proposals/proposals-section.tsx:16`, `:362-374`, `:386-398`, `:411-413`
```tsx
import { FunnelStrip } from "@/components/proposals/funnel-strip";
…
  if (isLoadFailure({ data, isError, fetchStatus, errorUpdateCount })) {
    return (
      <div className="flex flex-col gap-5">
        <FunnelStrip />
        <LoadErrorState
…
  if (items.length === 0) {
    return (
      <div className="flex flex-col gap-5">
        <FunnelStrip />
…
  return (
    <div className="flex flex-col gap-6 pb-20">
      <FunnelStrip />
```

The full funnel already lives in Analytics › Overview on the **same query key**:

`components/analytics/agent-pipeline-card.tsx:25-28`
```tsx
  const { data, isLoading, error } = useQuery({
    queryKey: ["proposals", "funnel"],
    queryFn: () => apiFetch<ProposalFunnel>("/api/proposals/funnel"),
  });
```

`cap` is always present on `/api/proposals/funnel` (`routers/proposals.py:265` `cap=svc.cap_status(db)`).
"Today" is a rolling window: `services/proposals.py:397` counts `cap_reserved_at >= now - 1 day`.

### New code

**Delete** `components/proposals/funnel-strip.tsx`. `grep -rn FunnelStrip frontend/app frontend/components`
returns only the three mounts above.

`hooks/use-proposal-funnel.ts` (new): one definition of the query both readers use.
```ts
"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { ProposalFunnel } from "@/lib/types";

/** The proposal funnel. Two readers share this one cache entry: the Agent
 *  inbox's "Cap today" line and Analytics › Overview's Agent pipeline card.
 *  Under ["proposals"], so every triage invalidation refreshes both. */
export function useProposalFunnel() {
  return useQuery({
    queryKey: ["proposals", "funnel"],
    queryFn: () => apiFetch<ProposalFunnel>("/api/proposals/funnel"),
  });
}
```

`components/analytics/agent-pipeline-card.tsx:24-28`
```tsx
export function AgentPipelineCard() {
  const { data, isLoading, error } = useProposalFunnel();
```
(drop the `useQuery` and `apiFetch` imports; add `import { useProposalFunnel } from "@/hooks/use-proposal-funnel";`).

`components/proposals/cap-today.tsx` (new)
```tsx
"use client";

import { RotateCw } from "lucide-react";

import { RetryChip } from "@/components/retry-chip";
import { useProposalFunnel } from "@/hooks/use-proposal-funnel";
import { isLoadFailure } from "@/lib/query-state";

/**
 * "Cap today 2/10" under the Agent inbox subtitle: the one number from the old
 * funnel strip that bears on triage, because each submit a connected agent
 * makes takes a slot. The whole funnel lives in Analytics › Overview (Agent
 * pipeline) on the same query.
 *
 * "Today" is the backend's rolling 24 hours (services/proposals.cap_status),
 * and the spoken text says so. While loading it shows nothing, which claims
 * nothing. A failed first load is its own state, a retry chip, never a silent
 * blank (docs/frontend-conventions.md, "A failed fetch is a THIRD state").
 */
export function CapToday() {
  const query = useProposalFunnel();
  if (isLoadFailure(query)) {
    return (
      <RetryChip
        className="text-muted-foreground mt-0.5 inline-flex items-center gap-1 text-xs underline-offset-4 hover:underline"
        title="Retry loading the daily submission cap"
        icon={<RotateCw className="size-3" aria-hidden="true" />}
        label="Couldn't load the daily cap. Retry"
        retrying={query.isFetching}
        onRetry={() => void query.refetch()}
      />
    );
  }
  const cap = query.data?.cap;
  if (!cap) return null;
  return (
    <p className="mt-0.5 text-xs tabular-nums">
      <span aria-hidden="true">
        Cap today {cap.reserved_last_24h}/{cap.max_per_day}
      </span>
      <span className="sr-only">
        Daily submission cap: {cap.reserved_last_24h} of {cap.max_per_day} used in the last 24 hours
      </span>
    </p>
  );
}
```
The line inherits the subtitle's `text-muted-foreground` (pinned at 4.5:1 on the page in both modes).
`RetryChip` already hands focus off when it unmounts (`useFocusHandoff`), so a successful retry does not
drop focus.

`components/proposals/proposals-section.tsx`: remove the import and all three mounts. The failure branch
becomes the bare `LoadErrorState` (its opening line, which a pin reads, is unchanged):
```tsx
  if (isLoadFailure({ data, isError, fetchStatus, errorUpdateCount })) {
    return (
      <LoadErrorState
        title="Couldn't load your Agent inbox."
        detail={(error as Error)?.message}
        retrying={isFetching}
        onRetry={() => void refetch()}
      />
    );
  }
```
and the main return opens `<div className="flex flex-col gap-6 pb-20">` with the A3 toolbar as its first
child.

`components/settings/auto-apply-section.tsx:107` comment only:
```tsx
      // The inbox's Cap today line and Analytics' Agent pipeline read the cap.
      qc.invalidateQueries({ queryKey: ["proposals", "funnel"] });
```

### Pins to add (`test_frontend_agent_inbox.py`)

```python
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
    hook = _read("hooks/use-proposal-funnel.ts")
    assert 'queryKey: ["proposals", "funnel"]' in hook
    assert "useProposalFunnel()" in _read("components/analytics/agent-pipeline-card.tsx")
```

### Existing pins that change

`backend/tests/test_frontend_query_error_states.py:68` — **delete** the row
```python
    ("components/proposals/funnel-strip.tsx", "if (!data) return null"),
```
(the file is gone; `test_query_surface_error_branch_precedes_empty_state` would raise on a missing file).
The `agent-pipeline-card.tsx` row (`:72`, marker `"return null"`) stays: it still spells its error check
`error` before `return null`. Re-run the module after the hook swap: `_ERROR_BRANCH` matches
`!isLoading && !error` at `agent-pipeline-card.tsx:30` (the `!error\b` alternative), which is unchanged.

### Browser checks

1. **1280, light.** `/proposals` has no stage-count card. Under the subtitle: "Cap today 0/10" (or your
   cap). `read_page` shows the sr-only text "Daily submission cap: 0 of 10 used in the last 24 hours" and
   not the visible "0/10" (it is `aria-hidden`).
2. **Shared cache.** Open Analytics › Overview: the Agent pipeline card still shows every stage and its
   cap line. Change the daily cap in Settings › Connected agents (A8) and save; return to `/proposals`: the
   line shows the new maximum without a reload.
3. **Failure.** Stop uvicorn, reload `/proposals`: the page shows its `LoadErrorState`, and the header shows
   "Couldn't load the daily cap. Retry". Tab to it, restart uvicorn, press Enter: the line returns and
   focus lands on the page's nearest `tabIndex={-1}` ancestor or `#main-content`, never `<body>`.
4. **Dark, 768, 375.** The line wraps under the subtitle; no horizontal scrollbar.

### Risks

- A user who relied on the in-page funnel now has one click more to Analytics. Owner decision; the
  pipeline card is unchanged.
- The pipeline card hides itself when nothing was captured (`agent-pipeline-card.tsx:30`). That is fine for
  Analytics and does not affect the inbox's cap line.

---

## A3. A toolbar consistent with Applications (owner decision 3)

### Current code

Applications' toolbar (`app/applications/page.tsx:417-473`): a search pill on its own line, then ONE row of
`h-8 rounded-full` controls named by `aria-label`, with no visible stacked caption.
```tsx
      <div className="flex flex-col gap-3">
        <div className="relative w-full max-w-sm">
          <Search className="text-muted-foreground pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2" />
          <Input
            aria-label="Search applications"
            placeholder="Search company or role…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="h-10 rounded-full pl-10"
          />
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Select …>
            <SelectTrigger
              className="h-8 min-w-[11rem] rounded-full"
              aria-label="Filter by status"
            >
…
          <SourceToggle
            className="ml-auto"
```

The inbox's toolbar (`components/proposals/proposals-section.tsx:415-482`): four stacked captions over
square `h-8` controls, and a free-number field.
```tsx
      <div className="flex flex-wrap items-end gap-2">
        <div className="grid gap-1">
          <span className="text-muted-foreground text-xs">Sort</span>
          <Select …>
            <SelectTrigger className="h-8 min-w-[9rem]" aria-label="Sort">
…
          <span className="text-muted-foreground text-xs">Role</span>
          <Select value={role} onValueChange={(v) => setRole(v ?? "all")}>
            <SelectTrigger className="h-8 min-w-[9rem]" aria-label="Role">
              <SelectValue>
                {role === "all" ? "All roles" : role}
              </SelectValue>
…
              {roles.map((r) => (
                <SelectItem key={r} value={r}>
                  {r}
                </SelectItem>
…
          <span className="text-muted-foreground text-xs">Min score</span>
          <Input
            type="number"
            inputMode="decimal"
            aria-label="Minimum score"
            placeholder="e.g. 50"
…
```

**Found while reading:** the Role select prints the raw `role_category` key (`{r}`, `:446`, and `role` in
the `SelectValue`, `:439`), e.g. `data_scientist`. Frontend conventions require `useRoleLabel`, and
`test_no_role_key_reaches_the_screen` only scans the analytics files, so nothing caught it.

The filter helpers live inside the component (`:110-133`, `:168-186`), so none is node-testable.

### Design

- **Same shape as Applications**: the search pill on its own line (`max-w-sm`, `h-10 rounded-full`), then
  one wrapping row of `h-8 rounded-full` Selects. The Applications "toolbar" is itself two lines (search,
  then controls); the inbox mirrors it exactly rather than inventing a third layout.
- **Controls kept:** Sort, Role, Job board, Score. **Added:** the search box (company or role, as on
  Applications). **Not added:** a status Select (the lanes *are* the status grouping) and SourceToggle
  (every proposal is an agent's or yours, and A9's by-line already says which).
- **No stacked captions.** Each trigger is named by `aria-label` and shows a self-describing value:
  - Sort: "Best score first", "Newest first", "Role A–Z", "Company A–Z" (a bare "Role" as a sort value
    reads like a filter).
  - Role: "All roles" or the role's label (never the key).
  - Job board: "All boards" or the host.
  - Score: "Any score", "Score 50+", "Score 60+", "Score 70+", "Score 80+". Presets replace the number
    field, which had a stacked label, an example placeholder and no step. The owner may prefer a free
    number (open question 5).
- **Lanes below unchanged**, plus one new state: when filters hide every row, "Nothing matches these
  filters" (Applications' wording shape: `app/applications/page.tsx:504-510`).

### New code

`components/list-search.tsx` (new): the one list search box. Applications can swap its block for this
(open question 12); until then the two copies are identical.
```tsx
"use client";

import { Search } from "lucide-react";

import { Input } from "@/components/ui/input";

/** The list pages' search box: a pill above the filter row. `label` names it
 *  (a search field's placeholder is a prompt, not its name). The placeholder
 *  is on test_frontend_placeholders.py's named-prompt list. */
export function ListSearch({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
}) {
  return (
    <div className="relative w-full max-w-sm">
      <Search
        aria-hidden="true"
        className="text-muted-foreground pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2"
      />
      <Input
        aria-label={label}
        placeholder="Search company or role…"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-10 rounded-full pl-10"
      />
    </div>
  );
}
```

`lib/inbox-filter.ts` (new; moved from the component, plus search and score floors)
```ts
import type { Proposal } from "./types";

/**
 * The Agent inbox's filters, pure so `node --test` runs them
 * (lib/inbox-filter.test.ts); pinned by test_frontend_agent_inbox.py.
 */

/** Score floors the toolbar offers ("Score 70+"): a preset Select keeps the
 *  toolbar one row of the same control, as on Applications. */
export const SCORE_FLOORS = [50, 60, 70, 80] as const;
export type ScoreFloor = (typeof SCORE_FLOORS)[number];

/** The chosen base's score from the proposal's fit, or null when the agent
 *  recorded none. */
export function chosenScore(p: Pick<Proposal, "fit_json">): number | null {
  const fit = (p.fit_json ?? {}) as Record<string, unknown>;
  const chosen = fit.chosen_base;
  const scores = fit.scores;
  if (typeof chosen !== "string" || !scores || typeof scores !== "object") {
    return null;
  }
  const value = (scores as Record<string, unknown>)[chosen];
  return typeof value === "number" ? value : null;
}

export function boardHost(url: string | null): string | null {
  if (!url) return null;
  try {
    return new URL(url).hostname;
  } catch {
    return null;
  }
}

export type InboxFilter = {
  q: string;
  role: string;
  board: string;
  minScore: number | null;
};

export function filterProposals<T extends Pick<Proposal, "fit_json" | "job">>(
  items: T[],
  { q, role, board, minScore }: InboxFilter,
): T[] {
  const needle = q.trim().toLowerCase();
  return items.filter((p) => {
    if (role !== "all" && p.job.role_category !== role) return false;
    if (board !== "all" && boardHost(p.job.source_url) !== board) return false;
    if (minScore != null) {
      const score = chosenScore(p);
      if (score == null || score < minScore) return false;
    }
    if (needle && !`${p.job.company ?? ""} ${p.job.title ?? ""}`.toLowerCase().includes(needle)) {
      return false;
    }
    return true;
  });
}
```

`lib/inbox-filter.test.ts` (new)
```ts
import assert from "node:assert/strict";
import { test } from "node:test";

import { boardHost, chosenScore, filterProposals } from "./inbox-filter.ts";

const p = (over = {}) => ({
  fit_json: { chosen_base: "ds", scores: { ds: 72 } },
  job: {
    company: "Acme",
    title: "Data Scientist",
    role_category: "data_scientist",
    source_url: "https://boards.greenhouse.io/acme/1",
  },
  ...over,
});
const all = { q: "", role: "all", board: "all", minScore: null };

test("no filter keeps every row", () => {
  assert.equal(filterProposals([p(), p()], all).length, 2);
});

test("search matches company or title, case-insensitively, trimmed", () => {
  const rows = [p(), p({ job: { ...p().job, company: "Beta", title: "ML Engineer" } })];
  assert.equal(filterProposals(rows, { ...all, q: "  acme " }).length, 1);
  assert.equal(filterProposals(rows, { ...all, q: "engineer" }).length, 1);
  assert.equal(filterProposals(rows, { ...all, q: "zzz" }).length, 0);
});

test("a score floor drops rows below it and rows with no score", () => {
  const rows = [p(), p({ fit_json: { chosen_base: "ds", scores: { ds: 40 } } }), p({ fit_json: null })];
  assert.equal(filterProposals(rows, { ...all, minScore: 70 }).length, 1);
});

test("role and board compare keys and hosts", () => {
  assert.equal(filterProposals([p()], { ...all, role: "ml_engineer" }).length, 0);
  assert.equal(filterProposals([p()], { ...all, board: "boards.greenhouse.io" }).length, 1);
});

test("the helpers never throw on odd input", () => {
  assert.equal(chosenScore({ fit_json: { chosen_base: 3 } }), null);
  assert.equal(boardHost("not a url"), null);
  assert.equal(boardHost(null), null);
});
```

`components/proposals/proposals-section.tsx` (the changed parts)

Imports: drop `FunnelStrip`, `Input`, `Card`/`CardContent` stay (rows use them). Add:
```tsx
import { Bot, BookOpen, Settings as SettingsIcon } from "lucide-react";   // merge into the lucide import
import { EmptyState } from "@/components/empty-state";
import { ListCapNotice } from "@/components/list-cap-notice";
import { ListSearch } from "@/components/list-search";
import { useRoleLabel } from "@/components/role-category-picker";
import { AGENT_APPLICATIONS_URL, CONNECTED_AGENTS_SETTINGS, JOB_HUNT_SKILL_URL } from "@/lib/agent-links";
import { proposalByLine } from "@/lib/agent-name";
import { formatTimeAgo } from "@/lib/format-date";
import { SCORE_FLOORS, type ScoreFloor, boardHost, chosenScore, filterProposals } from "@/lib/inbox-filter";
import { LIST_CAP, listCap } from "@/lib/list-cap";
import { NEEDS_YOU_STATUSES } from "@/lib/needs-you";
```

Replace `:82` and `:93-100`:
```tsx
const NEEDS_YOU = NEEDS_YOU_STATUSES; // one list with the sidebar count (A4)
…
type SortKey = "score" | "newest" | "role" | "company";

// Values that describe themselves: the toolbar has no captions (A3).
const SORT_LABELS: Record<SortKey, string> = {
  score: "Best score first",
  newest: "Newest first",
  role: "Role A–Z",
  company: "Company A–Z",
};

const scoreLabel = (floor: ScoreFloor | null) =>
  floor == null ? "Any score" : `Score ${floor}+`;
```
Delete `chosenScore`, `boardHost` and `filterProposals` (`:110-133`, `:168-186`); `chosenBase`,
`duplicateKey`, `formatDayLabel` and `sortProposals` stay (the last now calls the imported `chosenScore`).

`:189-193` (the fetch; `LIST_CAP` is A7):
```tsx
  const { data, isLoading, isError, error, isFetching, fetchStatus, refetch, errorUpdateCount } = useQuery({
    queryKey: PROPOSALS_KEY,
    queryFn: () =>
      apiFetch<ProposalListResponse>(`/api/proposals?limit=${LIST_CAP}`),
  });
```

State (`:197-200`):
```tsx
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<SortKey>("score");
  const [role, setRole] = useState("all");
  const [board, setBoard] = useState("all");
  const [minScore, setMinScore] = useState<ScoreFloor | null>(null);
  const roleLabel = useRoleLabel();
```

`:212-218` (roles ordered by what the user reads):
```tsx
  const roles = useMemo(() => {
    const set = new Set<string>();
    for (const p of items) {
      if (p.job.role_category) set.add(p.job.role_category);
    }
    return [...set].sort((a, b) => roleLabel(a).localeCompare(roleLabel(b)));
  }, [items, roleLabel]);
```

`:229-232`:
```tsx
  const filtered = useMemo(
    () => filterProposals(items, { q, role, board, minScore }),
    [items, q, role, board, minScore],
  );
  const nothingMatches = filtered.length === 0;
```
(`nothingMatches` is read only after the `items.length === 0` early return, so it means "filters hid
everything".)

The toolbar, replacing `:415-482`:
```tsx
      <div className="flex flex-col gap-3">
        <ListSearch label="Search the Agent inbox" value={q} onChange={setQ} />
        <div className="flex flex-wrap items-center gap-1.5">
          <Select
            value={sort}
            onValueChange={(v) => setSort((v as SortKey) ?? "score")}
          >
            <SelectTrigger className="h-8 min-w-[10rem] rounded-full" aria-label="Sort">
              <SelectValue>{SORT_LABELS[sort]}</SelectValue>
            </SelectTrigger>
            <SelectContent align="start" alignItemWithTrigger={false} className="w-auto min-w-[12rem]">
              {(Object.keys(SORT_LABELS) as SortKey[]).map((key) => (
                <SelectItem key={key} value={key}>
                  {SORT_LABELS[key]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={role} onValueChange={(v) => setRole(v ?? "all")}>
            <SelectTrigger className="h-8 min-w-[10rem] rounded-full" aria-label="Role">
              <SelectValue>{role === "all" ? "All roles" : roleLabel(role)}</SelectValue>
            </SelectTrigger>
            <SelectContent align="start" alignItemWithTrigger={false} className="w-auto min-w-[12rem]">
              <SelectItem value="all">All roles</SelectItem>
              {roles.map((r) => (
                <SelectItem key={r} value={r}>
                  {roleLabel(r)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={board} onValueChange={(v) => setBoard(v ?? "all")}>
            <SelectTrigger className="h-8 min-w-[10rem] rounded-full" aria-label="Job board">
              <SelectValue>{board === "all" ? "All boards" : board}</SelectValue>
            </SelectTrigger>
            <SelectContent align="start" alignItemWithTrigger={false} className="w-auto min-w-[12rem]">
              <SelectItem value="all">All boards</SelectItem>
              {boards.map((b) => (
                <SelectItem key={b} value={b}>
                  {b}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={minScore == null ? "any" : String(minScore)}
            onValueChange={(v) =>
              setMinScore(v && v !== "any" ? (Number(v) as ScoreFloor) : null)
            }
          >
            <SelectTrigger className="h-8 min-w-[8rem] rounded-full" aria-label="Minimum score">
              <SelectValue>{scoreLabel(minScore)}</SelectValue>
            </SelectTrigger>
            <SelectContent align="start" alignItemWithTrigger={false} className="w-auto min-w-[10rem]">
              <SelectItem value="any">{scoreLabel(null)}</SelectItem>
              {SCORE_FLOORS.map((floor) => (
                <SelectItem key={floor} value={String(floor)}>
                  {scoreLabel(floor)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {nothingMatches ? (
        <EmptyState
          title="Nothing matches these filters"
          description="Try another role, board or score, or clear the search."
        />
      ) : (
        <>
          {/* the Needs you, Triage, Queued, In flight lanes and the History
              section, exactly as today (:484-634) */}
        </>
      )}

      {/* A7 */}
      <ListCapNotice state={listCap(items.length, data?.total)} noun="proposals" />

      <BulkBar … />   {/* unchanged */}
```

Focus: the search box and the four Selects stay mounted through every filter change (the toolbar sits
above both branches), so typing a search that empties the list never unmounts the focused field.

### Pins to add (`test_frontend_agent_inbox.py`)

```python
def test_the_toolbar_is_one_row_like_applications():
    toolbar = _SECTION[_SECTION.index("<ListSearch") : _SECTION.index("{nothingMatches ? (")]
    triggers = re.findall(
        r'<SelectTrigger\s+className="([^"]*)"\s+aria-label="([^"]+)"', toolbar
    )
    assert [label for _, label in triggers] == ["Sort", "Role", "Job board", "Minimum score"]
    assert all("h-8" in cls.split() and "rounded-full" in cls.split() for cls, _ in triggers)
    # No caption stacked over a control, and no free-number field.
    assert "grid gap-1" not in toolbar
    assert "<Input" not in toolbar
    assert 'placeholder="e.g. 50"' not in _SECTION


def test_the_search_box_is_the_shared_one():
    search = _read("components/list-search.tsx")
    assert 'placeholder="Search company or role…"' in search
    assert "aria-label={label}" in search
    assert '<ListSearch label="Search the Agent inbox" value={q} onChange={setQ} />' in _SECTION


def test_the_role_filter_names_roles_not_keys():
    assert "{roleLabel(r)}" in _SECTION
    assert 'role === "all" ? "All roles" : roleLabel(role)' in _SECTION
    assert not re.search(r"^\s*\{r\}\s*$", _SECTION, re.M)


def test_filtering_is_one_pure_function():
    lib = _read("lib/inbox-filter.ts")
    assert not re.search(r"^import (?!type )", lib, re.M)  # node --test loads it
    assert "export const SCORE_FLOORS = [50, 60, 70, 80] as const;" in lib
    assert (
        '`${p.job.company ?? ""} ${p.job.title ?? ""}`.toLowerCase().includes(needle)'
        in lib
    )
    assert "if (score == null || score < minScore) return false;" in lib
    assert "filterProposals(items, { q, role, board, minScore })" in _SECTION
    assert "function filterProposals" not in _SECTION  # one definition


def test_a_filter_that_hides_everything_says_so():
    assert "const nothingMatches = filtered.length === 0;" in _SECTION
    assert 'title="Nothing matches these filters"' in _SECTION
```

### Existing pins that change

- `backend/tests/test_frontend_placeholders.py:38-53` `_PROMPTS`: **add**
  `("components/list-search.tsx", "Search company or role" + _ELLIPSIS),`. Keep the
  `app/applications/page.tsx` entry until Applications adopts `ListSearch`; then delete it
  (`test_named_prompts_are_the_ones_on_screen` fails on a listed prompt that is no longer on screen).
- `backend/tests/test_frontend_color_roles.py:326-328` still holds (the History chips keep
  `variant={active ? "tonal" : "outline"}` and `{active && <Check`).
- `backend/tests/test_frontend_color_roles.py:834-835` (`_PLACED_TEXT`): the OPT and "possible duplicate"
  class strings in `ProposalRow` are untouched; the pin asserts they are still literally present.

### Browser checks

1. **1280, light.** The toolbar is a search pill, then one row: "Best score first", "All roles", "All
   boards", "Any score", all 32px tall and fully rounded like Applications' status Select (compare the two
   pages side by side).
2. **Role labels.** Open Role: items read "Data Scientist", never `data_scientist`.
3. **Search.** Type "acme": only Acme rows stay; clear it: all return. Type "zzz": "Nothing matches these
   filters" appears, the text field keeps focus and the caret (`document.activeElement` is the input).
4. **Score.** Pick "Score 70+": rows without a score and below 70 leave every lane.
5. **Keyboard.** Tab from the search box through the four Selects in order; each opens with Enter/Space,
   Arrow moves, Enter picks, Escape closes and focus returns to its trigger.
6. **Screen reader names** (`read_page`): "Search the Agent inbox", "Sort", "Role", "Job board",
   "Minimum score", each with its value.
7. **768** (sidebar pinned, 462px usable): the four Selects wrap to two lines, nothing overflows the
   page. **375**: the search pill is full width; the Selects wrap two per line. **Dark**: triggers use
   `dark:bg-input/30` like Applications'.

### Risks

- Filter state still resets on reload (as today, and as Applications' search does). URL persistence is a
  separate decision (research §3 recommendation 3).
- Presets remove the ability to type an arbitrary floor such as 65. Open question 5.

---

## A4. A Needs-you count on the sidebar item (owner decision 4)

### Current code

The sidebar has no badges. `NavMenu` renders a bare label (`components/app-sidebar.tsx:167-176`):
```tsx
          <SidebarMenuItem key={item.href}>
            <SidebarMenuButton
              isActive={current !== undefined}
              render={
                <Link href={item.href} aria-current={current}>
                  <Icon />
                  <span>{item.label}</span>
                </Link>
              }
            />
          </SidebarMenuItem>
```
`components/ui/sidebar.tsx:603-619` has shadcn's `SidebarMenuBadge`, but it is an absolutely positioned
SIBLING of the link: its text would not be in the link's accessible name, and it is `pointer-events-none`
over the row's right edge. Not used here.

The inbox's Needs you lane is `["needs_decision", "needs_human"]` (`proposals-section.tsx:82`).

**The cheapest count already exists.** `GET /api/proposals?status=<csv>&limit=1` returns
`total` = the count over the whole filtered set before paging (`routers/proposals.py:189`
`total = db.scalar(select(func.count()).select_from(stmt.subquery()))`), after the same lazy expiry
(`svc.expire_stale(db)`, `:185`) that the inbox runs, so an expired `needs_decision` drops out of both.
`expire_stale` commits only when a row actually expired (`services/proposals.py:425-426`). The funnel
endpoint cannot serve: it folds `needs_decision` into `proposed` (`:262`). **No backend change.**

react-query defaults are `staleTime: 30_000` and `refetchOnWindowFocus: false` (`app/providers.tsx:17,36`).
Every triage mutation invalidates the `["proposals"]` prefix (`triage-actions.tsx:50`,
`app/applications/page.tsx:232`, `app/jobs/[id]/page.tsx:157`, `components/ats-score-panel.tsx:279`). A
connected agent changes proposals outside the tab, so the count also polls.

The sidebar is `collapsible="offcanvas"` (the default, `ui/sidebar.tsx:155`): collapsed, it is off-screen
and `inert`, and there is no icon rail.

### New code

`lib/needs-you.ts` (new)
```ts
import type { ProposalStatus } from "./types";

/**
 * What waits on the user. One list for the inbox's Needs you lane and the
 * sidebar's count, so the two can never disagree about which statuses count.
 * Pure (lib/needs-you.test.ts); pinned by test_frontend_agent_inbox.py.
 */
export const NEEDS_YOU_STATUSES: readonly ProposalStatus[] = ["needs_decision", "needs_human"];

export type NavBadge = { text: string; spoken: string };

/** The sidebar badge for a count. Hidden (null) at 0, and while the count is
 *  unknown (loading, failed, or the server-rendered fallback), so it never
 *  claims a number it does not have. "99+" past 99. `spoken` completes the
 *  link's accessible name: "Agent inbox, 3 need you". */
export function needsYouBadge(count: number | null | undefined): NavBadge | null {
  if (count == null || !Number.isFinite(count) || count < 1) return null;
  const n = Math.floor(count);
  return {
    text: n > 99 ? "99+" : String(n),
    spoken: `${n} ${n === 1 ? "needs" : "need"} you`,
  };
}
```

`lib/needs-you.test.ts` (new)
```ts
import assert from "node:assert/strict";
import { test } from "node:test";

import { NEEDS_YOU_STATUSES, needsYouBadge } from "./needs-you.ts";

test("hidden at zero and while unknown", () => {
  for (const n of [0, -1, null, undefined, Number.NaN]) assert.equal(needsYouBadge(n), null);
});

test("one needs you, several need you", () => {
  assert.deepEqual(needsYouBadge(1), { text: "1", spoken: "1 needs you" });
  assert.deepEqual(needsYouBadge(3), { text: "3", spoken: "3 need you" });
});

test("past 99 the badge caps and the name keeps the real count", () => {
  assert.deepEqual(needsYouBadge(140), { text: "99+", spoken: "140 need you" });
});

test("the lane's statuses", () => {
  assert.deepEqual([...NEEDS_YOU_STATUSES], ["needs_decision", "needs_human"]);
});
```

`hooks/use-needs-you-count.ts` (new)
```ts
"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import { NEEDS_YOU_STATUSES } from "@/lib/needs-you";
import type { ProposalListResponse } from "@/lib/types";

/**
 * How many proposals wait on the user, for the sidebar's Agent inbox badge.
 *
 * `limit=1`: the list endpoint counts the whole filtered set in `total` before
 * paging, after the same lazy expiry as the inbox. The key sits under
 * ["proposals"], so every triage invalidation refreshes it. A connected agent
 * changes proposals from outside this tab, hence the minute poll, which
 * react-query pauses while the tab is hidden.
 */
export function useNeedsYouCount(): number | null {
  const { data } = useQuery({
    queryKey: ["proposals", "needs-you-count"],
    queryFn: () =>
      apiFetch<ProposalListResponse>(
        `/api/proposals?status=${NEEDS_YOU_STATUSES.join(",")}&limit=1`,
      ),
    select: (page) => page.total,
    refetchInterval: 60_000,
  });
  return data ?? null;
}
```

`components/app-sidebar.tsx`

Imports: add
```tsx
import { useNeedsYouCount } from "@/hooks/use-needs-you-count";
import { needsYouBadge, type NavBadge } from "@/lib/needs-you";
```
Below `ACCOUNT_ITEMS`:
```tsx
// The Needs-you count wears the Needs you chip's orange (status-chip.tsx).
// Dark text is orange-300, one step lighter than the chip's orange-400: on the
// current row under the pointer the chip's shade reads 3.88:1, and this one
// holds 4.5:1 on all four row states (test_frontend_color_roles.py).
const NEEDS_YOU_BADGE = "bg-orange-500/10 text-orange-800 dark:text-orange-300";
```
`MainNav` (`:117-150`): read the count once and hand it to the Job search group.
```tsx
function MainNav({ pathname, from }: { pathname: string; from: string | null | undefined }) {
  const fabCurrent = navCurrent(pathname, "/new");
  // Unknown on the server-rendered fallback (no data yet): no badge, the
  // fallback rule (it must not claim state it cannot know).
  const needsYou = needsYouBadge(useNeedsYouCount());
  …
      {NAV_GROUPS.map((group) => (
        <SidebarGroup key={group.label}>
          <SidebarGroupLabel>{group.label}</SidebarGroupLabel>
          <SidebarGroupContent>
            <NavMenu
              items={group.items}
              pathname={pathname}
              from={from}
              badges={{ "/proposals": needsYou }}
            />
          </SidebarGroupContent>
        </SidebarGroup>
      ))}
```
`NavMenu` (`:152-182`):
```tsx
function NavMenu({
  items,
  pathname,
  from,
  badges,
}: {
  items: NavItem[];
  pathname: string;
  from: string | null | undefined;
  badges?: Partial<Record<string, NavBadge | null>>;
}) {
  return (
    <SidebarMenu>
      {items.map((item) => {
        const Icon = item.icon;
        const current = navCurrent(pathname, item.href, from);
        const badge = badges?.[item.href] ?? null;
        return (
          <SidebarMenuItem key={item.href}>
            <SidebarMenuButton
              isActive={current !== undefined}
              render={
                <Link href={item.href} aria-current={current}>
                  <Icon />
                  {/* truncate explicitly: the button's [&>span:last-child]
                      rule no longer reaches the label once a badge follows. */}
                  <span className="min-w-0 truncate">{item.label}</span>
                  {badge ? (
                    <>
                      {/* Seen, not read: the sr-only line below says it in
                          words, so the name is "Agent inbox, 3 need you". */}
                      <span
                        aria-hidden="true"
                        className={cn(
                          "ml-auto inline-flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full px-1.5 text-xs font-medium tabular-nums",
                          NEEDS_YOU_BADGE,
                        )}
                      >
                        {badge.text}
                      </span>
                      <span className="sr-only">, {badge.spoken}</span>
                    </>
                  ) : null}
                </Link>
              }
            />
          </SidebarMenuItem>
        );
      })}
    </SidebarMenu>
  );
}
```
The Account nav passes no `badges`, so it renders exactly as today.

`components/proposals/proposals-section.tsx:82` becomes `const NEEDS_YOU = NEEDS_YOU_STATUSES;` (A3's
import list), and `NEEDS_YOU.includes(p.status)` at `:248` is unchanged in shape.

**Accessible name.** Content is the icon (lucide SVGs carry no title, so nothing), "Agent inbox", the
hidden visible count, and ", 3 need you". Name: "Agent inbox, 3 need you" (with `aria-current`, "…,
current page"). WCAG 2.5.3 Label in Name holds: the name starts with the visible label.

**Hidden at 0**, and while the count is loading or failed. A failed count shows nothing because the badge
is a hint and the inbox page is where the truth and its error state live; a sidebar retry chip would be
noise on every page.

**Collapsed sidebar.** Off-canvas, so the badge goes with it; the reveal pill
(`components/sidebar-reveal-trigger.tsx`) shows no count this round (open question 2). Below 768 the
sidebar is a sheet and the badge shows when it opens.

**Contrast** (both modes, the badge's text over its tint over each row state; minimum 4.5):

| Row state | Surface | Light | Dark |
|---|---|---|---|
| at rest | `--sidebar` | 6.34 | 9.29 |
| hovered | `--sidebar-accent` | 6.09 | 7.77 |
| current | `--secondary-container` | 5.36 | 6.42 |
| current, hovered | `--secondary-container-hover` | 4.67 | 5.42 |

With the chip's `dark:text-orange-400` the last dark cell is **3.88** (fails), which is why the badge
uses `orange-300`.

### Pins to add

`test_frontend_agent_inbox.py`
```python
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
    assert "count < 1) return null;" in lib
    assert 'n > 99 ? "99+" : String(n)' in lib
    assert '`${n} ${n === 1 ? "needs" : "need"} you`' in lib


def test_the_count_is_in_the_link_name_and_not_read_twice():
    assert "const needsYou = needsYouBadge(useNeedsYouCount());" in _SIDEBAR
    assert 'badges={{ "/proposals": needsYou }}' in _SIDEBAR
    badge = _SIDEBAR[_SIDEBAR.index("{badge ? (") :]
    assert badge.index('aria-hidden="true"') < badge.index("{badge.text}")
    assert '<span className="sr-only">, {badge.spoken}</span>' in badge
    assert '<span className="min-w-0 truncate">{item.label}</span>' in _SIDEBAR
```

`backend/tests/test_frontend_color_roles.py`: add the shade to `_TAILWIND` (`:560-645`) and one test.
```python
    "orange-300": (0.837, 0.128, 66.29),
```
```python
_SIDEBAR_BADGE = "bg-orange-500/10 text-orange-800 dark:text-orange-300"


@pytest.mark.parametrize("mode", list(_MODES))
def test_the_needs_you_badge_meets_aa_on_every_sidebar_row_state(mode):
    """The Agent inbox count sits on the sidebar at rest, on a hovered row
    (--sidebar-accent), on the current row (secondary container) and on the
    current row under the pointer (its hover mix). The chip's own dark text,
    orange-400, read 3.88:1 on that last one."""
    assert f'const NEEDS_YOU_BADGE = "{_SIDEBAR_BADGE}";' in _read("components/app-sidebar.tsx")
    t = _MODES[mode]
    mix = _HOVER_MIX["secondary-container"]
    surfaces = {
        "sidebar": _rgb(t, "sidebar"),
        "sidebar-accent": _rgb(t, "sidebar-accent"),
        "secondary-container": _rgb(t, "secondary-container"),
        "secondary-container-hover": _hover(t, "secondary-container", "on-secondary-container", mix[2]),
    }
    for name, under in surfaces.items():
        ratio = _palette_ratio(mode, _SIDEBAR_BADGE, under)
        assert ratio >= 4.5, f"{mode}: needs-you badge on {name} is {ratio:.2f}:1"
```
`test_copied_tailwind_shades_match_the_installed_theme` then checks the new shade against the installed
theme, and `test_every_palette_text_meets_aa_on_page_card_and_popover` picks up the badge's class string
automatically (it needs `orange-300` in the table, or `_chip_colour` raises).

Mutation checks: set the dark text back to `orange-400` (the new test fails on
`secondary-container-hover`); delete `aria-hidden="true"` from the count; change `count < 1` to
`count < 0`.

### Existing pins that change

None. `test_frontend_sidebar_nav.py:15-17` (`navCurrent(`, `aria-current={current}`) still holds.

### Browser checks

1. **Zero.** With no Needs-you proposals, the sidebar row reads "Agent inbox" with no badge;
   `read_page` names the link "Agent inbox".
2. **Three.** Send three proposals to Needs you (`request-decision` twice, `report-failure` once). Within a
   minute, or at once after any triage click, the row shows a pill "3". `read_page`: the link is named
   "Agent inbox, 3 need you"; the "3" is not read separately.
3. **One.** Accept or skip two: the badge reads "1" and the name ends "1 needs you".
4. **Row states, light and dark.** Hover the row; open `/proposals` (current row); hover it there. The pill
   stays legible on each (zoom the region). Tab to the row: the focus ring is not covered by the pill.
5. **Collapse** (Cmd/Ctrl+B): the sidebar leaves with its badge; the reveal pill shows no count; focus goes
   to the pill (existing behaviour). **375**: open the sheet: the badge shows; the label never truncates
   against it.
6. **External change.** Leave `/applications` open, move a proposal to Needs you with curl: the badge
   appears within 60 seconds without a click.

### Risks

- The count reads the server's total while the Needs you lane reads the (filtered, 500-capped) loaded
  list, so with a filter set the lane can show fewer than the badge. The lane heading and the badge measure
  different things; the A7 notice covers the cap.
- One small request a minute per open tab. It is local and uses the status index; no concern at this
  scale.

---

## A5. One word per kind of agent (owner decision 5)

### The vocabulary

| Kind | The word | Where it shows |
|---|---|---|
| The in-app chat agent | **Assistant** | settings capability line, KB point origin |
| External MCP clients (Claude, Codex, ChatGPT desktop) | **connected agent(s)** in running text; **Connected agents** as the Settings tab and card | inbox subtitle, tracker mark, settings, toasts |
| The Chrome extension | **Companion** ("the Companion browser extension" on first mention in a card) | autofill, quick tailor, analytics |
| Chat's and the studio's approval cards | **Suggested edits** / **Suggested project** / **Suggest** | chat cards, Ask for changes sheet |
| A job an agent filed | **proposal** | inbox rows, delete dialog, day batches |

Bare "Agent" survives only inside the proper names **Agent inbox** and **Agent pipeline** (Analytics).
**"hunt"** stays as the name of a connected agent's search run: the owner's own empty-state link says
"Start a hunt" and the skill is `job-hunt`. **"swarm"** and **"lane"** leave the UI.

### Inventory (every user-visible use; current → new)

Rows marked **T-A2** are in files the inbox task owns; the rest are T-A4's. `☐` = needs a pin change.

| # | File:line | Current | New |
|---|---|---|---|
| 1 | `components/app-sidebar.tsx:49` | `Agent Proposals` | `Agent inbox` (A1, T-A3) |
| 2 | `app/proposals/page.tsx:8-9` | `Agent proposals` / `What the hunt found. Submitting still needs your approval.` | `Agent inbox` / `Jobs your connected agents found. Nothing is submitted without your yes.` (A1, T-A2) |
| 3 | `proposals-section.tsx:367` | `Couldn't load agent proposals.` | `Couldn't load your Agent inbox.` (T-A2) |
| 4 | `proposals-section.tsx:392-393` | `No agent proposals yet. Proposals appear here when an agent hunt files applications for your review.` | A6 empty state ☐ (T-A2) |
| 5 | `proposals-section.tsx:417,435,453,471` | captions `Sort` `Role` `Board` `Min score` | removed; `aria-label`s (A3, T-A2) |
| 6 | `app/jobs/[id]/page.tsx:291,316,546` | `Previous proposal in list` / `Back to proposals` / `Next proposal in list` | `Previous job in Agent inbox` / `Back to Agent inbox` / `Next job in Agent inbox` (A1, T-A2) |
| 7 | `app/jobs/[id]/page.tsx:155` | toast `Queued for the next apply run` | `Queued in your Agent inbox` (T-A2) |
| 8 | `app/jobs/[id]/page.tsx:362` | toast `Accepted — queued for apply` (em dash as a clause joiner) | `Accepted. A connected agent can apply to it now.` (T-A2) |
| 9 | `app/jobs/[id]/page.tsx:401` | `{promote.isPending ? "Queueing…" : "Queue for agent"}` | `{promote.isPending ? "Queueing…" : "Queue in Agent inbox"}` (T-A2) |
| 10 | `app/jobs/[id]/page.tsx:342-348` | pill shows the status only | status plus an sr-only by-line (A9, T-A2) |
| 11 | `proposal-agent-panel.tsx:39,58,76` | `Agent proposal` | loading/error: `Agent inbox`; loaded: the by-line (A9, T-A2) |
| 12 | `proposal-agent-panel.tsx:44` | `Couldn't load the agent proposal.` | `Couldn't load this proposal.` (T-A2) |
| 13 | `proposal-agent-panel.tsx:81` | Fact `Proposed` | Fact `Date` (the title now says who and the verb; A9, T-A2) |
| 14 | `proposal-agent-panel.tsx:176` | `All proposals` | `Open Agent inbox` (A1, T-A2) |
| 15 | `app/applications/page.tsx:230` | toast `Queued for the next apply run` | `Queued in your Agent inbox` (**shared file**) |
| 16 | `app/applications/page.tsx:461` | `<SelectLabel>Agent lane</SelectLabel>` | `<SelectLabel>Agent inbox</SelectLabel>` (**shared file**) |
| 17 | `app/applications/page.tsx:590-593` | `<Bot … aria-label="Found by agent" />` | A9 mark: "Proposed by Claude" / "Found by a connected agent" (**shared file**) |
| 18 | `app/applications/page.tsx:636` | `label="Queue for agent apply"` | `label="Queue in Agent inbox"` (**shared file**) |
| 19 | `components/source-toggle.tsx:44` (+ docstring `:10`) | `"You" : "Agent"` | `"You" : "Agents"` (segment; the group is already named "Filter by who found it") |
| 20 | `components/career/points-list.tsx:58,60` | `chat: "Capture"`, `mcp: "Agent"` | `chat: "Assistant"`, `mcp: "Connected agent"` (origin `chat` is written only by the chat tools, `services/chat_tools.py:308,430`; the KB page's Quick capture writes `manual`, `routers/career_kb.py:332`) |
| 21 | `components/career/points-list.tsx:315` | ``title={point.origin_detail ? `Written by ${point.origin_detail}` : undefined}`` | ``title={point.origin_detail ? `Written by ${agentDisplayName(point.origin_detail) ?? point.origin_detail}` : undefined}`` (A9's mapper, so `claude-ai` reads "Claude") |
| 22 | `app/settings/page.tsx:35` | `API keys, models, agent behaviour, and appearance.` | `API keys, models, connected agents and appearance.` (**Settings-tabs appendix owns the file**; hand it this text, or its own tabbed subtitle) |
| 23 | `components/settings/llm-endpoint.tsx:22` | `gates: "the chat agent"` | `gates: "the Assistant in Chat"` (renders "Enables the Assistant in Chat", `:184`) |
| 24 | `components/settings/mcp-workflow-section.tsx:54` | `Agent workflow hints` | `Next-step hints for connected agents` |
| 25 | `mcp-workflow-section.tsx:55` | `Adds a suggested next step to Career Studio's MCP tool results, so Claude or Codex can walk the tailoring workflow without being told each step. Turn it off to keep responses minimal.` | `Adds a suggested next step to what the app tells a connected agent, so Claude or Codex can walk the tailoring workflow without being told each step. Turn it off to keep responses minimal.` |
| 26 | `mcp-workflow-section.tsx:68` | `Suggest the next step in MCP tool results` | `Suggest the next step to connected agents` |
| 27 | `components/settings/auto-apply-section.tsx:34` | hint `Approving a proposal reserves a slot for 24 hours.` ("Approve" is the agent's submit-time record; the user *accepts* in the inbox) | `Your yes before a submit reserves a slot for 24 hours.` |
| 28 | `auto-apply-section.tsx:40` | `Proposals per hunt run` | `Proposals per hunt` |
| 29 | `auto-apply-section.tsx:79` | `Guardrails for the agent hunt-and-apply lane.` | `Limits on what connected agents may do when they find and apply to jobs.` |
| 30 | `auto-apply-section.tsx:164-165` | `The hunt never captures or proposes these companies. Skipping a single posting does not block its company.` | `A connected agent never saves or proposes these companies. Skipping one posting does not block its company.` |
| 31 | `components/analytics/agent-pipeline-card.tsx:41` | `What the hunt swarm captured and how far each stage got.` | `Jobs your connected agents saved, and how far each one got.` |
| 32 | `agent-pipeline-card.tsx:16` | stage `Accepted` | `Queued` (the ONE status vocabulary says `accepted` → "Queued", `status-chip.tsx:129`) |
| 33 | `components/ats-score-panel.tsx:289-290` | `…and any open agent proposal for this job is closed.` | `…and any open proposal in your Agent inbox for this job is closed.` |
| 34 | `components/chat/proposal-card.tsx:67` | `Proposed project` | `Suggested project` |
| 35 | `components/chat/edit-proposal-card.tsx:112` | `Suggested edit` | `` {`Suggested ${proposal.ops_count === 1 ? "edit" : "edits"}`} `` |
| 36 | `components/resume-editor/instruct-sheet.tsx:122-125` | `…Nothing changes until you apply a proposal, and the model may not invent facts…` | `…Nothing changes until you apply a suggestion, and the model may not invent facts…` |
| 37 | `instruct-sheet.tsx:174` | `"Thinking…" : proposal ? "Propose again" : "Propose"` | `"Thinking…" : proposal ? "Suggest again" : "Suggest edits"` |
| 38 | `instruct-sheet.tsx:193-195` | `The resume changed since this was proposed. Propose again to get edits for this version.` | `The resume changed since these edits were suggested. Suggest again to get edits for this version.` ☐ |
| 39 | `instruct-sheet.tsx:204-205` | `No edits proposed. Ask for a change in those words if you want one made.` | `No edits suggested. Ask for a change in those words if you want one made.` |
| 40 | `components/settings/quick-tailor-section.tsx:50` | `…and by the browser extension's Fast tailor.` | `…and by the Companion browser extension's Fast tailor.` |
| 41 | `components/settings/autofill-section.tsx:443` | `Preset answers the browser extension uses to fill job-application forms.` | `Preset answers the Companion browser extension uses to fill job-application forms.` |
| 42 | `autofill-section.tsx:755` | `Allow extension to fill these answers` | `Allow the Companion to fill these answers` |
| 43 | `autofill-section.tsx:777` | `Allow extension to tick agreement boxes` | `Allow the Companion to tick agreement boxes` |
| 44 | `autofill-section.tsx:854` | `Most recent first, matching the extension&apos;s repeated form blocks.` | `Most recent first, matching the Companion&apos;s repeated form blocks.` |
| 45 | `components/analytics/autofill-coverage-card.tsx:99-101` | `…Capture stays on — turn it off in the extension card's ⋯ menu.` | `…Capture stays on. Turn it off in the Companion's ⋯ menu.` |
| 46 | `autofill-coverage-card.tsx:120` | `…and where the extension's fill pipeline fails.` | `…and where the Companion's fill pipeline fails.` |
| 47 | `autofill-coverage-card.tsx:124` | `No telemetry yet. Fill an application with the extension to start capturing.` | `No telemetry yet. Fill an application with the Companion to start capturing.` |

Checked and **kept**:
- `autofill-section.tsx:581` already says "Maestro CS Companion".
- The status label "Proposed" (`status-chip.tsx:126`) and the tracker's Agent-inbox options
  "Proposed / Queued / Needs you / Skipped" (`app/applications/page.tsx:93-98`) name proposal states,
  which is what "proposal" now means.
- `proposals-section.tsx:530` "3 proposals" (day batch), `:834` and `app/jobs/[id]/page.tsx:390`
  "Delete proposal", `triage-actions.tsx:114,116,126` ("Delete this proposal?", "Proposal deleted").
- `new-base-resume-dialog.tsx` "Suggest a selection" already uses the Suggest word.
- "value proposition" (`gap-card.tsx:705`, `tailor/[sessionId]/page.tsx:758`) is ordinary English.
- Code identifiers (`AGENT_LANE_FILTERS`, `ProposalCard`, `EditProposalCard`, `proposeOnce`,
  `promoteJobToAgentQueue`, `source="agent"`, `?source=agent`) stay: they are not on screen, and several
  are pinned by name (`test_frontend_single_flight.py:29,36`, `test_frontend_focus.py:400`).
- MCP docstrings and backend strings (the frozen surface). One backend-composed UI string is listed in
  *Found by reading* instead.

### New code

Each row above is a literal string swap at the quoted line, except these:

`components/career/points-list.tsx` (add the import; rows 20–21)
```tsx
import { agentDisplayName } from "@/lib/agent-name";
…
const ORIGIN_LABELS: Record<KBPointOut["origin"], string> = {
  manual: "Manual",
  ingested: "Document",
  chat: "Assistant",
  consolidated: "Consolidated",
  mcp: "Connected agent",
  gap_elicitation: "Gap answer",
  base_sync: "Base sync",
};
…
          title={
            point.origin_detail
              ? `Written by ${agentDisplayName(point.origin_detail) ?? point.origin_detail}`
              : undefined
          }
```

`components/source-toggle.tsx:10-11,44`
```tsx
/** Segmented All / You / Agents provenance filter — shared by Applications
 * tracker and Analytics Overview. "Agents" are connected agents. */
…
          {s === "all" ? "All" : s === "user" ? "You" : "Agents"}
```

`components/chat/edit-proposal-card.tsx:111-113`
```tsx
        <Badge variant="outline" className="gap-1 text-xs">
          <Sparkles className="size-3" aria-hidden="true" />
          {`Suggested ${proposal.ops_count === 1 ? "edit" : "edits"}`}
        </Badge>
```

`triage-actions.tsx:104-106` (found by reading; the em-dash copy rule):
```tsx
      toast.error(
        `${failed.length} of ${vars.ids.length} could not be ${verb}: ${sample}`,
      );
```

### Pins to add (`backend/tests/test_frontend_agent_words.py`, new, owned by T-A4)

```python
"""Pins: one word per kind of agent (appendix A5).

Assistant is the in-app chat, connected agents are MCP clients, the
Companion is the extension, and chat's approval cards are suggestions, so
"proposal" means only a job an agent filed. Each row is a string that left
the screen and the one that replaced it; identifiers and the API stay.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

# (file, gone, present)
_WORDS = [
    ("components/source-toggle.tsx", '"You" : "Agent"}', '"You" : "Agents"}'),
    ("components/career/points-list.tsx", 'mcp: "Agent",', 'mcp: "Connected agent",'),
    ("components/career/points-list.tsx", 'chat: "Capture",', 'chat: "Assistant",'),
    ("components/settings/llm-endpoint.tsx", 'gates: "the chat agent"', 'gates: "the Assistant in Chat"'),
    ("components/settings/mcp-workflow-section.tsx", 'title="Agent workflow hints"',
     'title="Next-step hints for connected agents"'),
    ("components/settings/mcp-workflow-section.tsx", "Suggest the next step in MCP tool results",
     "Suggest the next step to connected agents"),
    ("components/settings/auto-apply-section.tsx", "Guardrails for the agent hunt-and-apply lane.",
     "Limits on what connected agents may do when they find and apply to jobs."),
    ("components/settings/auto-apply-section.tsx", "Approving a proposal reserves a slot",
     "Your yes before a submit reserves a slot"),
    ("components/settings/auto-apply-section.tsx", "The hunt never captures or proposes",
     "A connected agent never saves or proposes"),
    ("components/analytics/agent-pipeline-card.tsx", "hunt swarm",
     "Jobs your connected agents saved, and how far each one got."),
    ("components/analytics/agent-pipeline-card.tsx", '{ key: "accepted", label: "Accepted"',
     '{ key: "accepted", label: "Queued"'),
    ("components/ats-score-panel.tsx", "any open agent proposal",
     "any open proposal in your Agent inbox"),
    ("components/chat/proposal-card.tsx", "Proposed project", "Suggested project"),
    ("components/resume-editor/instruct-sheet.tsx", '"Propose again" : "Propose"',
     '"Suggest again" : "Suggest edits"'),
    ("components/resume-editor/instruct-sheet.tsx", "No edits proposed.", "No edits suggested."),
    ("components/settings/quick-tailor-section.tsx", "the browser extension's Fast tailor",
     "the Companion browser extension's Fast tailor"),
    ("components/settings/autofill-section.tsx", "Allow extension to fill these answers",
     "Allow the Companion to fill these answers"),
    ("components/settings/autofill-section.tsx", "Allow extension to tick agreement boxes",
     "Allow the Companion to tick agreement boxes"),
    ("components/analytics/autofill-coverage-card.tsx", "with the extension to start capturing",
     "with the Companion to start capturing"),
]


@pytest.mark.parametrize(
    "rel,gone,present", _WORDS, ids=[f"{r.rsplit('/', 1)[-1]}:{i}" for i, (r, _, _) in enumerate(_WORDS)]
)
def test_one_word_per_kind_of_agent(rel: str, gone: str, present: str):
    src = (_FRONTEND / rel).read_text(encoding="utf-8")
    assert gone not in src, f"{rel} still says {gone!r}"
    assert present in src, f"{rel} lost {present!r}"


def test_no_screen_says_swarm_or_the_chat_agent():
    for root in ("app", "components"):
        for path in (_FRONTEND / root).rglob("*.tsx"):
            src = path.read_text(encoding="utf-8")
            for word in ("hunt swarm", "the chat agent", "Found by agent", "Agent lane"):
                assert word not in src, f"{path.relative_to(_FRONTEND)}: {word!r}"
```
The four shared-file rows (15–18) and the T-A2 rows are pinned in `test_frontend_agent_inbox.py`
(A1, A6, A9) and by the sweep test above ("Found by agent", "Agent lane").

### Existing pins that change

- `backend/tests/test_frontend_dialog_drafts.py:188` ☐
  ```python
      assert "The resume changed since these edits were suggested." in note
  ```
- `backend/tests/test_frontend_query_error_states.py:75` ☐ (A6 owns the new marker)
  ```python
      ("components/proposals/proposals-section.tsx", "No proposals yet"),
  ```
- No pin reads any other string in the table (searched `backend/tests/` for each current string).

### Browser checks

1. **Chat** (`/chat`, pinned résumé): ask for an edit. The card's badge reads "Suggested edit" (one op) or
   "Suggested edits". Ask it to draft a project: "Suggested project".
2. **Studio Ask for changes**: the button reads "Suggest edits", then "Suggest again"; Save the résumé
   mid-way: the stale note reads "…since these edits were suggested. Suggest again…". Keyboard: the button
   keeps focus while it works (existing `focusableWhenDisabled`).
3. **Career KB** point chips: a point written over MCP reads "Connected agent"; hover shows "Written by
   Claude" for `origin_detail = claude-ai`; a point from chat reads "Assistant".
4. **Settings**: the two cards and the capability line read as in the table; the Autofill card says
   "Companion".
5. **Tracker and Analytics** SourceToggle: "All · You · Agents" with the Check on the pressed one.
6. **Dark, 768, 375**: no string overflows its control (the longest new button label is "Queue in Agent
   inbox" in the job header cluster, which already wraps: `app/jobs/[id]/page.tsx:341`).

### Risks

- "Agents" in the three-segment toggle is the one place the full "connected agents" does not fit. Open
  question 3.
- The chat nav item still says "Chat"; calling the in-app agent "Assistant" in Settings while the nav says
  Chat is deliberate for now (open question 4).

---

## A6. The empty state (owner decision 6)

### Current code

`components/proposals/proposals-section.tsx:386-398`
```tsx
  if (items.length === 0) {
    return (
      <div className="flex flex-col gap-5">
        <FunnelStrip />
        <Card>
          <CardContent className="text-muted-foreground py-10 text-center text-sm">
            No agent proposals yet. Proposals appear here when an agent hunt
            files applications for your review.
          </CardContent>
        </Card>
      </div>
    );
  }
```
`components/empty-state.tsx:19-49` is the one list empty state (its docstring records that Proposals was
the odd one out). External-link convention: `app/settings/page.tsx:37-51`.

**Anchors** (GitHub lowercases, drops everything but letters, digits, spaces and hyphens, and turns spaces
into hyphens):
- `README.md:554` `### Going all the way: agent applications` → `#going-all-the-way-agent-applications`.
- `docs/GETTING_STARTED.md:183` `## 5. Connect your AI assistant (optional)` →
  `#5-connect-your-ai-assistant-optional` (the guide's own contents line at `:15` uses the same anchor).
- `docs/skills/README.md` exists on local main.

**These resolve only after local main is pushed.** On `origin/main` (`b4afd7ef`), `docs/skills/README.md`
does not exist, the README heading is `### Going all the way: the proposal ledger`, and GETTING_STARTED
§5 is "The browser extension". The pin below computes the anchors from the files in this checkout, so a
later heading rename fails CI instead of breaking the link.

### New code

`lib/agent-links.ts` (new; no imports)
```ts
/**
 * Where the app sends a user to learn about connected agents. Pinned against
 * the headings they point at (test_frontend_agent_inbox.py), so renaming a
 * README section fails CI instead of breaking a link.
 */
const REPO = "https://github.com/seinun-ai/maestro-career-studio/blob/main";

export const JOB_HUNT_SKILL_URL = `${REPO}/docs/skills/README.md`;
export const AGENT_APPLICATIONS_URL = `${REPO}/README.md#going-all-the-way-agent-applications`;
export const CONNECT_AGENT_GUIDE_URL = `${REPO}/docs/GETTING_STARTED.md#5-connect-your-ai-assistant-optional`;
/** The Settings tab the Settings-tabs appendix adds (A8 designs its content). */
export const CONNECTED_AGENTS_SETTINGS = "/settings?tab=agents";
```

`components/proposals/proposals-section.tsx` replacing `:386-398` (shown only when the inbox holds no
proposals at all, after load; a failed load branches earlier, and a filter that hides everything is A3's
state):
```tsx
  if (items.length === 0) {
    return (
      <EmptyState
        icon={Bot}
        title="No proposals yet"
        description="Proposals come from an AI agent you connect over MCP (Claude, Codex, the ChatGPT desktop app), never from the app itself. Nothing is submitted without your yes."
        action={
          <div className="flex max-w-full flex-col items-center gap-2 px-4">
            {/* The label is long; let it wrap at 375 instead of overflowing. */}
            <Button
              nativeButton={false}
              className="h-auto min-h-8 max-w-full py-1.5 whitespace-normal"
              render={
                <a href={JOB_HUNT_SKILL_URL} target="_blank" rel="noopener noreferrer">
                  <BookOpen className="size-4" />
                  Start a hunt: install the ready-made job-hunt skill
                </a>
              }
            />
            <div className="flex flex-wrap justify-center gap-2">
              <Button
                variant="ghost"
                nativeButton={false}
                render={
                  <a href={AGENT_APPLICATIONS_URL} target="_blank" rel="noopener noreferrer">
                    How agent applications work
                  </a>
                }
              />
              <Button
                variant="ghost"
                nativeButton={false}
                render={
                  <Link href={CONNECTED_AGENTS_SETTINGS}>
                    <SettingsIcon className="size-4" />
                    Connect an agent
                  </Link>
                }
              />
            </div>
          </div>
        }
      />
    );
  }
```
`EmptyState` takes a string description, so the owner's copy goes in whole; a later copy audit edits one
string.

### Pins to add (`test_frontend_agent_inbox.py`)

```python
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


def test_the_empty_state_links_point_at_real_headings():
    links = _read("lib/agent-links.ts")
    readme = (_ROOT / "README.md").read_text(encoding="utf-8")
    heading = re.search(r"^### (Going all the way: .+)$", readme, re.M).group(1)
    assert f"/README.md#{_github_slug(heading)}`" in links
    guide = (_ROOT / "docs/GETTING_STARTED.md").read_text(encoding="utf-8")
    section = re.search(r"^## (5\. .+)$", guide, re.M).group(1)
    assert f"/docs/GETTING_STARTED.md#{_github_slug(section)}`" in links
    assert (_ROOT / "docs/skills/README.md").exists()
    assert "/docs/skills/README.md`" in links
    assert 'export const CONNECTED_AGENTS_SETTINGS = "/settings?tab=agents";' in links
```

### Existing pins that change

`backend/tests/test_frontend_query_error_states.py:75` marker `"No agent proposals yet"` →
`"No proposals yet"`. The pin still proves the failure branch (`:362`) precedes the empty state.

### Browser checks

1. **Empty DB, 1280, light.** `/proposals` shows the dashed empty state with the robot icon, the two
   sentences, a filled "Start a hunt…" button and two ghost links. No toolbar, no cap notice.
2. **Links.** Middle-click is not needed: each external link opens a new tab
   (`read_network_requests` / the tabs list), at the skills README and at the README section. "Connect an
   agent" navigates in the same tab to `/settings?tab=agents` and the Connected agents tab is selected (once
   the Settings-tabs appendix lands; before that, `/settings` renders its flat page).
3. **Keyboard.** Tab reaches the three links in order; each shows the solid focus ring; Enter follows.
4. **375.** The primary label wraps onto two lines inside its button; no horizontal scroll. **768** and
   **dark**: the ghost links read at AA (they are `Button` ghost, already measured).
5. **Failure** is not the empty state: stop uvicorn and reload: `LoadErrorState`, never "No proposals yet".

### Risks

- The two GitHub links 404 or miss their anchor until local main is pushed (above).
- If the Settings-tabs appendix lands after this one, "Connect an agent" lands on the Settings page without
  the tab; nothing breaks.

---

## A7. "Showing your 500 most recent" at the end of the list (owner decision 7)

### Current code

- `proposals-section.tsx:191-192` `apiFetch<ProposalListResponse>("/api/proposals?limit=500")`; the
  response carries `total` over the unpaged set (`routers/proposals.py:189,211`; typed in
  `lib/types.ts:1860-1863`).
- Applications: `app/applications/page.tsx:191,195` fetch `?limit=500` from two endpoints that return
  plain arrays (no total).
- Server paging is deferred: SYSTEM.md §11 item 5.

### New code

`lib/list-cap.ts` (new; no imports)
```ts
/**
 * The list pages load at most LIST_CAP rows (SYSTEM.md §11 item 5: server
 * paging is deferred). A list cut there says so at its end instead of
 * silently dropping older rows. Pure (lib/list-cap.test.ts); pinned by
 * test_frontend_agent_inbox.py. Used by the Agent inbox and Applications.
 */
export const LIST_CAP = 500;

export type ListCapState =
  | { capped: false }
  | { capped: true; shown: number; total: number | null };

/**
 * `total` is the server's count when the endpoint returns one (proposals).
 * Without it (applications, saved jobs), a page that came back exactly full
 * is taken as cut: the next row cannot be seen from here.
 */
export function listCap(
  loaded: number,
  total?: number | null,
  cap: number = LIST_CAP,
): ListCapState {
  if (total != null) {
    return total > loaded ? { capped: true, shown: loaded, total } : { capped: false };
  }
  return loaded >= cap ? { capped: true, shown: loaded, total: null } : { capped: false };
}

/** "Showing your 500 most recent proposals of 612. Older ones aren't shown." */
export function listCapText(state: ListCapState, noun: string): string | null {
  if (!state.capped) return null;
  const of = state.total != null ? ` of ${state.total}` : "";
  return `Showing your ${state.shown} most recent ${noun}${of}. Older ones aren't shown.`;
}
```

`lib/list-cap.test.ts` (new)
```ts
import assert from "node:assert/strict";
import { test } from "node:test";

import { LIST_CAP, listCap, listCapText } from "./list-cap.ts";

test("with a server total, cut means the total is larger than what loaded", () => {
  assert.deepEqual(listCap(500, 612), { capped: true, shown: 500, total: 612 });
  assert.deepEqual(listCap(500, 500), { capped: false });
  assert.deepEqual(listCap(12, 12), { capped: false });
});

test("without a total, a full page is taken as cut", () => {
  assert.deepEqual(listCap(LIST_CAP), { capped: true, shown: 500, total: null });
  assert.deepEqual(listCap(499), { capped: false });
});

test("the words", () => {
  assert.equal(
    listCapText(listCap(500, 612), "proposals"),
    "Showing your 500 most recent proposals of 612. Older ones aren't shown.",
  );
  assert.equal(
    listCapText(listCap(500), "applications"),
    "Showing your 500 most recent applications. Older ones aren't shown.",
  );
  assert.equal(listCapText(listCap(3, 3), "proposals"), null);
});
```

`components/list-cap-notice.tsx` (new)
```tsx
import { Info } from "lucide-react";

import { listCapText, type ListCapState } from "@/lib/list-cap";

/**
 * The end-of-list line for a list the client cut at LIST_CAP. Static text,
 * not a live region: it changes only when the list itself loads. Renders
 * nothing when the list is whole.
 */
export function ListCapNotice({ state, noun }: { state: ListCapState; noun: string }) {
  const text = listCapText(state, noun);
  if (!text) return null;
  return (
    <p className="text-muted-foreground flex items-start gap-2 text-sm">
      <Info aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
      {text}
    </p>
  );
}
```

In the inbox (A3's main return, after the lanes and History, before `BulkBar`):
```tsx
      <ListCapNotice state={listCap(items.length, data?.total)} noun="proposals" />
```
**For the Applications appendix:** `listCap(apps.data?.length ?? 0)` and
`listCap(savedJobs.data?.length ?? 0)` (both endpoints lack a total), with nouns "applications" and
"saved jobs", rendered after the table; replace `?limit=500` with `` `?limit=${LIST_CAP}` ``.

### Pins to add (`test_frontend_agent_inbox.py`)

```python
def test_the_list_cap_is_one_constant_and_honest():
    lib = _read("lib/list-cap.ts")
    assert not re.search(r"^import ", lib, re.M)
    assert "export const LIST_CAP = 500;" in lib
    assert "return total > loaded ? { capped: true, shown: loaded, total } : { capped: false };" in lib
    assert (
        "return loaded >= cap ? { capped: true, shown: loaded, total: null } : { capped: false };"
        in lib
    )
    assert "`/api/proposals?limit=${LIST_CAP}`" in _SECTION
    assert "limit=500" not in _SECTION


def test_the_inbox_says_at_its_end_when_the_list_was_cut():
    notice = _SECTION.index(
        '<ListCapNotice state={listCap(items.length, data?.total)} noun="proposals" />'
    )
    assert _SECTION.index("History ·") < notice < _SECTION.index("<BulkBar")
    component = _read("components/list-cap-notice.tsx")
    assert "listCapText(state, noun)" in component
    assert "aria-live" not in component
```

### Existing pins that change

None.

### Browser checks

1. **Below the cap** (the seed): no notice anywhere on the page.
2. **Over the cap.** Seed 520 agent jobs and file a proposal for each (loop the seeding script, then curl
   in a loop). Reload `/proposals`: after History, "Showing your 500 most recent proposals of 520. Older
   ones aren't shown." with an info icon. `read_page`: plain text, not a live region.
3. **Exactly 500**: no notice (`total` equals what loaded).
4. **Dark, 768, 375**: the line wraps under the icon; the fixed BulkBar (select a triage row) does not
   cover it (the page keeps its `pb-20`).

### Risks

- Beyond 500, the Needs you lane can miss old rows that the sidebar count includes (A4 risk). The notice
  is the honest statement; server paging (§11 item 5) is the fix.

---

## A8. Settings › Connected agents: the tab's content (owner decision 8)

The Settings-tabs appendix builds the tab container (`/settings?tab=agents`) and owns
`app/settings/page.tsx`. This appendix supplies what goes inside: a new explainer card, then the two
existing cards moved as they are (A5 rows 24–30 change their words).

### Current code

`app/settings/page.tsx:54-61` renders the cards in one column:
```tsx
      <ApiKeysSection />
      <ModelsSection />
      <QuickTailorSection />
      <AutoApplySection />
      <McpWorkflowSection />
      <PromptsSection />
      <AppearanceSection />
      <AboutSection />
```
Nothing in the web app explains what a connected agent is. The only mention of external clients is the
hints card's description (`mcp-workflow-section.tsx:55`). Deep-link ids: `id="auto-apply"`
(`auto-apply-section.tsx:77`) and `id="agent-hints"` (`mcp-workflow-section.tsx:53`); no in-app link
targets either today (`git grep` for `#auto-apply`, `agent-hints` finds only the definitions).

Facts the card may state (each checked):
- Clients: Claude Desktop and Claude Code, the Codex CLI, the ChatGPT desktop app; not claude.ai or
  chatgpt.com in a browser (`docs/GETTING_STARTED.md:183-190`, `README.md:437-439`).
- The daily cap is enforced by the server: `services/proposals._enforce_daily_cap` raises before a slot is
  reserved.
- MCP has no delete tool for the career record (SYSTEM.md §7, "No delete tool").
- Nothing is submitted from the web app itself (`README.md:572-573`).
- The yes before a submit is recorded by the agent: "an audit trail and a volume limit, not a lock"
  (`README.md:575-579`).
- `scripts/setup-mcp.sh` is needed only for Cursor, Windsurf and other apps; Claude and Codex/ChatGPT
  install from their own settings (`docs/GETTING_STARTED.md:192-233`). So the card links the guide section
  and does **not** name the script: a new user on Claude or Codex never needs it, and the linked section
  covers the rest.

### New code

`components/settings/connected-agents-card.tsx` (new)
```tsx
"use client";

import { useId } from "react";
import { BookOpen } from "lucide-react";

import { GuardedLink as Link } from "@/components/guarded-link";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { CONNECT_AGENT_GUIDE_URL, JOB_HUNT_SKILL_URL } from "@/lib/agent-links";

/**
 * What a connected agent is, first in Settings › Connected agents, above the
 * Auto-apply limits and the next-step hints it explains.
 *
 * Not a SettingCard: it fetches nothing, so it has no loading or error state
 * (the Appearance precedent). Every "can't" is one the server or the tool set
 * enforces; the one guarantee that is only recorded (the yes before a submit)
 * is said to be a record, not a lock, as the README says.
 */
export function ConnectedAgentsCard() {
  const canId = useId();
  const cantId = useId();
  return (
    <Card id="connected-agents">
      <CardHeader>
        <CardTitle>Connected agents</CardTitle>
        <CardDescription>
          AI apps on this computer that use Career Studio for you over MCP: Claude, Codex or the
          ChatGPT desktop app.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-5 text-sm">
        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <p id={canId} className="mb-1.5 font-medium">
              They can
            </p>
            <ul aria-labelledby={canId} className="text-muted-foreground list-disc space-y-1 pl-5">
              <li>Save and score job postings, and tailor your resumes.</li>
              <li>Read your career record and job preferences.</li>
              <li>
                Put the jobs they find in your{" "}
                <Link href="/proposals" className="text-primary underline underline-offset-4">
                  Agent inbox
                </Link>
                .
              </li>
            </ul>
          </div>
          <div>
            <p id={cantId} className="mb-1.5 font-medium">
              They can&apos;t
            </p>
            <ul aria-labelledby={cantId} className="text-muted-foreground list-disc space-y-1 pl-5">
              <li>Go past the daily submission cap below.</li>
              <li>Delete your career record.</li>
              <li>Connect from claude.ai or chatgpt.com in a browser.</li>
            </ul>
          </div>
        </div>
        <p className="text-muted-foreground max-w-[65ch]">
          This web app never submits anything. Before each submit, the agent asks for your yes and
          records it. That record is an audit trail, not a lock, so run apply sessions while you
          watch.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            nativeButton={false}
            render={
              <a href={CONNECT_AGENT_GUIDE_URL} target="_blank" rel="noopener noreferrer">
                <BookOpen className="size-4" />
                How to connect an agent
              </a>
            }
          />
          <Button
            variant="outline"
            size="sm"
            nativeButton={false}
            render={
              <a href={JOB_HUNT_SKILL_URL} target="_blank" rel="noopener noreferrer">
                <BookOpen className="size-4" />
                Ready-made skills
              </a>
            }
          />
        </div>
      </CardContent>
    </Card>
  );
}
```
Sub-heads are `<p>` named into their lists, not `<h3>`: card titles are `<div>`s here, so an `<h3>` would
skip levels under the page `<h1>`. The in-card link is `text-primary` (the link-colour rule,
`test_underlined_links_take_a_colour_role`).

**The tab's content, in order** (for the Settings-tabs appendix to mount):
```tsx
<ConnectedAgentsCard />
<AutoApplySection />
<McpWorkflowSection />
```
`id="auto-apply"` and `id="agent-hints"` stay, so a future deep link (`/settings?tab=agents#auto-apply`)
works once the tabs appendix resolves hash targets inside a tab.

### Pins to add (`test_frontend_agent_words.py`, T-A4)

```python
def test_the_connected_agents_card_explains_before_the_limits():
    card = (_FRONTEND / "components/settings/connected-agents-card.tsx").read_text(encoding="utf-8")
    assert 'id="connected-agents"' in card
    assert "<SettingCard" not in card  # fetches nothing: the Appearance precedent
    assert "an audit trail, not a lock" in card
    assert "href={CONNECT_AGENT_GUIDE_URL}" in card and "href={JOB_HUNT_SKILL_URL}" in card
    assert card.count('target="_blank" rel="noopener noreferrer"') == 2
    assert "setup-mcp.sh" not in card  # only Cursor-and-others need it; the guide covers it
```
The Settings-tabs appendix pins the mount order (`<ConnectedAgentsCard />` before `<AutoApplySection />`
before `<McpWorkflowSection />` inside the agents tab).

### Existing pins that change

None. `test_settings_cards_route_through_the_shared_shell` lists the API-reading cards; the new card
reads nothing and is deliberately absent, like `appearance-section.tsx`.

### Browser checks

1. **`/settings?tab=agents`, 1280, light.** The explainer card, then Auto-apply, then Next-step hints for
   connected agents. Two columns "They can" / "They can't".
2. **Links.** "Agent inbox" navigates in place; the two outline buttons open new tabs at GETTING_STARTED
   §5 and the skills README.
3. **Keyboard.** Tab order: Agent inbox link, How to connect an agent, Ready-made skills, then the
   Auto-apply fields. Every stop shows the solid ring.
4. **Screen reader** (`read_page`): each list is named "They can" / "They can't".
5. **375**: the two lists stack; the buttons wrap. **768** with the sidebar pinned: two columns only from
   `sm` (640px of card width is not reached at 462px usable, so they stack; expected). **Dark**: muted list
   text on the card is pinned at 4.5:1.

### Risks

- Copy length: the card is the longest prose in Settings. The copy audit may trim it; the pin holds only
  the honesty sentence and the links.

---

## A9. Every proposal names who filed it ("proposed by", planner's scope addition)

### What exists

- **Model** `backend/app/models/application_proposal.py:17-47`: no filer column.
- **Create** `backend/app/routers/proposals.py:88-164` → `services/proposals.py:57-68`
  `create_proposal(session, *, job_id, application_id=None, referral_id=None, fit=None, plan=None)`. An
  open proposal for the job is returned as-is (`:96-130`, idempotent).
- **Reads** build `ProposalRead`/`ProposalDetail` field by field: the list at `routers/proposals.py:194-211`
  and `_detail` at `:67-85`. `schemas/proposal.py:76-92` `ProposalRead`, `:109-113` `ProposalDetail`.
- **Job reads** annotate the newest proposal as transient attributes: list `routers/jobs.py:341-359`,
  detail `:524-534`; exposed as `proposal_status`/`proposal_id` on `JobRead` (`schemas/job.py:37-40`) and
  `JobSummary` (`:89-90`); typed in `frontend/lib/types.ts:57-61`.
- **The client name is already plumbed for KB writes.** `mcp_server/server.py:102-120` `_client_label(ctx)`
  reads `ctx.session.client_params.clientInfo.name` (what the client declared at `initialize`), falling
  back to `MAESTRO_CS_MCP_CLIENT`. KB tools take `ctx: Context | None = None` (FastMCP injects it and keeps
  it out of the input schema) and pass `origin_detail=_client_label(ctx)`
  (`server.py:388-401`). `mcp_server/client.py:31-37` `_origin_headers` sends `X-Maestro-CS-Origin: mcp`
  plus `X-Maestro-CS-Origin-Detail: <name>`. The backend reads them with
  `app/write_origin.get_write_origin` (closed origin set `{"mcp"}`, detail trimmed to 120 chars). Verified
  in the installed `mcp` package: `ServerSession.client_params -> InitializeRequestParams | None` and
  `Context.session -> request_context.session`. Real names seen in the ecosystem: `claude-ai` (Claude
  Desktop), `codex-mcp-client` (Codex); ChatGPT desktop's is unverified (open question 8).
- **MCP propose** `server.py:1557-1582` → `client.py:994-1009`: no headers today.
- **Web queue** `frontend/lib/api.ts:190-215` `promoteJobToAgentQueue`: POSTs a proposal with
  `plan: { summary: "Promoted from the tracker by the user" }` and `fit.decided_by: "user"`, then PATCHes it
  to `accepted`. That fixed summary identifies every past web promotion exactly.
- **Migrations.** The SQLite chain is ONE baseline `871d0425b64c`; this is its first revision. The
  first-boot Postgres import (`app/tools/migrate_from_postgres.copy_database`, `:164-171`) **refuses** when
  the source table lacks any model column ("source lacks […]"), and it brings the source to the legacy
  chain's head (`85a1bb628e28`) before copying. So a model column needs a legacy revision too, or the
  import fails closed for every user still on Postgres.

### Design

- **Column** `application_proposals.proposed_by TEXT NULL`. Values: `"you"` (the web app's queue), the MCP
  client's raw `clientInfo.name` (≤120 chars), or NULL (unknown: an MCP client that declared no name, or a
  REST caller that is neither).
- **Who sets it.** In `create_proposal`: when `X-Maestro-CS-Origin: mcp` is present, `proposed_by` is the
  header's detail (possibly NULL), and the body cannot override it, so an agent can never file as "you".
  Otherwise it is the body's `proposed_by`, which accepts only `"you"` (`Literal["you"] | None`, 422 on
  anything else). The idempotent path keeps the first filer.
- **Backfill** in both chains: rows whose `plan_json.summary` is the web promotion's fixed text become
  `"you"`. Everything else stays NULL and reads "a connected agent", which is true for every other past
  proposal (the only other filer was MCP).
- **Reads** add `proposed_by` to `ProposalRead` (list and detail, so MCP `list_proposals`/`get_proposal`
  pass it through) and `proposal_proposed_by` to `JobRead`/`JobSummary` (tracker and job page).
- **Display** in the frontend, from one pure mapper: raw names map to "Claude", "Codex", "ChatGPT" (and a
  few more); an unknown name is title-cased, never shown as a slug; `"you"` reads "Queued by you" (a web
  promotion is always queued at once); NULL reads "Proposed by a connected agent".
- **Where it shows**:
  - Inbox row: a meta line "Proposed by Claude · 2 days ago" / "Queued by you · 3 hours ago".
  - Overview card: its title is the by-line ("Proposed by Claude").
  - Job header pill: the status stays the visible text (it is the ONE status vocabulary,
    `PROPOSAL_STATUS_CHIP`); the by-line is its `title` and an sr-only prefix, so a screen reader hears
    "Proposed by Claude, status Proposed". The Overview card, first on the default tab, carries the visible
    line. Open question 7 if the owner wants it visible in the header.
  - Tracker row mark (the `Bot` on an agent-captured row): "Proposed by Claude" when the job's newest
    proposal names a client, else "Found by a connected agent".

### New code: backend

`backend/app/models/application_proposal.py` (after `reason`, `:39`)
```python
    reason: Mapped[str | None] = mapped_column(Text)
    # Who filed it: "you" (the web app's Queue in Agent inbox), the MCP
    # client's self-declared clientInfo.name ("claude-ai"), or NULL when
    # unknown. A label, not an identity (mcp_server.server._client_label).
    proposed_by: Mapped[str | None] = mapped_column(Text)
```

`backend/migrations/versions/3ac279fcc4b9_application_proposals_proposed_by.py` (new; id from
`uuid.uuid4().hex[:12]`)
```python
"""application_proposals.proposed_by

Who filed a proposal: "you" for the web app's queue, the MCP client's
clientInfo.name for a connected agent, NULL when unknown. Backfills the web
app's own promotions, which carry a fixed plan summary
(frontend/lib/api.ts promoteJobToAgentQueue). The legacy Postgres chain gets
the same column in 08b05599ef28, or the first-boot import refuses the
source ("source lacks ['proposed_by']").

Revision ID: 3ac279fcc4b9
Revises: 871d0425b64c
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3ac279fcc4b9"
down_revision: Union[str, Sequence[str], None] = "871d0425b64c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PROMOTED = "Promoted from the tracker by the user"


def upgrade() -> None:
    with op.batch_alter_table("application_proposals", schema=None) as batch_op:
        batch_op.add_column(sa.Column("proposed_by", sa.Text(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE application_proposals SET proposed_by = 'you' "
            "WHERE json_extract(plan_json, '$.summary') = :summary"
        ).bindparams(summary=PROMOTED)
    )


def downgrade() -> None:
    with op.batch_alter_table("application_proposals", schema=None) as batch_op:
        batch_op.drop_column("proposed_by")
```

`backend/legacy_postgres/migrations/versions/08b05599ef28_application_proposals_proposed_by.py` (new)
```python
"""application_proposals.proposed_by (mirror of the SQLite chain's 3ac279fcc4b9)

The first-boot import copies every model column and refuses a source that
lacks one, so the boxed Postgres chain gains the column (and the same
backfill) before the copy. Delete with this chain (SYSTEM.md §13
postgres-to-sqlite).

Revision ID: 08b05599ef28
Revises: 85a1bb628e28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "08b05599ef28"
down_revision: Union[str, Sequence[str], None] = "85a1bb628e28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("application_proposals", sa.Column("proposed_by", sa.Text(), nullable=True))
    op.execute(
        "UPDATE application_proposals SET proposed_by = 'you' "
        "WHERE plan_json->>'summary' = 'Promoted from the tracker by the user'"
    )


def downgrade() -> None:
    op.drop_column("application_proposals", "proposed_by")
```

`backend/app/schemas/proposal.py`
```python
class ProposalCreate(BaseModel):
    job_id: UUID
    application_id: UUID | None = None
    referral_id: UUID | None = None
    fit: dict[str, Any] | None = None
    plan: dict[str, Any] | None = None
    # The web app's own queue says "you". Nothing else is accepted from a body:
    # an MCP filer is named by the X-Maestro-CS-Origin headers, which win.
    proposed_by: Literal["you"] | None = None
…
class ProposalRead(BaseModel):
    …
    reason: str | None = None
    proposed_by: str | None = None
    expires_at: datetime | None = None
```

`backend/app/services/proposals.py:57-65`
```python
def create_proposal(session, *, job_id: UUID, application_id: UUID | None = None,
                    referral_id: UUID | None = None,
                    fit=None, plan=None, proposed_by: str | None = None) -> ApplicationProposal:
    cfg = auto_apply_settings.get_settings(session)
    prop = ApplicationProposal(
        job_id=job_id, application_id=application_id, referral_id=referral_id,
        status="pending_review", fit_json=fit, plan_json=plan, proposed_by=proposed_by,
        expires_at=datetime.now(UTC) + timedelta(days=cfg.proposal_expiry_days),
    )
```

`backend/app/routers/proposals.py`
```python
from app.write_origin import WriteOrigin, get_write_origin
…
@router.post("", response_model=ProposalDetail)
def create_proposal(
    payload: ProposalCreate,
    db: Annotated[Session, Depends(get_db)],
    response: Response,
    write_origin: Annotated[WriteOrigin, Depends(get_write_origin)],
):
    …
    # An MCP filing is named by its client (the header), and cannot claim the
    # web app's "you" through the body. The idempotent return above keeps the
    # first filer.
    proposed_by = write_origin.detail if write_origin.origin == "mcp" else payload.proposed_by
    prop = svc.create_proposal(
        db,
        job_id=payload.job_id,
        application_id=payload.application_id,
        referral_id=payload.referral_id,
        fit=payload.fit,
        plan=payload.plan,
        proposed_by=proposed_by,
    )
```
In `_detail` (`:67-85`) and the list's `ProposalRead(...)` (`:195-210`) add
`proposed_by=prop.proposed_by,` after `reason=prop.reason,`.

`backend/app/schemas/job.py` (both `JobRead` after `proposal_id` at `:40`, and `JobSummary` after `:90`)
```python
    # Who filed the newest proposal (same query as proposal_status): the
    # tracker's agent mark and the job page's pill name them.
    proposal_proposed_by: str | None = None
```

`backend/app/routers/jobs.py:341-359` (list)
```python
        proposal_rows = db.execute(
            select(
                ApplicationProposal.job_id,
                ApplicationProposal.id,
                ApplicationProposal.status,
                ApplicationProposal.proposed_by,
            )
            .where(ApplicationProposal.job_id.in_([job.id for job in rows]))
            .order_by(ApplicationProposal.created_at.desc())
        ).all()
        for job_id, prop_id, status, proposed_by in proposal_rows:
            newest.setdefault(job_id, (prop_id, status, proposed_by))
        for job in rows:
            hit = newest.get(job.id)
            if hit is None:
                job.proposal_status = None
                job.proposal_id = None
                job.proposal_proposed_by = None
            else:
                job.proposal_id, job.proposal_status, job.proposal_proposed_by = hit
```
`:524-534` (detail): select `ApplicationProposal.proposed_by` as a third column and set
`job.proposal_proposed_by` in both branches the same way.

`backend/mcp_server/client.py:994-1009`
```python
    def propose_application(
        self,
        job_id: str,
        fit: dict | None = None,
        plan: dict | None = None,
        application_id: str | None = None,
        referral_id: str | None = None,
        origin_detail: str | None = None,
    ) -> Any:
        payload = _drop_none(
            job_id=job_id,
            fit=fit,
            plan=plan,
            application_id=application_id,
            referral_id=referral_id,
        )
        # The origin headers name the filer (the proposal's proposed_by),
        # exactly as KB writes name their author.
        return self._request(
            "POST", "/api/proposals", json=payload, headers=_origin_headers(origin_detail),
        )
```

`backend/mcp_server/server.py:1557-1582`
```python
def propose_application(
    job_id: str,
    fit: dict | None = None,
    plan: dict | None = None,
    application_id: str | None = None,
    referral_id: str | None = None,
    ctx: Context | None = None,
) -> Any:
    """…docstring unchanged…"""
    return _client.propose_application(
        job_id=job_id,
        fit=fit,
        plan=plan,
        application_id=application_id,
        referral_id=referral_id,
        origin_detail=_client_label(ctx),
    )
```
Optional, one clause on `list_proposals`' docstring (`:1588-1593`, far under budget): "Each item's
`proposed_by` names who filed it: the MCP client, 'you' for the web app's queue, or null."

### New code: frontend

`frontend/lib/types.ts`
```ts
// Job (after proposal_id, :61)
  /** Who filed the newest proposal: "you", an MCP client's name, or null. */
  proposal_proposed_by?: string | null;
// Proposal (after reason, :1840)
  /** "you" (the web app's queue), an MCP client's clientInfo.name, or null. */
  proposed_by?: string | null;
```
Both optional, so an older backend (a Docker image predating the field) reads as unknown.

`frontend/lib/api.ts:193-207` (inside `promoteJobToAgentQueue`'s POST body)
```ts
    body: JSON.stringify({
      job_id: jobId,
      proposed_by: "you",
      fit: …,
      plan: { summary: "Promoted from the tracker by the user" },
    }),
```
The plan summary stays: it is what the migrations' backfill keys on, and a record agents already read.

`frontend/lib/agent-name.ts` (new; no imports)
```ts
/**
 * Who filed a proposal, in words. `proposed_by` is stored raw: "you" for the
 * web app's Queue in Agent inbox, an MCP client's self-declared
 * clientInfo.name ("claude-ai", "codex-mcp-client") for a connected agent,
 * null when unknown. Pure (lib/agent-name.test.ts); pinned by
 * test_frontend_agent_inbox.py. Also names a KB point's writer.
 */
const KNOWN: ReadonlyArray<readonly [RegExp, string]> = [
  [/claude/i, "Claude"],
  [/codex/i, "Codex"],
  [/chatgpt|openai/i, "ChatGPT"],
  [/cursor/i, "Cursor"],
  [/windsurf/i, "Windsurf"],
  [/gemini/i, "Gemini"],
];
const ACRONYMS = new Set(["ai", "api", "cli", "ide", "mcp"]);

/** "Claude" for "claude-ai"; an unknown name title-cased ("my-agent" →
 *  "My Agent"), never shown as a slug; null for "you" or nothing. */
export function agentDisplayName(raw: string | null | undefined): string | null {
  const name = (raw ?? "").trim();
  if (!name || name.toLowerCase() === "you") return null;
  for (const [pattern, label] of KNOWN) {
    if (pattern.test(name)) return label;
  }
  return name
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((w) => (ACRONYMS.has(w.toLowerCase()) ? w.toUpperCase() : w[0].toUpperCase() + w.slice(1)))
    .join(" ");
}

/** "Proposed by Claude", "Queued by you" (a web promotion is queued at once),
 *  or "Proposed by a connected agent" when the filer is unknown. */
export function proposalByLine(proposedBy: string | null | undefined): string {
  if (proposedBy === "you") return "Queued by you";
  return `Proposed by ${agentDisplayName(proposedBy) ?? "a connected agent"}`;
}

/** The tracker's mark on an agent-captured row: the newest proposal's filer
 *  when an agent filed one, else the capture itself. */
export function agentMarkLabel(proposedBy: string | null | undefined): string {
  const name = agentDisplayName(proposedBy);
  return name ? `Proposed by ${name}` : "Found by a connected agent";
}
```

`frontend/lib/agent-name.test.ts` (new)
```ts
import assert from "node:assert/strict";
import { test } from "node:test";

import { agentDisplayName, agentMarkLabel, proposalByLine } from "./agent-name.ts";

test("known clients read as their product", () => {
  assert.equal(agentDisplayName("claude-ai"), "Claude");
  assert.equal(agentDisplayName("Claude Desktop"), "Claude");
  assert.equal(agentDisplayName("codex-mcp-client"), "Codex");
  assert.equal(agentDisplayName("ChatGPT"), "ChatGPT");
});

test("an unknown client is title-cased, never a slug", () => {
  assert.equal(agentDisplayName("my-agent"), "My Agent");
  assert.equal(agentDisplayName("mcp_inspector"), "MCP Inspector");
});

test("you and nothing are not agent names", () => {
  for (const raw of ["you", "You", "", "  ", null, undefined]) assert.equal(agentDisplayName(raw), null);
});

test("the by-line", () => {
  assert.equal(proposalByLine("claude-ai"), "Proposed by Claude");
  assert.equal(proposalByLine("you"), "Queued by you");
  assert.equal(proposalByLine(null), "Proposed by a connected agent");
});

test("the tracker mark falls back to the capture", () => {
  assert.equal(agentMarkLabel("codex-mcp-client"), "Proposed by Codex");
  assert.equal(agentMarkLabel("you"), "Found by a connected agent");
  assert.equal(agentMarkLabel(null), "Found by a connected agent");
});
```

`components/proposals/proposals-section.tsx`, `ProposalRow` (`:776-780`, after the company line)
```tsx
              <div className="text-muted-foreground truncate text-xs">
                {[job.company, job.location, job.work_mode]
                  .filter(Boolean)
                  .join(" · ")}
              </div>
              <div className="text-muted-foreground truncate text-xs">
                {proposalByLine(proposal.proposed_by)} · {formatTimeAgo(proposal.created_at)}
              </div>
```

`components/proposals/proposal-agent-panel.tsx`
```tsx
import { proposalByLine } from "@/lib/agent-name";
…
          <CardTitle>Agent inbox</CardTitle>            {/* :39 and :58, before data */}
…
            title="Couldn't load this proposal."          {/* :44 */}
…
      <CardHeader className="pb-2">
        <CardTitle>{proposalByLine(data.proposed_by)}</CardTitle>   {/* :76 */}
      </CardHeader>
      <CardContent className="flex flex-col gap-5 text-sm">
        <dl className="flex flex-wrap gap-x-6 gap-y-3">
          <Fact label="Date">
            {formatAbsoluteDateTime(data.created_at)}
          </Fact>
```

`app/jobs/[id]/page.tsx:342-348`
```tsx
            {isProposalStatus(proposalStatus) ? (
              <Badge
                className={cn("shrink-0", STATUS_BADGE_CLASS[proposalStatus])}
                variant="secondary"
                title={proposalByLine(job.proposal_proposed_by)}
              >
                {/* The status is the pill's text (the ONE status vocabulary);
                    who filed it is heard first and shown on hover. The
                    Overview card shows it visibly. */}
                <span className="sr-only">
                  {proposalByLine(job.proposal_proposed_by)}, status{" "}
                </span>
                {STATUS_LABELS[proposalStatus]}
              </Badge>
```

`app/applications/page.tsx:586-595` (shared file; with `import { agentMarkLabel } from "@/lib/agent-name";`)
```tsx
                          <p className="flex min-w-0 items-center gap-1.5 text-sm font-medium">
                            <span className="truncate">{company}</span>
                            {(r.kind === "saved" ? r.job.source : r.app.source) ===
                            "agent" ? (
                              <span className="inline-flex shrink-0" title={mark}>
                                <Bot className="text-muted-foreground size-3.5" aria-hidden="true" />
                                <span className="sr-only">{mark}</span>
                              </span>
                            ) : null}
                          </p>
```
with, next to `company`/`title` in the row body (`:557-558`):
```tsx
                const mark = agentMarkLabel(
                  r.kind === "saved" ? r.job.proposal_proposed_by : null,
                );
```
(An SVG with only `aria-label` and no role is announced inconsistently; the sr-only text is announced
everywhere and becomes part of the row link's name, as the old label did.)

### Tests to add (backend)

`backend/tests/test_proposals_proposed_by.py` (new)
```python
"""Who filed a proposal (appendix A9): the MCP client's name from the origin
headers, "you" for the web app's own queue, NULL when unknown. Additive on
every read, backfilled for the web app's past promotions."""

import sqlite3
import uuid
from contextlib import closing
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.main import app
from tests.test_proposals_models import _mk_job

client = TestClient(app)
_MCP = {"X-Maestro-CS-Origin": "mcp"}
BACKEND_DIR = Path(__file__).resolve().parents[1]


def _file(job, headers=None, **body):
    return client.post("/api/proposals", json={"job_id": str(job.id), **body}, headers=headers or {})


def test_an_mcp_proposal_records_the_clients_name(db_session):
    job = _mk_job(db_session, company="Acme", source="agent")
    r = _file(job, {**_MCP, "X-Maestro-CS-Origin-Detail": "claude-ai"})
    assert r.status_code == 201
    pid = r.json()["id"]
    assert r.json()["proposed_by"] == "claude-ai"
    assert client.get(f"/api/proposals/{pid}").json()["proposed_by"] == "claude-ai"
    listed = {i["id"]: i for i in client.get("/api/proposals").json()["items"]}
    assert listed[pid]["proposed_by"] == "claude-ai"


def test_an_unnamed_mcp_client_is_unknown_and_cannot_claim_you(db_session):
    job = _mk_job(db_session, company="Beta", source="agent")
    r = _file(job, _MCP, proposed_by="you")
    assert r.status_code == 201
    assert r.json()["proposed_by"] is None


def test_the_web_apps_queue_says_you(db_session):
    job = _mk_job(db_session, company="Gamma")
    r = _file(job, proposed_by="you")
    assert r.json()["proposed_by"] == "you"


def test_a_body_can_only_say_you(db_session):
    job = _mk_job(db_session, company="Delta")
    assert _file(job, proposed_by="Claude").status_code == 422


def test_a_repeat_filing_keeps_the_first_filer(db_session):
    job = _mk_job(db_session, company="Epsilon", source="agent")
    first = _file(job, {**_MCP, "X-Maestro-CS-Origin-Detail": "codex-mcp-client"})
    again = _file(job, {**_MCP, "X-Maestro-CS-Origin-Detail": "claude-ai"})
    assert again.status_code == 200
    assert again.json()["proposed_by"] == first.json()["proposed_by"] == "codex-mcp-client"


def test_job_reads_carry_the_newest_proposals_filer(db_session):
    job = _mk_job(db_session, company="Zeta", source="agent")
    _file(job, {**_MCP, "X-Maestro-CS-Origin-Detail": "claude-ai"})
    listed = {j["id"]: j for j in client.get("/api/jobs?without_application=true&limit=500").json()}
    assert listed[str(job.id)]["proposal_proposed_by"] == "claude-ai"
    detail = client.get(f"/api/jobs/{job.id}/detail").json()
    assert detail["job"]["proposal_proposed_by"] == "claude-ai"


def test_the_migration_backfills_the_web_apps_own_promotions(tmp_path):
    path = tmp_path / "m.sqlite3"
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    command.upgrade(cfg, "871d0425b64c")
    job, promoted, hunted = (uuid.uuid4().hex for _ in range(3))
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("INSERT INTO jobs (id, raw_text, raw_text_hash) VALUES (?, 'JD', 'h')", (job,))
        conn.executemany(
            "INSERT INTO application_proposals (id, job_id, plan_json) VALUES (?, ?, ?)",
            [
                (promoted, job, '{"summary": "Promoted from the tracker by the user"}'),
                (hunted, job, '{"summary": "Strong fit"}'),
            ],
        )
        conn.commit()
    command.upgrade(cfg, "head")
    with closing(sqlite3.connect(path)) as conn:
        rows = dict(conn.execute("SELECT id, proposed_by FROM application_proposals"))
    assert rows == {promoted: "you", hunted: None}
```
`test_migration_model_parity.py` then proves the model and the SQLite chain agree, with no edit.
`test_export_from_real_postgres` (CI's legacy-postgres job) proves the legacy revision lets the import
copy the column.

`backend/mcp_server/tests/test_client_proposals.py` (new)
```python
"""propose_application: request shape and who-filed-it provenance."""

import json

import httpx
import respx

from mcp_server.client import BackendClient

BASE = "http://test-backend"


@respx.mock
def test_propose_application_names_the_client_in_the_origin_headers():
    route = respx.post(f"{BASE}/api/proposals").mock(
        return_value=httpx.Response(201, json={"id": "p1"})
    )
    BackendClient(BASE).propose_application("j1", plan={"summary": "fit"}, origin_detail="claude-ai")
    request = route.calls.last.request
    assert json.loads(request.read()) == {"job_id": "j1", "plan": {"summary": "fit"}}
    assert request.headers["X-Maestro-CS-Origin"] == "mcp"
    assert request.headers["X-Maestro-CS-Origin-Detail"] == "claude-ai"


@respx.mock
def test_an_unnamed_client_still_files_as_mcp_never_as_you():
    route = respx.post(f"{BASE}/api/proposals").mock(
        return_value=httpx.Response(201, json={"id": "p1"})
    )
    BackendClient(BASE).propose_application("j1")
    request = route.calls.last.request
    assert request.headers["X-Maestro-CS-Origin"] == "mcp"
    assert "X-Maestro-CS-Origin-Detail" not in request.headers
    assert "proposed_by" not in json.loads(request.read())
```

`backend/mcp_server/tests/test_proposal_tools.py` (add)
```python
def test_propose_application_passes_the_client_label(monkeypatch):
    seen = {}
    monkeypatch.setenv("MAESTRO_CS_MCP_CLIENT", "codex-mcp-client")
    monkeypatch.setattr(
        srv._client, "propose_application", lambda job_id, **kw: seen.update(kw) or {"id": "p1"}
    )
    srv.propose_application("j1")
    assert seen["origin_detail"] == "codex-mcp-client"


async def test_propose_application_keeps_ctx_out_of_its_schema():
    tools = {tool.name: tool for tool in await srv.mcp.list_tools()}
    assert "ctx" not in tools["propose_application"].inputSchema["properties"]
```
(The module's other async tests show the collection setup; if it has none, put the async test in
`test_server.py` next to `test_resolve_gaps_contract_lists_every_backend_action`.)

### Pins to add (frontend; `test_frontend_agent_inbox.py`)

```python
def test_every_proposal_surface_names_who_filed_it():
    assert "{proposalByLine(proposal.proposed_by)} · {formatTimeAgo(proposal.created_at)}" in _SECTION
    assert "<CardTitle>{proposalByLine(data.proposed_by)}</CardTitle>" in _PANEL
    assert "title={proposalByLine(job.proposal_proposed_by)}" in _JOB
    tracker = _read("app/applications/page.tsx")
    assert "agentMarkLabel(" in tracker
    assert "Found by agent" not in tracker


def test_the_filer_words_live_in_one_mapper():
    lib = _read("lib/agent-name.ts")
    assert not re.search(r"^import ", lib, re.M)
    assert 'if (proposedBy === "you") return "Queued by you";' in lib
    assert '`Proposed by ${agentDisplayName(proposedBy) ?? "a connected agent"}`' in lib
    assert 'return name ? `Proposed by ${name}` : "Found by a connected agent";' in lib


def test_the_web_queue_files_as_you():
    api = _read("lib/api.ts")
    promote = api[api.index("export async function promoteJobToAgentQueue") :]
    promote = promote[: promote.index("\n}\n")]
    assert 'proposed_by: "you",' in promote
    # The backfill keys on this summary; changing it orphans the migration.
    assert 'plan: { summary: "Promoted from the tracker by the user" },' in promote
```

### Existing tests that change

- `backend/mcp_server/tests/test_proposal_tools.py:23-33`
  `test_propose_application_tool_calls_client`: its stub lambda has no `origin_detail` parameter and
  would raise `TypeError`. New stub:
  ```python
        lambda job_id, base_resume=None, fit=None, plan=None, application_id=None, referral_id=None,
               origin_detail=None: seen.update(
            j=job_id, f=fit, p=plan, a=application_id, r=referral_id, o=origin_detail
        ) or {"id": "p1"},
  ```
  and `assert seen == {…, "r": None, "o": None}` (no env label set in that test; if the suite's
  environment sets `MAESTRO_CS_MCP_CLIENT`, `monkeypatch.delenv` it first).
- No other test asserts the exact key set of a proposal or job response (searched
  `test_proposals_router.py`, `test_jobs_router.py`, `test_proposal*.py`).

### Browser checks

1. **Seeded as Claude** (the A1 curl): the inbox row reads "Proposed by Claude · just now". Open it: the
   Overview card's title is "Proposed by Claude"; its first fact is "Date". Hover the header pill: the
   tooltip reads "Proposed by Claude"; `read_page` names it "Proposed by Claude, status Proposed".
2. **Queued by you.** On a saved user job, click "Queue in Agent inbox": toast "Queued in your Agent
   inbox"; the inbox's Queued lane shows it with "Queued by you · just now"; its job page card title reads
   "Queued by you".
3. **Unnamed client.** curl with `X-Maestro-CS-Origin: mcp` and no detail: "Proposed by a connected agent".
4. **Tracker.** `/applications?source=agent`: hover the robot on the Acme row: "Proposed by Claude"; on an
   agent capture with no proposal: "Found by a connected agent". `read_page`: the row link's name contains
   the same words.
5. **Real client.** With the MCP server connected to Claude Desktop (a scratch stack, never the live one),
   ask it to propose a saved job: the row names "Claude". Repeat from Codex: "Codex".
6. **Dark, 768, 375**: the by-line truncates with an ellipsis inside the row, never pushing the status
   badge off the row.

### Risks

- **The legacy revision edits a boxed chain.** Without it the first-boot import fails closed for every
  user still on Postgres. The alternative (teach `copy_database` to fill model-only nullable columns with
  NULL) loses the "you" backfill for imported rows. Open question 6.
- **This is the SQLite chain's first revision.** SYSTEM.md §2 says "ONE SQLite baseline"; A10 queues the
  wording.
- **`clientInfo.name` is self-declared.** It is a label, not an identity (`_client_label`'s docstring says
  so). Nothing security-bearing reads `proposed_by`.
- **ChatGPT desktop and Codex may declare the same name** (they install the same plugin). Then a ChatGPT
  filing reads "Codex". Open question 8 has the check.

---

## A10. Docs

`docs/frontend-conventions.md` (in the same commits as the code):
- `:53` "the proposals filter" → "the Agent inbox's history filter".
- `:776` "Agent Proposals when `?from=proposals`" → "Agent inbox when `?from=proposals`".
- `:795` group list → "**Job search** (Applications, Agent inbox, Referrals)"; add to the sidebar bullet:
  "The Agent inbox item carries a Needs-you count: `needsYouBadge` (`lib/needs-you.ts`) hides it at 0 or
  unknown, the pill is `aria-hidden` and an sr-only ', N need you' completes the link's name; its orange is
  measured on all four row states (`test_the_needs_you_badge_meets_aa_on_every_sidebar_row_state`)."
- `:800-806` "Tracker filter": "Agent lane" → "Agent inbox".
- `:808` Naming: add "**One word per kind of agent**: Assistant (the in-app chat), connected agents (MCP
  clients; Connected agents in Settings), Companion (the extension), Suggested edits (chat's and the
  studio's approval cards). 'Proposal' means only a job an agent filed. Bare 'Agent' only inside Agent inbox
  and Agent pipeline. A filer is named through `lib/agent-name.ts`, never printed raw."
- `:889` Settings vs Profile: "agent hints" → "connected agents (Auto-apply, next-step hints)".
- New bullet after the tracker filter: "**A list cut at `LIST_CAP` says so at its end**
  (`lib/list-cap.ts`, `ListCapNotice`): with a server `total`, cut means total > loaded; without one, a
  full page. One search box for list pages: `ListSearch`."

`docs/entities/others.md:382-464` (ApplicationProposal): add "`proposed_by` (migration `3ac279fcc4b9`;
legacy mirror `08b05599ef28`): `'you'` from the web app's queue (body field, accepted only as `'you'`), the
MCP client's `clientInfo.name` from the `X-Maestro-CS-Origin-Detail` header (which wins; an agent cannot
file as you), else NULL; job list/detail expose the newest proposal's as `proposal_proposed_by`." and
"`/proposals` triage inbox" → "`/proposals` (the Agent inbox)"; "Agent proposal Overview block" → "the
proposal's Overview card, titled with its filer".

**Queued for the docs sweep (SYSTEM.md is at its cap):**
- §2 `:93` "ONE SQLite baseline" → "the SQLite chain (baseline `871d0425b64c` plus revisions)".
- §5 step 2 `:150-155`: "(hunt inventory lives on `/proposals`)" → "(agent inventory lives in the Agent
  inbox, `/proposals`)"; "**Agent lane**" → "**Agent inbox**".
- §5 step 3 `:157,161`: "proposal pill" → "proposal pill (filer in its name)"; "Agent proposal block" →
  "the proposal card, titled with its filer (`proposed_by`)".
- §7, the proposal-ledger clause: add "`propose_application` stamps `proposed_by` from the client's
  `clientInfo.name` (the KB writes' origin headers)".

**User docs** (not code; T-A4 or the docs sweep):
- `README.md:568` "**Agent Proposals** page" → "**Agent inbox**"; `docs/GETTING_STARTED.md:297` "You
  decide on **Agent Proposals**" → "You decide in the **Agent inbox**".
- The `TODO(P4) proposals.png` comment at `README.md:556-562` describes the removed counters; update it
  when the screenshot is taken.

---

## Found by reading (not asked for; each is small)

1. **The Role filter printed raw keys** (`proposals-section.tsx:439,446`). Fixed in A3.
2. **Selection survives a filter change**: rows selected in Triage stay in `selected` when a filter hides
   them, and the BulkBar's Accept/Skip acts on rows the user can no longer see. Suggest pruning `selected`
   to `filtered` ids in the handlers that change filters (not an effect). Not designed here.
3. **"Expires" shows on queued proposals** (`proposal-agent-panel.tsx:84-86`), though "Accepted proposals
   never expire" (`auto-apply-section.tsx:49`). Show it only for `pending_review`/`needs_decision`.
4. **The two Queue buttons are not single-flight** (`app/applications/page.tsx:641`,
   `app/jobs/[id]/page.tsx:397`). A double click files once (the POST is idempotent) and then PATCHes
   `accepted` twice; the second 409s into an error toast. `useSingleFlight(promote.mutate)` fixes it.
5. **The KB timeline says "— added by mcp"** (`backend/app/services/career_kb.py:437`): a raw origin and an
   em dash, composed server-side and also returned over MCP (`get_kb_entity`). A display fix belongs with
   the backend owner (use the client label, drop the dash).
6. **Bulk-triage error toast used an em dash** (`triage-actions.tsx:105`). Fixed in A5's code block.

---

## File ownership

**New files (this appendix):**
- `frontend/lib/list-cap.ts`, `frontend/lib/list-cap.test.ts` (T-A2)
- `frontend/lib/inbox-filter.ts`, `frontend/lib/inbox-filter.test.ts` (T-A2)
- `frontend/lib/needs-you.ts`, `frontend/lib/needs-you.test.ts` (T-A2 creates it for the lane constant; T-A3
  may add the badge function if split)
- `frontend/lib/agent-name.ts`, `frontend/lib/agent-name.test.ts` (T-A2)
- `frontend/lib/agent-links.ts` (T-A2)
- `frontend/hooks/use-needs-you-count.ts` (T-A3)
- `frontend/hooks/use-proposal-funnel.ts` (T-A2)
- `frontend/components/list-search.tsx`, `frontend/components/list-cap-notice.tsx` (T-A2)
- `frontend/components/proposals/cap-today.tsx` (T-A2)
- `frontend/components/settings/connected-agents-card.tsx` (T-A4)
- `backend/migrations/versions/3ac279fcc4b9_application_proposals_proposed_by.py` (T-A1)
- `backend/legacy_postgres/migrations/versions/08b05599ef28_application_proposals_proposed_by.py` (T-A1)
- `backend/tests/test_proposals_proposed_by.py` (T-A1)
- `backend/mcp_server/tests/test_client_proposals.py` (T-A1)
- `backend/tests/test_frontend_agent_inbox.py` (T-A2; T-A3 appends the A4 tests)
- `backend/tests/test_frontend_agent_words.py` (T-A4)

**Deleted:** `frontend/components/proposals/funnel-strip.tsx` (T-A2).

**Modified, owned here:**
- T-A1: `backend/app/models/application_proposal.py`, `backend/app/schemas/proposal.py`,
  `backend/app/schemas/job.py`, `backend/app/routers/proposals.py`, `backend/app/routers/jobs.py`,
  `backend/app/services/proposals.py`, `backend/mcp_server/server.py` (propose only),
  `backend/mcp_server/client.py` (propose only), `backend/mcp_server/tests/test_proposal_tools.py`,
  `docs/entities/others.md`.
- T-A2: `frontend/app/proposals/page.tsx`, `frontend/components/proposals/proposals-section.tsx`,
  `frontend/components/proposals/proposal-agent-panel.tsx`, `frontend/components/proposals/triage-actions.tsx`
  (toast), `frontend/components/analytics/agent-pipeline-card.tsx` (hook swap; T-A4 changes its two
  strings, so T-A2 takes those rows too if they run in parallel), `frontend/lib/types.ts` (three optional
  fields), `frontend/lib/api.ts` (one body field), `backend/tests/test_frontend_query_error_states.py`,
  `backend/tests/test_frontend_placeholders.py`.
- T-A3: `frontend/components/app-sidebar.tsx`, `backend/tests/test_frontend_color_roles.py` (one
  `_TAILWIND` row, one test).
- T-A4: `frontend/components/source-toggle.tsx`, `frontend/components/career/points-list.tsx`,
  `frontend/components/settings/llm-endpoint.tsx`, `frontend/components/settings/mcp-workflow-section.tsx`,
  `frontend/components/settings/auto-apply-section.tsx`, `frontend/components/settings/quick-tailor-section.tsx`,
  `frontend/components/settings/autofill-section.tsx`, `frontend/components/analytics/autofill-coverage-card.tsx`,
  `frontend/components/ats-score-panel.tsx`, `frontend/components/chat/proposal-card.tsx`,
  `frontend/components/chat/edit-proposal-card.tsx`, `frontend/components/resume-editor/instruct-sheet.tsx`,
  `backend/tests/test_frontend_dialog_drafts.py`, `README.md`, `docs/GETTING_STARTED.md`.

**Shared with other appendices (coordinate):**
- `frontend/app/applications/page.tsx` (**Applications appendix owns it**): A5 rows 15, 16, 18 and A9's
  tracker mark are four local edits plus one import. Hand them to the Applications lane, or land them after
  it. Its cap notice uses A7's `listCap`/`ListCapNotice`, and it may adopt `ListSearch` (then delete the
  `app/applications/page.tsx` row from `_PROMPTS`).
- `frontend/app/jobs/[id]/page.tsx`: A1 labels, A5 rows 7–9, A9 pill. String-level; any appendix that
  restructures the job header (a contacts card on Overview, say) must merge around them.
- `frontend/app/settings/page.tsx` (**Settings-tabs appendix owns it**): mounts A8's card and the two moved
  cards in the agents tab, and takes A5 row 22's subtitle.
- `docs/frontend-conventions.md`: every lane edits its own bullet (A10 names them).
- `backend/tests/test_frontend_color_roles.py`: append-only here.

---

## Open questions for the planner

1. **Keep `/proposals`?** Recommended (A1). A rename to `/inbox` needs a redirect stub and two docstring
   edits for no visible gain.
2. **Collapsed sidebar:** the count disappears with the sidebar. Add a small dot to the reveal pill when
   something needs you? Recommended: not this round.
3. **SourceToggle's third segment:** "Agents" (proposed) or "Connected"? It is shared with Analytics.
4. **Rename the Chat nav item to "Assistant"?** Not asked; A5 uses "Assistant" only in Settings and KB
   chips.
5. **Score filter:** presets 50/60/70/80 (proposed) or keep a free number (which brings back a label or
   an example placeholder in the toolbar)?
6. **Legacy Postgres revision** (A9) vs teaching the importer to NULL-fill model-only columns. The
   revision is recommended: it keeps the importer strict and carries the "you" backfill.
7. **Job header pill:** status text plus an sr-only and hover by-line (proposed, keeps the one status
   vocabulary), or a visible "Proposed by Claude" in the header?
8. **Real client names:** before merge, read the names actually seen on this machine from a `backups/`
   snapshot (never the live file):
   `SELECT DISTINCT origin_detail FROM kb_points WHERE origin = 'mcp';`. If ChatGPT desktop reports the
   same name as Codex, the mapper cannot tell them apart; say "Codex or ChatGPT", or accept it.
9. **"Cap today"** is a rolling 24 hours. Keep the owner's words (proposed; the spoken text says "last 24
   hours") or show "Daily cap 2/10"?
10. **Poll interval** for the count: 60 s proposed.
11. **KB timeline "added by mcp"** (found-by-reading 5): fix in this plan's backend lane or leave?
12. **`ListSearch` in Applications:** which lane swaps Applications' block (and its `_PROMPTS` row)?
13. **"hunt"** stays as the name of a connected agent's search run (the owner's own "Start a hunt"); confirm
    that "Proposals per hunt" and "A connected agent never saves or proposes these companies" read right.
