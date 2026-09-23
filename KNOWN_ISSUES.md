# Known issues and rough edges

This project is early. It is used daily by its author and the test suite is
large, but "one person's tool that works on their machine" and "software other
people can rely on" are different standards, and this file is where the gap is
written down honestly.

Read it before you file a bug — several things below look like defects and are
recorded decisions. Want to help? The work that needs other people is under
[Where help is wanted](CONTRIBUTING.md#where-help-is-wanted) in
`CONTRIBUTING.md`, with the migrations still in flight just below it.
Maintainers: the engineering detail behind every item here lives in
`SYSTEM.md`.

---

## What is solid

These have real coverage and are unlikely to move under you.

- **ATS scoring is deterministic.** No LLM anywhere in the scoring path. The
  same resume, job description and config version produce a byte-identical
  0–100 score and breakdown, every time. This is the part most worth trusting.
- **Rendering.** Both engines (LaTeX and Typst) compile the bundled templates,
  and cross-engine parity is enforced by tests, cover letters included.
- **The Career KB → resume → application chain.** Approved evidence composes
  verbatim; rewriting is a separate, consented step. Resume versions are
  recorded, so nothing is one-way.
- **The MCP server.** 83 tools across six profiles, cold-install tested in CI
  against the exact command the README gives you.
- **Data stays local.** No telemetry leaves your machine — see the extension
  section of the README for what the one telemetry endpoint stores and how to
  clear it.

## What is rough

- **The tracker slows down past 500 rows.** It loads everything at once and
  stops at 500.
- **No single "ready to apply" check on the final PDF.** A knock-out pre-scan
  compares the posting's stated requirements (work authorization, OPT policy,
  salary) against your profile on the job Overview and in the agent final
  review — but health, page-count, em-dash and contact checks still don't run
  against the *exact rendered PDF* in one pass, so it is still possible to send
  something a check would have caught.
- **Scores can go stale.** Scores derived from a base resume are not re-scored
  when that base resume changes, so a score can quietly describe an older
  document.
- **A mis-read job description can't be corrected.** After extraction only the
  posting link can be edited; a wrong title or seniority is stuck.
- **Documents attached in chat don't become Career KB sources.** Only their
  text is kept, so the trail back to the original file stops at the chat
  message.
- **The extension does not handle every ATS — and autofill is not
  first-try-clean even on the ones it does.** Workday, Greenhouse, Lever and
  iCIMS get the most attention because those are what I meet in my own search;
  expect gaps elsewhere. Even on covered platforms a first run rarely fills
  everything: unusual widgets (multi-step button dropdowns, custom comboboxes)
  and less-common questions fall through to you, by design — the extension
  leaves a field alone rather than guess.
- **Unusual resume shapes import unevenly.** Import is most confident on
  conventionally structured resumes. Nonstandard sections, merged entries and
  heavily designed layouts can land in the wrong place or need rearranging by
  hand afterwards.
- **Adding a Typst template is finicky.** The bundled Typst templates work,
  but bringing a new one in through the in-app chat or MCP is rougher than
  the LaTeX path: depending on the template it can take source-level
  adjustment, or extra package installation, before validation passes. The
  web "New template" flow starts from a LaTeX starter only today.
- **Formatting controls on a template made in chat need hand-tuning.** A
  template brought in through chat or MCP often compiles before its margins,
  spacing and fonts are actually wired to the per-resume and per-application
  formatting controls — expect some source-level work before those behave.
- **Local models are configurable but untested.** The OpenAI-compatible path
  (Ollama, LM Studio, vLLM) can be pointed at with `OPENAI_BASE_URL`, but it has
  not been exercised against the app's heavier demands — long tailoring prompts,
  strict JSON output, streaming tool calls for chat. Expect model-dependent
  rough edges, and use the per-model **Test** button in Settings to measure
  what your model can actually do before relying on it.
- **Onboarding import takes at most 10 files** and does not connect related
  items of different kinds, so a certificate can land next to the job it
  belongs to instead of inside it.
- **Résumé attach is narrower than the fill.** A page with more than one upload
  box gets a sentence of explanation instead of an attach, and a Greenhouse or
  Lever form embedded inside another page is never offered one at all, even
  though the fill reaches it.

### Where the product is still confusing

Nothing here throws an error; these are places where the app makes sense to
someone who already knows how it is put together, and not yet to someone who
does not.

- **Two things are called "Profile".** Career KB → Profile holds your identity
  and is the source of truth. The sidebar Profile page holds persona, job
  preferences and a separate autofill copy of your contact details. "Fill from
  resume" copies once into blank fields and never syncs again, so the two can
  drift with nothing telling you.
- **Re-importing the same résumé creates a second base.** The name comes from
  the filename, so an updated copy of the same document lands as `resume_2`
  with its own KB evidence, instead of being offered as an update.
