# FilledAnswer — the answer receipt (`models/filled_answer.py`)

> Reference tier, extracted from [SYSTEM.md](../../SYSTEM.md) (§4 Core entities). The header contract there governs this file too: integrate don't append, present tense, no dates outside the ledgers, update in the same change that alters the behaviour described.

One row per page run of a job's application form. Columns: `job_id` (FK, cascades with the job),
`application_id` (nullable, `SET NULL`, linked late), `base_resume` (the slug the writer was filling for,
nullable), `channel` (`companion` | `agent`), `host` (the writer's, else the host of the job's
`source_url`), `step` (a page number or the URL path, as text), `captured_at`, and `fields`, a list of
`{question, section, required, answer, options_count, source, slot, eeo, edited_by_you}` as written
(`schemas/filled_answers.FilledField`, `extra="forbid"`; an answer is text or, for a multi-select, the list
of ticked options; a number is stored as its text) plus the server's `eeo_answered` and `version`. Rows are
appended and never pruned; the values live here and nowhere else (SYSTEM.md §6 `{#inv-filled-answers-local}`).

- **Writers.** The Companion posts one row after every fill run, loop and rule pass alike, one per
  pause-row answer that sticks, and one per edit capture (a debounced re-read after you change a field, at
  Mark applied, and as the panel leaves a page; `extension/INTERNALS.md`, "The answer receipt"). An agent
  posts one per form page with MCP `record_filled_answers`, before Next and before "Submit now?". A
  writer may name the application (it must be this job's: 404 unknown, 400 another job's).
