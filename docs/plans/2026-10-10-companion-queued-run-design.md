# Companion queued run: the Companion applies to your Queued jobs, several tabs at once

Approved by the owner on 2026-10-10 (brainstorming session). It extends phase 4 (full automation,
`2026-10-05-full-automation-design.md`), whose rejected option (3) "the Companion submitting" stays
rejected for Submit only. Nothing here is built yet.

## Goal

The Companion already fills one page well (observe, map, pick, verify, attach). The owner wants it
to work as an applying agent: take the jobs you queued, open them a few at a time, fill every page,
move on to the next page by itself, and stop at the review page, so the only thing left for you is
Submit. It should ask you only when it must, and ask in the tab it is working in.

The owner's main complaint with the external bot was friction: it stopped "for small things" because
of the gates. Lowering that friction is part of the goal, not a side effect.

## Owner decisions

- **How far it goes:** the Companion clicks Next / Continue on every page and stops on the review
  page. **Submit stays yours at every setting.** This lifts only the Next half of the 2026-09-26
  rule "Next and Submit stay the user's".
- **Which jobs:** your Queued jobs only. The queue is the consent step; the server applies Companies
  to skip, already-applied and the remaining daily cap before any tab opens. Full automation must be On.
- **Job boards:** the run opens the employer's own application site and never clicks anything on a
  job board. Save job records the employer's apply link from the posting the user is viewing (Part
  7); a job without one falls back to following the posting's Apply. LinkedIn Easy Apply and Indeed
  Apply park as Needs you (their terms forbid automated use).
- **Sign-in:** use the saved job-site login to sign in to an existing account. Creating an account,
  email or SMS codes and CAPTCHAs always park.
- **Where it asks:** in the tab. The tab waits on the field, the panel lists every tab that needs you,
  you answer in the form itself and press **Resume**, and that tab's run resumes. **Answers are
  always remembered** (2026-10-11): no checkbox. Resume saves them to the profile and the panel says
  "Saved N answers to your profile · Undo". Long written answers are never saved as standing answers.
- **Friction rules:**
  - A run stops only for the protected list (below) or a wall it cannot pass (CAPTCHA, email code,
    account creation). Everything else is answered, marked, and shown on the review page. Flags warn;
    they never stop a run.
  - One stop per page, not per field: fill everything else first, then park once with all that
    page's open questions together.
  - Questions that can be predicted are asked once, before the run (on the Queue view, Part 5).
  - An answer is asked once: saved to the profile, it never parks again.
  - A job with no tailored PDF is settled before the run, never during it (Part 7). The run never
    quick-tailors a job that has an open tailoring session or a tailored draft: the custom tailoring
    path is never overwritten.
- **Answer the safer question:** the run gives a safe answer to anything NOT on the protected list.
- **Protected list** (park unless a saved fact answers it): work authorization and sponsorship;
  salary and pay; EEO and demographics (unless EEO consent); criminal or background history; security
  clearance; signatures and legal attestations (unless Agreements consent); factual education or
  experience claims the history does not support (degrees, dates, years with a skill).
- **One "Screening answers" dial** replaces the low-stakes switch (details in Part 3). Default:
  **Backed by your history**.
- **Where the run lives:** the side panel (approach A), built with three seams so a later move to the
  service worker or an offscreen document is a change of host, not a rewrite.
- **Mark applied:** when a tab shows a confirmation page after you pressed Submit, the run marks
  the job applied, with an undo on its row.
- **Job memory:** the 30-minute, one-key-per-browser `widget.session` memory becomes per-tab memory,
  for queued runs AND for ordinary single-page use.
- **Job step buttons (decided 2026-10-11):** with full automation on, the Companion's Job step offers
  **Apply** (primary: save, pick the resume, queue as the user's yes, then run this one job in this
  tab through to review) and **Queue** (save and queue for a later Apply to queued). Plain **Save job**
  shows only when full automation is off, exactly as today.
- **Panel look (2026-10-11):** direction C, "one next step": a single Next card that changes as the
  run moves (Apply → Filling page N → Needs you → Ready to submit), under a four-segment progress bar.
  Mockups of the Job step (Save job / Apply + Queue / finish tailoring first), a running job (filling,
  Needs you, a wall, Ready to submit with the 8 s Undo) and the Queue view (before a run, running,
  finished) live in the owner's private design canvas. Tasks 19, 20 and 20a build to them.
