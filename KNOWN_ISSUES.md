# Known issues, rough edges, and where help is wanted

This project is early. It is used daily by its author and the test suite is
large, but "one person's tool that works on their machine" and "software other
people can rely on" are different standards, and this file is where the gap is
written down honestly.

Read it before you file a bug — several things below look like defects and are
recorded decisions. Read it before you pick up work — the last section is the
part that needs other people.

For the engineering detail behind any item, `SYSTEM.md` §11 is the deferred
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
- **The MCP server.** 77 tools across six profiles, cold-install tested in CI
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
- **The extension does not handle every ATS — and autofill is not
  first-try-clean even on the ones it does.** Workday, Greenhouse, Lever and
  iCIMS get the most attention because those are what the author meets; expect
  gaps elsewhere (§11.12, §11.18). Even on covered platforms a first run
  rarely fills everything: unusual widget kinds (multi-step button dropdowns,
  custom comboboxes) and less-common field domains fall through to you, by
  design — the fill engine abstains rather than guesses.
- **Unusual resume shapes import unevenly.** Ingest is most confident on
  conventionally structured resumes. Content that does not map cleanly onto
  the structured model — nonstandard sections, merged entries, heavily
  designed layouts — can land in the wrong place or need manual rearranging
  after import.
- **Adding a Typst template is finicky.** The bundled Typst templates work,
  but bringing a new one in through the in-app chat or MCP is rougher than
  the LaTeX path: depending on the template it can take source-level
  adjustment, or extra package installation, before validation passes. The
  web "New template" flow starts from a LaTeX starter only today.
- **Formatting knobs on conversationally created templates need hand-tuning.**
  A template brought in through chat or MCP often compiles before its knobs
  (margins, spacing, fonts) are actually wired to the layered override
  system — expect a pass of source-level work before per-resume and
  per-application overrides behave on it.
- **Local models are supported but not battle-tested.** The OpenAI-compatible
  path (Ollama, LM Studio, vLLM) is a supported setup, but it has not been
  exercised hard against the app's heavier demands — long tailoring prompts,
  strict JSON output, streaming tool calls for chat. Expect model-dependent
  rough edges, and use the per-model **Test** button in Settings to measure
  what your model can actually do before relying on it.
- **Onboarding import is capped at 10 files** and does not resolve entities
  across kinds, so a certificate can land as a sibling of the job it belongs
  to. (§11.16)
- **Résumé attach is narrower than the fill.** A page with more than one upload
  box is refused with a sentence rather than resolved, and the offer is counted
  in the top frame only — so a Greenhouse or Lever form inside a subframe never
  gets offered an attach, even though the fan-out would reach it. (§11.22)

### Where the product is still confusing

From the 2026-08-19 usage audit. These are not bugs in the sense that something
throws; they are places where the app is operable by someone who already knows
the domain model and not yet self-explanatory to someone who does not.

- **Two things are called "Profile".** Career KB → Profile holds your identity
  and is the source of truth. The sidebar Profile page holds persona, job
  preferences and a separate autofill copy of your contact details. "Fill from
  resume" copies once into blank fields and never syncs again, so the two can
  drift with nothing telling you.
- **Re-importing the same résumé creates a second base.** The slug comes from
  the filename, so an updated copy of the same document lands as `resume_2`
  with its own KB evidence, instead of being offered as an update.
- **Delete, archive and retire do not add up to one safety model.** The
  base-résumé dialog warns that deletion cannot be undone, while the backend
  actually soft-deletes and keeps the files — and Career KB entities and points
  have genuinely destructive deletes next to reversible ones. There is no trash
  and no restore.
- **Neither library searches.** Career KB and Base Résumés filter by kind or
  archived-ness only, and the KB import picker has no search either, so finding
  one fact among a hundred means scrolling.
- **There are three ways to move KB evidence into a résumé** — create a base
  from selected entities, "Send to resume" from an entity, and "Import from
  Career KB" hidden under the editor's overflow menu — and they do not share a
  picker or a result summary. The overflow one omits custom sections.