- **Sources are a frozen vocabulary**, read by phase 4's auto-submit rule: `profile` (the autofill
  profile's personal, work_auth, eligibility, eeo, preferences, education and languages slots, and
  `derived.full_name`), `resume` (an `experience.N.*` slot or `skills`), `custom` (a saved answer,
  `custom.N`), `written` (prose `/choose` or an agent composed; it blends profile, saved answers, career
  history and persona, so prose is not split into Resume vs Career history), `inferred` (any other
  `derived.*` fact, a low-stakes or reasoned choice, anything no saved fact states), `you` (typed or
  changed by the user), `upload` (a file: `slot` is `resume` or `cover_letter`, `answer` the file name; a
  resume upload carries the application's resume `version`). On screen each is a one-word pill: Profile,
  Resume, Custom, Written, Inferred, You, Upload.
- **You, and edited by you.** A field the user changed AFTER the Companion wrote it keeps the Companion's
  source, sets `edited_by_you` and records the user's value; `guessed_screening` skips it, since you
  chose the answer. A field the policy never fills is never recorded as `you` (the receipt's list is
  `shared/policy.js` `NEVER_FILLED` plus its own `RECORD_NEVER` IDs: signatures, passwords, government,
  passport, licence and tax numbers). A field the run left open or found already filled is not recorded.
- **Latest wins.** Readers key a field by (step, section, question, occurrence), the first three case- and
  space-folded and the occurrence the field's index among same-labelled fields of its row, so two "Job
  Title" boxes both survive. Rows run oldest first and a later row replaces only the same occurrence on
  the same step; the same question on another step stays. A field keeps the place its question first had,
  and steps order by the first row that named them. Because the occurrence counts IN THE ROW, a writer
  that posts only the third "Company" would land on the first one's place, so the Companion restates every
  already-posted field still on the page with each post.
- **Linking.** Rows posted before the job has an application are unlinked; `filled_answers.link_unlinked`
  claims them when an application is NEW (`POST /api/applications/from-base`, a tailoring that inserts
  one; a rebuild keeps what is linked), when `PATCH /api/applications/{id}` marks it applied or later, and
  in `proposals.transition(..., "submitted")`. It claims the job's unlinked rows posted for that
  application's `base_resume`, and rows posted with no base only while the job has exactly one
  application; another base's rows stay unlinked. Stamps are honest: a resume upload takes the version
  the application had when the row was posted (a writer-named application gets the newest at post time),
  and none when it had no version yet.
- **EEO lifecycle.** A field is EEO when the writer says so, its slot is `eeo.*`, or its question names a
  protected characteristic (`answer_flags.EEO_RE`: gender, sex, race, ethnicity, Hispanic or Latino,
  veteran, disability, sexual orientation). At write its value is kept only while EEO consent is recorded,
  decided by `eeo_consent.withhold_unconsented` as the fill decides it (an unreadable consent keeps
  none); without consent the field keeps the question, `answer: null` and `eeo_answered`. Withdrawing
  consent (`eeo_consent.set_consent`) calls `clear_eeo_answers`, which nulls every stored EEO value in
  every row and keeps `eeo_answered`; granting consent again brings nothing back. The read asks consent
  again, so a stored value is served as null once it is withdrawn. The web tab shows EEO answers only on
  demand, per visit, under "Diversity questions (voluntary)". An agent read carries `eeo_answered`, never
  the value, consent or not (`agent_flags`; the MCP client strips it again), and no MCP path reads the GET.
- **Flags are computed at read time** (`services/answer_flags.py`) over the latest answer per question
  and the consent-gated profile catalog (`autofill_catalog.build` with no resume blocks), so a profile
  change re-flags old rows; nothing stores a flag. Four ids, warn only, each with one fixed reason line:
  - `guessed_screening`: a screening question answered `inferred` or `written`, not edited by you, not
    EEO, not read off a saved slot (a derived fact included), and not a `written` answer over 200
    characters (an essay is about something else).
  - `ticked_everything`: a list answer holding every one of more than two offered options.
  - `differs_from_profile`: the answer is not the saved value of its slot, for slots the profile itself
    answers (a list fact, `derived.today` and `derived.earliest_start_date` never compare). Text compares
    as word sets (one side's words all in the other's: "Master of Science (MS)" matches "Master of
    Science", "male" is not "female"), a phone by its last 10 digits, a date by its month. A saved Yes/No
    compares by polarity: only a negation on the question's own verb at its start ("Will you not...",
    "Are you unable...", curly apostrophes included) turns it around, so the literal same answer is the
    odd one there; any other negation cue in the asking clause ("without", "never") means no judgment.
    The asking clause is the last sentence holding a question mark, cut at its last comma.
  - `eeo_without_saved_answer`: an answered voluntary question with nothing saved for it, not an answer you
    chose; the key comes from the slot (`eeo.<key>`), else the question's words, else "anything saved".
- **A screening question** is a knock-out: a slot with the `exact` policy (not `eeo.*`, `languages.*` or
  `derived.agrees_to_terms`), or a question matching `SCREENING_RE`: authorized, sponsor, visa,
  relocate, on-site, in office, days a week or per week, in person, clearance, citizen, degree, graduate,
  enrolled, start date, available; eligible to work, right to work, work permit, permanent resident,
  green card, H-1B; over or at least 18; able or willing to commute; hybrid role, position or schedule;
  work in our office; when can you start, notice period, and "you reside". A bare "hybrid", "commute", "18"
  or "reside" is not enough. Phase 4 reads `is_screening`; its words are pinned on the real questions in
  `tests/test_answer_flags.py`.
- **Surfaces.** `POST /api/jobs/{id}/filled-answers` answers `{id, application_id, flag_count, flags}`, the
  run's flags by index into the request's `fields` (the Companion's **Check before you submit** group);
  `GET` answers the grouped receipt: per question the latest answer, by step and section, with
  `host`, `pages`, `captured_at` and `flag_count` (the job page's **What was submitted** tab, offered when
  `GET /api/jobs/{id}/detail` says `has_filled_answers`); `get_final_review` carries the job's flagged
  answers as `flags` (question, source, answer, reasons). Read-only: correcting an answer in the tab does
  not learn it.
- **The on-site knock-out** rides with the receipt: the job's pre-scan has an `on_site` check
  (`services/knockout.scan_for`, the ONE reader behind the job page, the final review and
  `/api/jobs/match`). Remote passes; an unknown work mode, or on-site with no city or state to compare,
  adds no check. On-site or hybrid where you live passes (state names and codes compare equal; a stated
  country that differs is another place; a posting listing several places counts when one is your city).
  Elsewhere a `willing_to_relocate` yes passes; otherwise a missing home city and state is
  `profile_missing`, a no is `conflict`, and an unset or free-text answer is `profile_missing`. The
  Companion's Fill body shows a conflict or missing answer as one plain line above the form.