- **Two views (2026-10-11):** a **This page | Queue (N)** switch tops the panel. **This page** is the
  Job → Resume → Fill → Track steps for the active tab, as today; its Job step's Apply and Queue are
  how jobs enter the queue. **Queue** is a live list of the user's Queued jobs, read from the server:
  before a run, each row shows its readiness and a tick, and **Apply to N** starts the run; during a
  run the same rows show live status; after it, a summary sits above them. There is no separate
  "Before we start" sheet. A fresh open picks the view: an application form or a job posting opens
  on This page; any other page, and any open while a run is going, opens on Queue.
- **Park less (2026-10-11):** a run parks only on required fields it could not answer or could not
  operate. A field that shows a value the engine could not prove does not park: the run clicks Next
  and lets the page's own validation decide (refill once, then park with the page's error text).
- **Try harder, remember, report (2026-10-11), Part 8:** run tabs get a bigger per-field budget; a
  field the user fixes by hand teaches the recipe book; failures accumulate in a durable,
  value-free known-gaps list that ranks what the engine should learn next.

Rejected: answering in the web app's Agent inbox (more to build; you visit each tab for Submit
anyway); the service worker or an offscreen document as the first host (survives closing the panel,
but costs a checkpoint/resume rewrite or a new permission and relay now); "Queued means I qualify" as
the default; including board-native apply.

## Part 1: Architecture

Three seams, built in from the start:

1. **The runner is host-agnostic.** `shared/queue-run.js` is a plain module with its transport
   injected, as `shared/guided-run.js` already is. The panel is its first host.
2. **Run state is plain data, saved at every page change.** One JSON record per tab:
   `{tabId, jobId, applicationId, proposalId, hosts, step, status, parked}`, mirrored to
   `chrome.storage.session` at every page boundary. Reopening the panel shows where each run got to.
3. **Page operations live in the content scripts.** Classify, find the advance button, sign in and
   fill all run in the page through the existing `sw.js` fan-out and frame gate
   (`inv-frame-earns-data`). Any host can call them.

The runner drives each tab through: open, follow Apply, sign in, fill, advance, ..., review (stop).
Filling is today's `shared/fill-loop.js` with the run's answer rules. Classification and advance are
new content-script operations.

The panel's single `card` store stays the view of the ACTIVE tab. Run records live beside it, pinned
to their own tabs: today's "a tab switch cancels the fill" rule stays for single-page Autofill and
does not apply to run tabs, whose fan-out targets their own `tabId`.

