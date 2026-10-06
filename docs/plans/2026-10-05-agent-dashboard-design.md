# Agent dashboard: readiness, run log, arrivals

Approved by the owner on 2026-10-05 (brainstorming session, approach 1). This is phase 3 of
four; phases 1 (`2026-10-04-automations-page-design.md`) and 2
(`docs/entities/filled-answers.md`) are merged.

## Goal

Make the Agent inbox (`/proposals`) the place to see what the user's own agent runs did and
what is ready to send, without opening each job.

**Scope rule from the owner: dashboard only.** This phase reads; it does not change
tailoring, filling, the knock-out rules, submit rules or the proposal state machine. The only
writes outside the page are a new run record and one closing line in each automation prompt.

## What exists (and stays)

The inbox already has the lanes Needs you, To review, Queued, Applying, History
(`frontend/lib/inbox-lanes.ts`) and the sidebar "N need you" badge. Lane titles do not change,
so the pins in `backend/tests/test_frontend_agent_inbox.py` keep holding.

## Owner decisions

- **Add:** readiness on each row, a run log, an arrivals summary. **Not now:** reply updates
  from mail-status.
- **Readiness marks rows only.** No lane split, no move into Needs you; the badge count is
  unchanged.
- **Run log shows** as a "Recent runs" inbox panel plus a "Last ran" line on each Automations
  card.
- **Approach 1.** Readiness is computed when the list is read. Rejected: (2) a second
  readiness request (two loading states, rows redraw); (3) readiness stored on the proposal
  (stale after profile edits, and needs hooks in tailoring code).

## Part 1: Readiness marks

**Backend.** New `backend/app/services/inbox_readiness.py`:
`for_proposals(session, proposals) -> dict[UUID, Readiness | None]`.

- Computed only for open-lane statuses: `pending_review`, `needs_decision`, `needs_human`,
  `accepted`, `approved`. History rows get `null`.
- `tailored: bool | None` — the linked application has a `pdf_path`; `null` when no
  application is linked.
- `knockout: str | None` — when `knockout.scan_job` returns `status == "conflict"`, the `kind`
  of the first conflicting check (`work_authorization`, `opt`, `salary`, `experience`,
  `on_site`); otherwise `null`. The profile, work auth, preferences and years of experience are
  read once for the whole batch, not per row (`scan_for` reads them per call, so the batch
  calls `scan_job` directly).
- `to_check: int` — the receipt's flag count, computed only for jobs where
  `filled_answers.has_any` is true; `0` otherwise.
- A row whose computation raises gets `null` and a logged warning; the list still returns.

`GET /api/proposals` adds `readiness` to each item (`ProposalRead` gains an optional field).

**Frontend.** In `proposals-section.tsx` rows, small badges on the meta line in existing
tones: **Tailored** / **Not tailored** (muted), **Knock-out: on-site** (warning; word per
kind), **3 to check** (warning). In the Queued lane, ready rows (tailored, no knock-out,
`to_check == 0`) sort first; the user's chosen sort applies within each group. The readiness
helpers (`isReady`, mark words) live in a pure `frontend/lib/inbox-readiness.ts`.

## Part 2: Run log

**Model.** New table `agent_runs`:

| Field | Notes |
|---|---|
| `id` | UUID |
| `automation` | card id (`mail-status`, `job-hunt`, `referral-pages`, `tailor-run`, `apply-session`) or a custom name, ≤ 40 chars |
| `agent` | client name, resolved the same way as `proposed_by` |
| `started_at`, `finished_at` | `finished_at` defaults to now |
| `outcome` | `ok` / `partial` / `failed` |
| `counts` | JSON object of non-negative ints; known keys `found`, `proposed`, `skipped`, `tailored`, `updated`, `needs_you`; unknown keys rejected |
| `digest` | plain text, ≤ 2000 chars |
| `job_ids` | JSON list, ≤ 50, unknown ids dropped |
| `created_at` | |

Retention: only the newest 200 rows are kept, pruned on write.

**MCP.** New tool `record_run` (write-only; no edit or delete tool, per
`{#inv-mcp-controls}`). Registered in `mcp_server/tests/test_server.py`; tool count 84 → 85.

**Prompts.** Each automation SKILL.md (`mail-status`, `job-hunt`, `referral-pages`,
`tailor-run`, `apply-session`) gets a closing step: call `record_run` with the counts and the
digest. `customize-job-skills` tells custom automations to do the same under their own name.
`job-hunt` now passes `source="agent"` to `store_extracted_jd` (it defaulted to `"user"`, so
its jobs were saved as the user's).

**Privacy.** The mail-status prompt says the digest holds counts and company/role lines only,
never email text. Maestro cannot verify that; `docs/entities/agent-runs.md` says so, the same
way phase 2 treats agent-reported answer sources.

**Reading.** `GET /api/agent-runs?limit=` (newest first) and `GET /api/agent-runs/latest`
(one per automation).

**Inbox panel "Recent runs".** One line per automation: title (card title, or the custom
name), relative time, outcome, counts ("Found 12 · proposed 4 · skipped 8"). Expanding shows
the digest and links to the jobs. Empty state: "No runs yet. Set one up on Automations."

**Automations cards.** A muted line: "Last ran 2h ago" or "Not run yet".

**No overdue warning.** Maestro does not know the user's schedule. A run that crashes before
recording leaves the old time, which is the honest signal.

## Part 3: Arrivals summary and the History fix

**Arrivals strip**, above the lanes and the Recent runs panel; four tiles:

- **New since your last visit** — proposals created after the last visit. The visit time is
  kept in `localStorage` (try/catch); without it the tile counts the last 24 hours. New rows
  get a small "New" dot.
- **Ready to apply** — Queued rows that are ready (Part 1 rule).
- **Needs you** — same count as the sidebar badge.
- **Submitted this week** — proposals moved to `submitted` plus proposals closed with reason
  `"applied manually"`, in the last 7 days.

Clicking a tile scrolls to its lane. Counts come from one new endpoint,
`GET /api/proposals/summary?since=`. `/funnel` is unchanged.

**History fix.** A proposal closed because the user applied themselves
(`status == "rejected"`, `reason == "applied manually"`, set in
`routers/applications.py`) shows **Applied yourself** in History instead of "Skipped".
UI label only; the state machine and `STATUS_CHIP_WORDS` are unchanged.

## Testing

- **Backend:** readiness per mark, a raising row → `null`, History → `null`, profile read
  once per batch; `record_run` validation (automation length, counts keys, digest cap,
  job_ids cap and unknown-id drop), pruning at 200, latest-per-automation; MCP registration;
  summary counts including manual applies; prompt guardrails (every automation prompt ends
  with `record_run`, job-hunt passes `source="agent"`, mail-status digest forbids email text).
- **Frontend:** pure tests for `inbox-readiness.ts` and the summary helpers; source-reading
  tests for the strip, the Recent runs panel, the marks, the card line and the "Applied
  yourself" label. Existing lane pins unchanged.
- Lint, typecheck, build; live check on a fresh stack on spare ports.

## Docs

- New `docs/entities/agent-runs.md` (fields, limits: unverified digest, no overdue).
- `docs/entities/others.md` proposals section: readiness, summary, the History label.
- SYSTEM.md §5 (inbox), §7 (`record_run`, tool counts 84 → 85). SYSTEM.md sits at 995/1000,
  so grooming must keep every rule-bearing clause.
- CHANGELOG.

## Out of scope

Tailoring, filling and submit rules; any scheduler or overdue logic; reply updates from
mail-status; phase 4 (auto-submit, local password).
