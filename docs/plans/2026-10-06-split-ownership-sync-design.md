# A second, always-on copy: split-ownership sync (phase 4b)

Approved by the owner on 2026-10-06 (brainstorming session). This replaces the deferred Part 4 of
`docs/plans/2026-10-05-full-automation-design.md`. It builds on phase 4 Parts 1–3 (full
automation mode), which come first.

## Goal

Let the user's own agent hunt and apply around the clock, even while the user's laptop is off,
from a second Maestro copy on an always-on machine, while the laptop stays the home of the
user's profile and keeps working fully offline.

**Opt-in and generic.** Nothing changes for anyone who doesn't set up a second copy (no sync key,
no remote address): every job is the machine's own, nothing is marked or locked, the sync
endpoints refuse every request, and `sync_now` answers "sync isn't set up". The whole existing
suite must pass unchanged with sync off. The second copy is any always-on machine that can make an
outgoing SSH connection to the laptop (a home server, a cloud VM, an agent app with its own
machine); its agent drives it through Maestro's MCP tools like any connected agent. Product names
appear only in the setup guide's worked example.

## Decisions and rejected options

- **Split ownership: one writer per piece of data,** so nothing ever merges.
- **Rejected:**
  - cr-sqlite / CRDT sync: Maestro has 7 unique constraints besides primary keys and 23 cascading
    foreign keys, and its state machine (skip vs submit, the daily cap, the consent ledger, resume
    version numbers) can't survive last-writer-wins.
  - Cloud-hub sync engines (SQLite Sync, Turso offline sync, PowerSync, Electric): a third-party
    or Postgres hub, the same schema limits, or a storage rewrite.
  - SQLite's session extension with custom conflict rules: the right tool if both copies had to
    write the same rows, but a driver switch and per-table conflict rules; split ownership needs
    neither.
  - One database on the always-on machine only: simplest, but the laptop would lose Maestro when
    that machine is down; the owner chose to keep the profile at home.
  - A job-only check-out lease: runs dry while the laptop is off for long.
- **Per-job ownership, not per-table:** the user's manual workflow on the laptop (add a job,
  tailor, score, apply with the Companion) keeps working offline.

## Part A: Who owns what

- **The laptop owns the profile:** base resumes and their versions, health and lint data on base
  resumes, career history and its documents, templates, referrals, and settings (autofill
  profile, job preferences, auto-apply limits, the full-automation switch, AI keys). The
  always-on copy holds a read-only replica, refreshed on every round; it needs it to tailor and
  fill (this includes the AI key and, when saved, EEO answers).
- **Each job has exactly one owner,** together with its job skills, application, tailored resume
  and its versions, proposal, consent events, ATS scores, gap analysis (tailoring session), Q&A,
  recorded answers, and its files (PDFs, evidence screenshots). Jobs added on the laptop start as
  the laptop's; jobs the always-on copy finds start as its own. The other machine holds a
  read-only replica, shown with a small "With your bot" / "On your laptop" mark.
- Rows of the four tables split by `resume_kind` (resume versions, lint reports, health answers
  and waivers) follow their resume: `base` with the profile, `application` with the job.
- **The always-on copy's run log** goes to the laptop, add-only, so Recent runs shows its work.
- **Never synced:** the Assistant's chats and the Companion's run data.
- **Duplicates:** the same job description saved on both (the `jobs.raw_text_hash` unique index):
  the laptop's job wins; the always-on copy drops its own and links to the laptop's.
- **Daily cap:** each copy counts the other's reserved slots from its replica, so the cap holds
  across both, within one sync interval.

## Part B: How the sync works

- **Connection:** the always-on copy holds a persistent outgoing SSH connection to the laptop over
  a private network (Tailscale) with a local forward: its `127.0.0.1:8101` reaches the laptop's
  `127.0.0.1:8001`. The laptop's `authorized_keys` line allows only that forward
  (`permitopen="127.0.0.1:8001"`, `no-pty`, no shell). It drops while the laptop sleeps and
  reconnects on its own.
- **Who drives:** the always-on copy only. Maestro ships a sync program; the machine's own
  supervisor keeps it alive. Maestro still runs no scheduler of its own on the laptop.
- **When:** every 5 minutes while the laptop answers; while it doesn't, the interval backs off
  toward 30 minutes and snaps back after the first success. An MCP tool `sync_now` lets an
  automation trigger a round at its start and end.
- **One round at a time:** a lock in the sync program and a single-flight guard on the laptop's
  sync endpoints, so a `sync_now` can never overlap a scheduled round.
