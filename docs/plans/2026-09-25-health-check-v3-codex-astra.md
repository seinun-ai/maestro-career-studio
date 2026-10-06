# Handoff: health check v3 — Codex (GPT-6 Astra)

**Plan:** `docs/plans/2026-09-24-health-check-frameworks.md` (revision 2). The plan is the spec. This file only covers
how to run the lane.

## Goal Card

The plan's Goal Card is binding, and is copied here:

- **Goal.** Every resume bullet earns its place with a number or with other concrete evidence (what the person did and
  what came of it). The health check judges each bullet on that, asks it only for the one thing it lacks, and never
  demands a number where one isn't natural.
- **The report.** The report is easy to read and quick to act on. Questions can be answered in one pass or card by
  card, and the user can tell the check in their own words why a flag is wrong.
- **Tailoring.** Tailoring follows the same guidance when it writes bullets.
- **Principles:**
  - judge the page, not the claim
  - rewrites never invent
  - the prompt judges; code validates and counts
  - code checks structure, not judgment
  - works beyond tech
  - desktop only

**Autonomy: peer (adapt-and-advise).**
- Adapt *how* when a step conflicts with repo reality, and log every deviation in the plan's *Deviation log* (one
  line, with a reason).
- **Every new or changed contract field, enum value, endpoint or DB column not named in the plan is a logged
  deviation.**
- Anything touching scope goes to the reviewer (Claude, over the walkie) as a short deviation note: planned / found /
  proposed / which Goal Card line. The same applies to the Goal Card itself and to the interfaces other tasks use
  (evaluation contract Task 5, finding fields Task 6, dispute API Task 7).
- Never expand scope.

## Where and how

- **Worktree:** `/Users/ajeyds/Projects/maestro-lanes/health-v3`
- **Branch:** `codex/health-v3` (from `main` `a150bf4f`). Work only here.
- **Never touch** the main checkout `/Users/ajeyds/Projects/maestro-career-studio`: its `data/` is the owner's live
  database, and its Docker stack on 3000/8001 is live.
- **Never merge, never push.** The reviewer merges after review.
- **Read first:** `SYSTEM.md` (it is the ground truth, and its header contract applies), then the plan's *Before you
  start*.
- **Python:** `/opt/anaconda3/bin/python3`, with pytest and ruff run from `backend/`. The suite is
  `pytest tests/ mcp_server/tests/ -q`.
- **Frontend:** run `npm ci` once in `frontend/`, from the lockfile, as-is. Then use `npm run lint` and
  `npx tsc --noEmit`.
- **No new dependencies** in Python or npm, and no lockfile, CI, Dockerfile or install-script changes. None is needed.
  If you believe one is, stop and ask.
- **Commits:** one per task, using the plan's message. Keep your red-then-green `test:` → `feat:` pattern. End every
  message with `Assisted-by: GPT-6 Astra (Codex CLI)`. Never commit `docs/ux/`, and never commit real resume text.
- **Usage limit:** commit as soon as a task is GREEN, BEFORE lint and verification, if your budget is low. A limit
  hit must leave a committed GREEN, not a dirty tree.

## Waves (stop at each checkpoint and report over the walkie)

| Wave | Tasks | Checkpoint |
|---|---|---|
| 1 | 1, 2, 3, 4, 5, 6 | Claude reviews. The owner signs off on the golden-set labels (Task 3), and Claude runs the golden gate with a real API key. |
| 2 | 7, 8, 9, 10 | Claude reviews |
| 3 | 11, 12, 13, 15 | Claude reviews + a browser pass. Task 14 (skills outside the repo) is done by Claude with the owner. |

- **Golden set (Task 3/5).**
  - Build the fixture (synthetic bullets only) and `scripts/health_golden.py`.
  - You need no API key: the golden RUN happens at the checkpoint.
  - Do prompt tuning on `dev` only, and only if a key is available to you. Otherwise freeze the prompt as written,
    log that as a deviation, and move on.
- **Owner questions:** ask them over the walkie, addressed to Claude, and keep working on tasks that don't depend on
  the answer.

## Report at each checkpoint

- Task list with commit SHAs.
- Gate results: suite counts before and after, ruff, lint, tsc, node tests.
- Deviation log entries, and anything left unverified, marked as unverified.
- Send it over the walkie to `claude`, or write `<share>/health-check/wave-N-report.md` and send the path.