What this does not give for free: runs that survive closing the panel or Chrome (that is the later
move to a service worker or offscreen host, reading the run records), and anything scheduled
(Maestro runs no scheduler; a scheduled run would come from the user's own agent).

## Part 2: Reading the page and clicking Next

**Page kinds.** Code decides first, from DOM signals:

| Kind | Signal | Run does |
|---|---|---|
| Posting | an Apply button or link | follow it; board-native apply parks |
| Sign-in | one visible password input | saved login (Part 4) |
| Create account / email code | confirm-password input, or a one-time-code input | park |
| CAPTCHA | a visible challenge frame (an invisible badge alone does not count) | park |
| Form step | fillable fields and a Next-like button | fill, then Next |
| Final form / review | a Submit-like button and no Next-like one | fill, then stop: Ready to submit |
| Confirmation | "application received / thank you" and no form | mark applied (after your Submit) |
| Closed | "no longer accepting applications" | Position closed |

**Choosing the button.** Code collects visible, enabled buttons near the form and sorts each as
Next-like (next, continue, save and continue, review), Submit-like (submit, apply, send, finish,
complete) or unclear. Only unclear ones go to a new `POST /api/autofill/page`, shaped like `/step`:
the model picks among candidates code labelled Next-like or unclear, and sees button texts only,
never page prose. **A Submit-like button is never clickable. When in doubt, the page is the review
page and the run stops.**

**Known buttons first.** A small table (`shared/ats-buttons.js`) names each common ATS's own
Next and Submit markers (attributes such as automation ids, not label text), starting with Workday,
Greenhouse, Lever, Ashby and iCIMS. On a known ATS the table decides; a marker it lists as Submit is
Submit whatever its wording. Unknown sites use the generic sort above. This is navigation only: the
owner's "no per-widget procedures" rule for filling stands.

**Before Next:** the fill finished, the resume is attached, the page's receipt is recorded
(`shared/receipt.js`), and no required field is open (an open one parks the page instead).

**After Next:** wait for a change (URL, step heading, or field fingerprint). The same page with
visible error text gets one retry fill on the flagged fields, then parks with the page's own error
text. At most 15 steps per application; the same fingerprint seen twice parks.

**New tabs:** a tab opened by Apply (`openerTabId`) replaces its opener in the run.

**Pins:** a browser test with a set of Submit wordings proves Submit is never clicked.
`content/sections.js`'s `NAV_ID` guard for section Add buttons stays as it is.

## Part 3: Answers

**Screening answers dial** (Settings › Form filling; replaces "Answer low-stakes questions for me"):

| Level | Answered without asking |
|---|---|
| Facts only | saved answers and career history; the rest parks (today's low-stakes Off) |
| Backed by your history (default) | the above; the low-stakes kinds answered in the job's favour; "N years of a skill" Yes when the history shows the skill and does not contradict the years |
| Queued means I qualify | the above; every requirement and years question on a Queued job is Yes, except a years question the history clearly contradicts (asked; owner 2026-10-13: Yes only when the history is silent or shows enough) |

- The protected list sits outside the dial at every level.
- EEO consent and Agreements (`consent_forms`) stay separate: they are legal permissions, not answer
  style.
- One setting, every reader: the Companion, the queued run, and the user's external agent through
  the Job Search Brief (the "one shared switch" `2026-10-06-application-preferences-design.md` asked
  for).
- Migration: no stored value reads as the new default; an explicit low-stakes `false` reads as Facts
  only; `true` reads as Backed by your history.
- Every answer the dial gives is marked on the receipt and listed under "Check before you submit"
  on the review page.
- The map prompt (`services/autofill_map.py`) gets the level 2 years rule and the level 3 rule; a
  fill request names its job so level 3 can tell a Queued job, and the page's host, which must
  match the job's apply or posting site (a restored application on the same ATS tenant is not
  enough; batch-2 review, 2026-10-13).
- Clearance and "employment by a kind of organization" questions never reach the low-stakes judge
  at any level (their own sentinel); only years questions widen at level 3.

## Part 4: Sign-in with the saved login

- `POST /api/companion/job-site-login`, admitted only for the configured Companion extension
  origin. Same gates as the agent hand-off (`services/proposals.py`): full automation On, job Queued
  or approved, company not skipped. Each hand-off records
  `ConsentEvent(action="login_shared", channel="companion")`, never the value.
- A dedicated `sign_in` content operation types email and password into the TOP frame, only on a
  host the run reached from the job's apply link, then clicks Sign in. The fill loop and the model
  never see a password input; the password never reaches traces, receipts or telemetry.
- No retries: a failed sign-in parks at once ("Sign-in didn't work"), so the account is not locked.
- `inv-job-site-password-local` is rewritten to name the second route.

**Batch-4 review decisions (owner, 2026-10-13):** the saved job-site password is typed only on
known ATS hosts (the Companion's ATS host list); any other sign-in page parks for the user
(`sign_in_yourself`). A posting's Apply is pressed only when it is a same-tab http(s) link on the first
read of a tab the run opened. Board pages (LinkedIn, Indeed) are `board_native` before any other check.

## Part 5: Running several tabs, the run list, Needs you

- **The Queue view** (shown while full automation is On) reads `GET /api/autofill/queue-run`:
  Queued jobs minus skipped companies and already-applied, up to the remaining daily cap, each with
  its apply link, PDF readiness and knock-out pre-scan. **Apply to N** starts the run.
- **Before a run, on the same list:** each row carries its readiness inline. Profile facts the
  pre-scan found missing are asked once (a link to Settings) and saved. Jobs with a knock-out
  conflict are unticked with "Apply anyway"; an unstated requirement just runs. Jobs with no PDF show
  the choice that will be made, with Change (Part 7).
- **Opening tabs:** a dedicated normal window, 3 tabs filling at once by default (1 to 5 in the
  panel). Ready-to-submit tabs stay open and do not count as filling; opening pauses at 10 waiting
  tabs.
- **Pacing:** a random gap of a few seconds between opening jobs, so a run never arrives as a burst
  from one browser.
- **During a run, the same list** shows one row per job: Opening, Filling page N, Needs you,
  Ready to submit, Applied, Stopped: reason; unticked jobs stay as Queued, "Not in this run". A row
  brings its tab forward and switches the panel to This page for it. A parked tab lists its open
  questions; the user answers in the form and presses Resume. Stop per row and Stop all.
- **After your Submit:** a confirmation page in that tab marks the job applied with an undo (consent
  channel `frontend`, since you clicked Submit; the confirmation is the submit evidence; the
  proposal goes Queued, approved, submitted, so the daily cap counts it). With no confirmation page
  the row offers Mark applied.
- **Run log:** at the end the Companion posts a Recent runs entry (`agent_runs`, automation
  "Queued run") with counts: ready, needs you, applied, stopped.
- **Time measured:** per application, value-free: run time from tab open to Ready to submit, and
  the user's own time (answering parked questions, Ready to submit to applied). The run log carries
  the medians, so "seconds of your time per application" is a measured number, not a claim.

**Risk measured first:** Chrome throttles background tabs (no animation frames; timers slow to once
a second, then once a minute after about five minutes hidden). The first build task is a spike:
fill time on a fixture form in a background tab of the run window vs a foreground tab. The default
of 3 follows from it.

## Part 6: Per-tab job memory

`widget.session` is one key per browser with a 30-minute TTL (`panel.js` `SESSION_TTL_MS`), so a
long wizard forgets its job and a second tab's pick overwrites the first. It becomes a per-tab entry
in `chrome.storage.session`, alive while the tab is open and cleared when Chrome closes. The origin
and tenant guards and "the backend wins" guard (`decisions.restorableSession`) stay. The old key is
read once while installs move over. Run tabs bind through their run record, with no timer, across
pages and into a tab Apply opens. The one-hour application-flow window gets the same per-tab
treatment for run tabs.

## Part 7: Apply link and resume readiness

- **Apply link at Save.** Jobs store only `source_url` today. Save job (Companion) also records
  the employer's apply link when the posting page the user is viewing exposes one (an external Apply
  link, or the posting's structured data), as a new `apply_url` on the job. The page the user is on
  is read; nothing is fetched in the background with the user's cookies. The run opens `apply_url`
  when present, else `source_url`.
- **Prepare when queued: optional, off by default.** A setting "Prepare queued jobs" quick-tailors
  and renders a PDF when a job is Queued, so a run starts filling at once. It skips any job with an
  open tailoring session or a tailored draft.
- **At run start,** jobs without a PDF show on the Queue view with a per-job choice: Quick
  tailor, Use base resume, or Skip. Default Quick tailor, except a job with an open custom tailoring
  session defaults to Skip ("finish tailoring first"). Quick tailor and renders run one at a time
  while earlier tabs fill. Nothing in a run overwrites a custom tailoring session or draft.

## Part 8: Try harder, remember, report

The fill loop already gives each field a small state machine (read, map, explore, pick, commit,
verify, plus an AI-chosen adaptive step from moves code lists, never repeating a failed move), and
the recipe book already remembers which known move worked per widget family. This part extends both.

1. **Try harder in runs.** A queued-run tab passes per-run limits to the fill loop: about 60 s per
   field (FIELD_MS, today 25 s) and 12 adaptive steps (MAX_STEPS, today 8). Single-page Autofill keeps
   today's limits. Limits become a per-run option, never a change to the shared module defaults, so
   parallel runs and the user's own fill don't affect each other.
2. **Learn from the user's fix.** When a parked field is fixed by hand and the user presses Resume,
   the page reports which gestures the user used on that widget (pointer or keyboard open; typed then
   Enter, or typed then waited), never what was typed. A gesture sequence that matches a move the
   engine knows becomes a recipe lesson at `probation` for that site (one demonstration never makes
   it trusted). One that matches nothing is noted as a missing technique in the known-gaps list.
3. **Known-gaps list.** A durable, value-free table: widget family hash, host, field shape, outcome
   (`cannot_operate`, `unconfirmed`, `user_fixed`), counts and last seen. It survives the 50-run trace
   limit, is posted only when `telemetryEnabled === true` (the fill log: off by default, Options ›
   Keep a fill log), is cleared by `DELETE /api/autofill/telemetry` (it holds hosts),
   and is ranked in `scripts/fill_trace.py report` and a one-line diagnostics summary in Settings ›
   Form filling. Each engine fix it drives ships with a recorded test form.

## Part 9: The fill agent: context, tools, ideas (added 2026-10-13)

The owner's live run on a Workday form (2026-10-13, five stored run traces) showed the loop isn't
short of time or tries. It's short of things to try. The owner's direction: the fill agent should
behave like a normal AI agent that has the context, the tools and at least the ideas to fill a
form. In simple words:

- **Context (what it knows when it is stuck on a field).** The question as worded, whether it is
  required, the options the page shows, the saved fact it is filling (server-side, as today), the
  job, every move it already tried and what each did, what worked on this site before (the recipe
  book), and the kind of widget it is facing.
- **Tools (what it can do).** The moves the page code offers, plus new ones: search with a term the
  agent writes (a shorter word, a synonym, the category), clear and retype, and tick a row's own
  checkbox. Typing a search is never an answer: an answer is still a click that clears the slot's
  match floor, exactly as today.
- **Ideas (how it thinks about the next try).** A short technique card per widget kind (search box
  with staged results, multi-pick list with pills, plain dropdown, checkbox group, date), about ten
  lines each, sent with every adaptive step: what to try after which failure. Cards are generic
  widget craft, never per-site procedures (the Goal Card's non-goal stands). The recipe book (what
  worked on this site) and the known-gaps list (Part 8.3) feed which cards get written next.
- **Check every action.** Every move is verified on the page before the next one. For a list field
  (skills), each item must show as a pill; a missing pill is clicked once more, then reported.
- **Don't go round in circles.** A move that left the page looking the same as before counts as
  failed, even if the page said it progressed. The same search for the same value is never sent
  three times.
- **Never touch a robot trap.** A field that tells humans not to fill it (a honeypot) is never
  filled, never asked about, and never counted as missing.
- **Don't ask what isn't needed.** An optional field with no saved fact is left blank quietly; a
  field the page already holds an answer in is "already there", even when no fact maps to it.
- **Let the page settle.** After a choice redraws part of the page, typing waits for the page to
  stop changing, so a field is typed once, not twice.

What it found, and which of the above fixes it:

| Live miss (Workday, 2026-10-13) | Fixed by |
|---|---|
| A "for robots only, do not enter" field was filled with the website | Robot trap |
| Skills: ~19 picks, 5 pills; one pick hung 20 s and the field ran out of time | Check every action; per-item time |
| Field of Study: the same exact-value search 8 times, then "couldn't operate" | Tools (own search term), don't go round in circles, ideas |
| Country Phone Code asked while it showed "United States (+1)" | Already there |
| Phone Extension (optional) asked | Don't ask what isn't needed |
| Every text field typed, went stale, typed again | Let the page settle |
| Phone Device Type, preferred name, conflict-of-interest questions asked | Part 3 (the dial) and always-remembered answers |

## Rules and docs changed on purpose

- SYSTEM.md §6: `inv-policy-deny-list-single-source` ("Next/Submit stay the user's" becomes "Submit
  stays the user's at every setting; Next is the Companion's only during a queued run with full
  automation On"), `inv-eeo-standing-consent` (the same sentence), `inv-job-site-password-local`,
  `inv-auto-consent-gated`. §7 Guided fill and Chrome extension.
- `extension/shared/policy.js` header, `extension/README.md`, `extension/INTERNALS.md` ("never
  advances", "Mark applied is never automatic", the session-key notes), `schemas/eeo_consent.py`
  wording, CONTRIBUTING (refusal #1 names the queued run as capped and queued).
- `2026-10-05-full-automation-design.md`: a note pointing here.
- SYSTEM.md is at its line cap: groom before documenting.

## Testing

- Unit fixtures for the classifier, one per page kind, and for button sorting.
- Recorded test forms (saved, scrubbed page snapshots with made-up employers) for Workday,
  Greenhouse, Lever, Ashby and iCIMS: the classifier and the known-buttons table run against each.
  They back a coverage table in the Companion docs: deep, generic or untested per ATS.
- Backend: Prepare queued jobs and the run-start choice never touch a job with an open tailoring
  session or a draft.
- Browser tests (bundled Chromium): a three-step wizard ending on review; Submit wordings never
  clicked; sign-in; CAPTCHA and email-code pages park; a validation-error retry; three tabs at once;
  per-tab memory surviving 30 minutes (clock injected) and a second tab's pick.
- Backend: dial levels and migration, gates on each new route, the proposal transitions on
  auto-mark, the brief carrying the dial.
- Owner live check: a real queued run on Greenhouse, Lever, Workday, Ashby and iCIMS jobs, each
  stopping on its review page.

## Known risks

- Sites that ignore script clicks: the only fix is debugger input, which the owner ruled out; such
  pages park.
- Background-tab throttling (measured first).
- Several tabs mean more concurrent model calls (each `/map`, `/pick`, `/step` has a 9 s budget) and
  more SQLite writes.
