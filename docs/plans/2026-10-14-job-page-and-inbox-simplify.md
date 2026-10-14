# Job page and Agent inbox simplification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** The first thing on each page answers "what do I need to do, and where does this stand?". Anything that only records history moves down, collapses, moves to its own page, or shows only when it matters. Approved by the owner 2026-10-14.

**Architecture:** Frontend only where possible (`frontend/app/jobs/[id]/page.tsx`, `components/proposals/*`, `components/job-knockout-card.tsx`, `frontend/app/proposals/page.tsx`, the Automations page). Follow `docs/design-system` and the existing component idioms. Desktop-only (1024px+). Test-first with the existing frontend test setup; `npx tsc --noEmit` clean.

---

## A. Job page (Overview)

### A1: one status in the header; fix "Skipped" for an applied job
- When an application exists, the header shows only the status menu; the proposal pill is not shown.
- With no application, the proposal pill uses the same labels as the inbox History lane (`historyLabel`): a rejection with reason "applied manually" reads "Applied yourself", never "Skipped".
- Tests: applied job → no pill, one status; proposal rejected "applied manually" without application → "Applied yourself".

### A2: a clear score
- The score pill reads "Resume match N (tailored)" from the application's tailored score when there is one, else "Best base resume N" from the base scores. Hidden when neither exists.
- Tests: tailored present → tailored label and value; only base → base label.

### A3: "Where this stands" line under the header
- Applied (status in the submitted stages): "Applied <date> with <base resume name> resume" plus links: View PDF (when ready), What was submitted (when there are filled answers).
- Draft application, not applied: "Not applied · best resume <name> <score>" with a short pointer to Tailor / Apply in the Companion (and the existing Score and tailor tab).
- No application: "Not applied yet" plus the best base resume when scored.
- Use data already on `GET /api/jobs/{id}/detail`; add only missing fields (e.g. applied_at, base resume name) to the backend detail response if they are not there, with a backend test.

### A4: knock-outs only when they block
- The knock-out card renders as a banner only on a conflict or a missing profile answer (as today).
- "No knock-outs" / "No requirements listed" / "Checks not run yet" become one small line inside the Job details card (tick + text), not a card.

### A5: the proposal card only when it carries something
- `ProposalAgentPanel` renders only when the proposal has content beyond the Companion's fixed filing: a needs-you question or reason, a company note, a non-default tailoring plan (not the Companion's fixed "Queued from the Companion by the user"), drafted answers, or screenshots. Never for `proposed_by: "you"` with only the fixed plan.
- "expires <date>" shows only while the proposal can still expire (pending_review, needs_decision).
- Tests for each condition.

## B. Agent inbox (`/proposals`)

### B1: one summary line instead of four tiles
- Replace the four stat tiles with one line: "<n> need you · <n> queued · <n> applied this week" (and "<n> new" when > 0). Each part links/scrolls to its lane; zero parts are omitted; all zero → "Nothing waiting".

### B2: lanes in order of urgency, empty lanes hidden
- Order: Needs you, To review, Queued, Applying, History (collapsed). A lane with 0 items is not rendered (To review included). The no-proposals empty state stays.

### B3: filters only for long lists
- Search and filters render only when the inbox holds more than 10 jobs (or a filter is active, so a user can always clear it).

### B4: daily limit only near it
- The cap meter renders only at 80% or more of the daily limit, or on error.

### B5: Recent runs move to Automations
- Remove `RecentRuns` from the inbox and render it on the Automations page (where runs come from), keeping its expand-to-digest and job links.
- The inbox shows a single line only when the newest run found something new (counts > 0): "<automation> found <n> new jobs <time ago> · See runs" linking to Automations.

## C. Docs and gate
- Update `docs/USING_MAESTRO.md` (job page and inbox sections), SYSTEM.md where these pages are described, CHANGELOG Unreleased (one entry), and any docs/ux notes that pin the old layout.
- Gate: frontend tests, `npx tsc --noEmit`, backend tests if the detail response changed.