- **Delete, archive and retire do not add up to one safety model.** The
  base-résumé dialog warns that deletion cannot be undone, while the app
  actually keeps the files — and Career KB entities and points have genuinely
  destructive deletes next to reversible ones. There is no trash and no
  restore.
- **Neither library searches.** Career KB and Base Résumés filter by kind or
  archived-ness only, and the KB import picker has no search either, so finding
  one fact among a hundred means scrolling.
- **There are three ways to move KB evidence into a résumé** — create a base
  from selected entities, "Send to resume" from an entity, and "Import from
  Career KB" hidden under the editor's overflow menu — and they do not share a
  picker or a result summary. The overflow one omits custom sections. The
  **KB sync (N)** button in the base studio is not a fourth: it goes the other
  way on purpose, drafting new and changed résumé items into the Career KB.
- **A role-targeted base still inherits every skill.** Narrowing which entities
  go into a base does not narrow the skills list on your Career KB profile, so a
  résumé built for one role can arrive carrying unrelated skill groups.
- **A failed render says that it failed, not why.** The editor marks the preview
  as stale after a failed PDF render, but does not name the template or
  compiler problem behind it.
- **Career KB points have a source but no history.** Editing a point
  overwrites its text; there is no revision list and no restore, unlike résumés,
  which snapshot every write. Bases also do not tell you "the KB changed since
  this was assembled".
- **The tracker records state but does not manage follow-through.** No next
  action, due date, reminder, status history, or snapshot of the exact artifact
  you actually submitted.
- **Import auto-approves more than you might expect.** Unchanged bullets from a
  file you wrote are approved on import; only merged or AI-generated points land
  in the review inbox. Defensible, but the result dialog does not say so.

### Operational gaps

- **A backup is two things and nothing joins them.** The database is a single
  file and `python -m app.tools.backup_db` snapshots it safely while the stack
  runs; `base_resumes/`, `applications/`, `kb_documents/`, `exports/`,
  `settings/` and `logs/` are the other half. A database snapshot alone is not a
  restore, a directory copy alone is not either, and there is still no bundle
  command or tested restore path.
- **A Career KB consolidation blocks other saves while it runs.** The database
  allows one writer at a time, and consolidation holds that slot across every
  model call it makes, so anything else trying to save — extension telemetry,
  an MCP capture, a chat turn — waits 30 seconds and then fails with "database
  is locked". It is user-started and rare; the workaround is not to use the app
  while one (or a first-boot import) is running. The few seconds a tailoring
  session spends enriching gaps behave the same way.
- **A stored ATS score cannot be exactly reproduced.** Scoring is deterministic
  given its inputs, but a stored score does not record its as-of date, which
  versions of the résumé and job description it saw, or the embedding model —
  and recency is computed against *today* — so the same document can score
  differently on a different day with nothing saying why.
- **Two moderate npm advisories** come in through the template editor's bundled
  HTML sanitiser (DOMPurify, via Monaco). CI fails only on high-severity and
  above, so they do not fail the build; whether any app-controlled HTML reaches
  that sanitiser has not been established.

### Security hardening not yet done

What is in place is in [`SECURITY.md`](SECURITY.md). None of these is reachable
from the network — they matter to the extent that something already running as
you, or a page you have open, is hostile.

- **LaTeX rendering is bounded, not isolated.** The compiler cannot read files
  outside its working folder, but it still runs with the backend's environment
  and its folders. The real fix is a throwaway, offline render worker holding no
  secrets and none of your data. Until then: do not render a template you have
  not read.
- **No CSRF token.** Requests from web pages the app does not recognise are
  refused outright, which closes the practical version of this, but there is no
  per-install token tying a change to the app that issued it.
- **Chat tools that change things are not all confirmed.** Resume edits arrive
  as approval cards; template administration does not. A prompt injection
  hidden in a job description could try to reach those tools.
- **No size, token or spend limits.** A large or malicious document can consume
  memory, CPU and model budget; nothing caps the daily spend.
- **Links between records are not verified.** Nothing checks that an
  application's job matches its proposal's job, so a mislinked record is
  possible.
- **Deleting does not always erase.** Deleting a base résumé keeps its files and
  version history; deleting a KB entity can leave its document folder behind.
  There is no purge, and no inventory of every copy.
- **Chat attachments are not tied to their chat.** An attachment can be
  referenced from a chat session other than the one it was uploaded to.
- **No Content-Security-Policy on the web app**, and detailed compiler and
  provider errors (including full file paths) can reach the browser.

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
- **No built-in job-board search or scraper.** The app captures postings you or
  your agent bring to it. An agent may find them with its own tools, within each
  site's terms — see [`docs/agentic-job-search.md`](docs/agentic-job-search.md).
- **No bulk auto-apply.** Employers now filter for machine-generated volume;
  building it would put the tool on the wrong side of the trend it exists to
  answer.