- **One round:**
  1. Version check: both copies must run the same Maestro version and schema revision; otherwise
     the round is skipped and reported, never half-done.
  2. Profile, laptop → always-on copy, if it changed (it replaces its replica, files included).
  3. Always-on copy's changed jobs → laptop (read-only replicas there), with files.
  4. Laptop's changed jobs → always-on copy, with files.
  5. Requests on the other side's jobs, both ways (Part C).
  6. Handovers (Part C).
  7. Run-log rows → laptop, add-only.
  Each step is one transaction: it lands completely or not at all; a failed round retries next
  time.
- **Change tracking:** every write to a job or anything attached bumps that job's revision; any
  profile write bumps a profile revision. A round sends only what changed since the last
  acknowledged revision. Ids are identical on both machines, so re-sending is always safe.
- **Security:** the sync endpoints listen only on the laptop's `127.0.0.1`, require the sync key
  (generated once on the laptop, set on the other machine from a file or environment variable,
  never pasted into a chat), refuse any request carrying an `Origin` header, and are never
  exposed publicly. The AI key and any secret travel only inside this channel and are never
  logged.

## Part C: Handovers and editing the other side's jobs

- **Laptop → always-on copy, automatic:** with full automation on, a laptop job the user queues is
  offered at the next round; the laptop marks it "Going to your bot" and locks it except for
  **Keep it here** (cancels). Once accepted, ownership flips on both sides.
- **Always-on copy → laptop, on request:** an always-on job shows **Work on it here**; the
  request goes at the next round and is granted only when the job isn't mid-application (not
  `approved`, not inside a run's fill); otherwise "Your bot is applying to this one; try again
  after its run."
- **Requests on a non-owned job:** queue, skip, status, notes, take over, sent as requests marked
  "Sent at the next sync" and applied by the owner with Maestro's normal rules (the state machine,
  forward-only statuses, the cap). A request that no longer fits (skipping a submitted job) is
  refused with the reason, shown in Recent runs.
- **Everything else on a non-owned job is read-only** (tailoring, Q&A, scores, applying), with a
  note naming the owner. One central ownership check guards every write path: the web app, MCP
  tools, the Companion, the Assistant.
- **Laptop off:** the always-on copy keeps hunting and applying to its own jobs; the user queues or
  skips them through their agent app, which uses the always-on copy's MCP tools. A mail update
  for a laptop job (an interview invite for a job applied to by hand) waits as a request and
  lands when the laptop is next reachable.

## Part D: Setup, backups, memory, testing

- **The always-on machine (no Docker needed):** a setup script installs Maestro's backend into a
  home-directory venv and ships plain `start`, `stop` and `health` commands that any supervisor
  can call (systemd, a watchdog cron, launchd). It runs the backend on `127.0.0.1:8001` for its
  own MCP server (stdio) and its browser's uploads (resume PDFs are staged on that machine), the
  tunnel on `127.0.0.1:8101`, and the sync program. No web app there; the user sees its jobs on
  the laptop.
- **Memory budget:** the backend measured about 400 MB resident on the laptop (container ~590 MB),
  plus the MCP server process. A task trims startup (load heavy libraries such as the LLM SDKs,
  PDF and Typst engines on first use) to a stated budget, pinned by a test that measures resident
  memory after startup.
- **Backups:** Litestream on each machine streams its SQLite file (WAL mode, as today) to a local
  directory that a synced folder (Drive or Dropbox, via rclone or the client) carries to the
  cloud. Either machine can be rebuilt from its backup plus a sync round.
- **One-time steps for the user:** allow SSH and the private-network join in the agent app (if it
  asks), turn on Remote Login on the Mac and add one restricted key line, and set the sync key on
  the always-on machine from a secure store.
- **Testing:** two Maestro instances with separate databases in one test run: full rounds,
  idempotent re-sends, version mismatch skips, both handovers (including busy and Keep it here),
  the ownership check on every write path, duplicates by hash, file integrity, the sync key and
  Origin refusal, the cap across both copies, backoff and the round lock; sync-off behavior
  unchanged; browser checks of the marks and locked controls.
- **Docs:** a setup guide with one worked example (an agent app VM with a watchdog cron and a
  vault), the security model in SECURITY.md and PRIVACY.md (the always-on copy holds a read-only
  copy of the profile, AI key included), SYSTEM.md invariants for ownership and the sync channel.

## Roles

Sol and Opus build and review phase 4b in Maestro's repo, as with Parts 1–3. The always-on
machine's agent installs only from the repo after it ships, runs the setup script and sets the
sync key from its vault; it doesn't build or modify Maestro.

## Out of scope

Two writers on the same row (no merge logic anywhere); a hosted multi-user copy; the web app on
the always-on machine; anything about how the agent handles CAPTCHAs, mail or reaching the user.
