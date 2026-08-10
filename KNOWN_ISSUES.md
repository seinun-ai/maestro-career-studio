# Known issues, rough edges, and where help is wanted

This project is early. It is used daily by its author and the test suite is
large, but "one person's tool that works on their machine" and "software other
people can rely on" are different standards, and this file is where the gap is
written down honestly.

Read it before you file a bug — several things below look like defects and are
recorded decisions. Read it before you pick up work — the last section is the
part that needs other people.

For the engineering detail behind any item, `docs/SYSTEM.md` §11 is the deferred
list and §13 is the migration ledger. This file is the map; that one is the
territory.

---

## What is solid

These have real coverage and are unlikely to move under you.

- **ATS scoring is deterministic.** No LLM anywhere in the scoring path. The
  same resume, job description and config version produce a byte-identical
  0–100 score and breakdown, every time. This is the part most worth trusting.
- **Rendering.** Both engines (LaTeX and Typst) compile the bundled templates,
  and cross-engine parity is enforced by tests, not by eye.
- **The Career KB → resume → application chain.** Approved evidence composes
  verbatim; rewriting is a separate, consented step. Resume versions are
  recorded, so nothing is one-way.
- **The MCP server.** 65 tools across six profiles, cold-install tested in CI
  against the exact command the README gives you.
- **Data stays local.** No telemetry leaves your machine — see the extension
  section of the README for what the one telemetry endpoint stores and how to
  clear it.

## What is rough

Honest list. None of these are secret; most are §11 items with a number.

- **The tracker does not paginate server-side.** The client caps at 500 rows.
  Past that, the page gets slow. (§11.5)
- **No "ready to apply" gate.** Health, page-count, em-dash and contact checks
  exist, but nothing runs them against the *exact rendered PDF* in one pass, so
  it is still possible to send something a check would have caught. (§11.2)
- **Score staleness.** Scores derived from a base resume are not re-scored when
  that base resume changes, so a score can quietly describe an older document.
  (§11.3)
- **Job description fields are not correctable after extraction.** Only
  `source_url` can be edited; a mis-extracted title or seniority is stuck.
  (§11.4)
- **Cover letters have no immutable safety block.** The Q&A path has one; the
  cover-letter path does not, so its output is less constrained. (§11.11)
- **Chat-attached documents do not become KB sources.** Only their extracted
  text is kept, so provenance stops at the chat message. (§11.6)
- **The extension does not handle every ATS.** Workday, Greenhouse, Lever and
  iCIMS get the most attention because those are what the author meets. Expect
  gaps elsewhere, and see §11.12 and §11.18.
- **Onboarding import is capped at 10 files** and does not resolve entities
  across kinds, so a certificate can land as a sibling of the job it belongs
  to. (§11.16)

## Limitations by design

These are decisions, not bugs. Please do not file them as defects; if you
disagree, open a discussion rather than a PR.

- **Single user, no authentication.** Every HTTP and MCP endpoint is
  unauthenticated and bound to localhost. This is what makes the tool simple
  and private. Do not expose it to a network. See `SECURITY.md`.
- **No hosted version, and no multi-tenancy.** Adding either would reverse the
  main design property and reintroduce the data-exposure risk this project was
  built to avoid.
- **The ATS score does not predict any real ATS.** It is our own deterministic,
  reproducible model. Anyone claiming to predict Workday's or Greenhouse's
  internal scoring is guessing. The narrowness is the point.
- **No job-board search.** Jobs are captured from postings you are already
  looking at. Scraping boards is a legal and durability problem we would rather
  not own.
- **No bulk auto-apply.** Employers now filter for machine-generated volume;
  building it would put the tool on the wrong side of the trend it exists to
  answer.

## Migrations in flight

Two things are deliberately live in two forms at once. `docs/SYSTEM.md` §13
carries the full ledger with removal triggers.

- **Two render engines.** LaTeX and Typst are both first-class and both
  supported. The default is LaTeX; a switch to Typst was considered and is on
  hold. Changes to templates or rendering must handle both.
- **Autofill profile shapes.** `work_auth` and `education` each have a legacy
  and a typed form, with readers for both. If you touch autofill, check §13
  before assuming which shape you have.

## Where help is wanted

Ordered roughly by how self-contained they are. Every one of these is a real
gap, not busy-work invented for contributors.

**Good first changes**

1. **Server-side tracker pagination** (§11.5). Contained, testable, and it fixes
   a real slowdown.
2. **URL canonicalization server-side** (§11.9). Tracking-parameter stripping is
   currently every caller's job, which means it is done inconsistently.
3. **Cover-letter safety block** (§11.11). Mirror `QA_OUTPUT_CONTRACT` from
   `prompt_assembly`; the pattern to copy already exists.
4. **`latex_escape_url`** (§11.7). Contact URLs go through the wrong escaper and
   `~` corrupts. The fix touches both templates, so it needs cover-letter
   regression tests — which is most of the work.

**Bigger, and genuinely useful**

5. **The "ready to apply" gate** (§11.2). High user value. The metadata path it
   needs already ships.
6. **Typed op vocabulary across chat, REST and MCP** (§11.1). Custom-section ops
   are hand-coded per surface today and every new op multiplies the drift.
7. **Extension coverage for more ATS platforms.** The most valuable contribution
   anyone could make, and the hardest to fake: it requires meeting a real form.
   The fixture corpus in `backend/tests/fixtures/autofill/` shows how to add a
   control shape **without** pasting captured DOM.
8. **Token-cost visibility.** Show what a tailoring run cost. Makes the
   local-model argument concrete at the moment it is felt.

**Wanted, but talk to us first**

9. **Sanctioned job ingest** via an official API. This closes the one real
   functional gap versus paid tools without taking on scraping.
10. **Provider-aware model routing** — cheap or local models for mechanical
    steps, a frontier model for tailoring.

## Before you start

- Read `CONTRIBUTING.md`. It is short, and it names the two things that will
  get a PR sent back: adding a GPL/AGPL dependency, and claiming the ATS score
  predicts a real system.
- Read the relevant part of `docs/SYSTEM.md` §6 (cross-cutting invariants).
  Most review comments on this codebase are invariants, not style.
- Open an issue before a large change. Several items above have a decided
  approach that is not obvious from the code.