- **A role-targeted base still inherits every global skill.** Narrowing which
  entities compose does not narrow `KBProfile.skills`, so a résumé built for one
  role can arrive carrying unrelated skill groups.
- **Render failures are recorded but not shown.** `render_error` is persisted
  and the Output tab does not display it, so a failed PDF reads as a generic
  "regenerate" rather than naming the template or compiler cause.
- **Career KB points have provenance but no history.** Editing a point
  overwrites its text; there is no revision list and no restore, unlike résumés,
  which snapshot every write. Bases also do not summarise "the KB changed since
  this was assembled".
- **The tracker records state but does not manage follow-through.** No next
  action, due date, reminder, status history, or snapshot of the exact artifact
  you actually submitted.
- **Import auto-approves more than the docs imply.** Unchanged verbatim bullets
  from a file you wrote are approved on import; only merged or AI-generated
  points land in the review inbox. Defensible, but the result dialog does not
  say so.

### Operational gaps

- **A backup is two things and nothing joins them.** Postgres holds the
  relational state; `base_resumes/`, `applications/`, `kb_documents/`,
  `exports/`, `settings/` and `logs/` hold the rest. A database dump alone is
  not a restore, a directory copy alone is not either, and there is no bundle
  command or tested restore path.
- **A stored ATS score cannot be exactly reproduced.** Scoring is deterministic
  given its inputs, but the row does not record `as_of`, the résumé/JD content
  hashes, or the embedding model — and recency is computed against *today* —
  so the same document can score differently on a different day with nothing
  saying why.
- **Two moderate npm advisories** ride in through Monaco's bundled DOMPurify.
  CI gates at high-and-above, so they do not fail the build; whether any
  app-controlled HTML reaches that sanitiser has not been established.

### Security work this release deliberately did not do

The 2026-08-19 audits produced more than one release could honestly absorb.
What landed is in `SECURITY.md` §3; what did not is here, so nobody has to
reverse-engineer the gap. None of these is reachable from the network — they
matter to the extent that something already running as you, or a page you have
open, is hostile.

- **LaTeX rendering is bounded, not isolated.** Paranoid file access stops a
  template reading outside its staging directory, but the compiler still runs
  in the backend process's world, with its environment and its mounts. The real
  fix is a disposable, networkless render worker holding no secrets and no PII
  mounts. Until then: do not render a template you have not read.
- **No CSRF capability token.** A disallowed `Origin` is now refused outright,
  which closes the practical version of this, but there is no per-install token
  binding a state-changing request to the app that issued it.
- **Mutating chat tools are not individually confirmed.** Resume edits arrive
  as approval cards; template administration does not. A successful prompt
  injection in a job description could try to reach those tools.
- **No upload, request-size, token or spend ceilings.** A large or malicious
  document can consume memory, CPU and model budget; nothing caps the daily
  spend.
- **Cross-object links are not verified.** Nothing enforces that an
  application's job matches the proposal's job, so a mislinked record is
  possible.
- **`DELETE` does not always erase.** Base-resume deletion is a soft delete
  that keeps files and version history; deleting a KB entity can leave its
  document directory behind. There is no purge, and no inventory of every copy.
- **Chat attachments are resolved by id without checking the session** they
  were uploaded to.
- **No Content-Security-Policy on the frontend**, and detailed compiler and
  provider errors (including absolute paths) can cross the API boundary.

Help is genuinely wanted on all of these; the render worker and the resource
ceilings are the two with the best effort-to-value ratio.

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

Two things are deliberately live in two forms at once. `SYSTEM.md` §13
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
- Read the relevant part of `SYSTEM.md` §6 (cross-cutting invariants).
  Most review comments on this codebase are invariants, not style.
- Open an issue before a large change. Several items above have a decided
  approach that is not obvious from the code.
