/* Maestro CS Companion — side panel controller.
 *
 * One store (`card`), one render loop, stages computed by ns.decisions.stageFor.
 * All backend traffic rides the SW's `api` message (the single fetch site);
 * all page work rides panel_prepare / panel_frame0 / page_broadcast with the
 * bound tabId. A panel is an extension page, so it CAN fetch and CAN read
 * chrome.storage directly — which is exactly why both rules are written down
 * rather than left to the environment (sw.js says the same from its side).
 *
 * WHAT THIS FILE PUBLISHES: ns.panel = { railModel, deepLink, stageAction,
 * resetPageFacts, applyMatch, previewFrom, ingestBodyFrom, evidenceFrom,
 * sessionEntryFrom, actionStore } — the parts that decide something without a
 * document. They are
 * on the namespace for the same reason shared/decisions.js's are: it is how the
 * node harness runs the real file (`loadModules`) rather than a slice of its
 * text, so a module that throws while wiring itself fails a test instead of
 * opening blank.
 *
 * `actionStore` is on that list for the same reason `resetPageFacts` is, and it
 * is worth saying so because it looks like an internal: the door it hands out
 * is the ONE enforced safety property of the actions seam — `write` refuses a
 * key the store does not have — and a property nothing can reach is a property
 * nothing can pin. Publishing the FACTORY rather than the store keeps `card`
 * private either way.
 *
 * WHAT IT READS OFF THE NAMESPACE: `ns.decisions` (shared/decisions.js),
 * `ns.panelStages` (panel/stages.js) and `ns.panelActions` (panel/actions.js).
 * All three are loaded before this file by panel.html's script tags, in that
 * order, and all three are read at load — so a missing tag is a panel that
 * fails loudly rather than one that renders a rail with nothing under its
 * active row, or one whose every primary throws on the first click.
 *
 * BOTH SPLITS HAVE HAPPENED, and this is what they left. The threshold was set
 * in advance — a FOURTH stage body, or roughly 1800 lines, whichever came
 * first — and the line clause fired twice: on the way into the Resume body
 * (Task 9), and again on the way into the Fill stage (Task 12). The stage
 * bodies live under `panel/stages/` and the actions under `panel/actions/`,
 * each family gathered by a tiny roster (`panel/stages.js`,
 * `panel/actions.js`) that publishes the one namespace entry this file reads;
 * this file keeps the store, the loaders, the generation guard, the render
 * scaffolding and the tab binding.
 *
 * WHERE THAT LEAVES THE NUMBERS, stated rather than implied, because a
 * threshold nobody can measure against is not one:
 *
 *   panel.js 3283 · panel/actions/ 1722 (9 files) + a 146-line roster ·
 *   panel/stages/ 1237 (5 files) + a 105-line roster · shared/choose.js 186
 *
 * (Re-counted with the posting re-ask, which is the second change since Task 15
 * to add to this file rather than move things out of it — the loaders live
 * here, and a bounded re-ask plus its injection rung is loader work. Before
 * that, the reopenable done row, which was the first — and the numbers had
 * drifted by ~200 lines before that one re-counted them, which is exactly the
 * failure the paragraph below names. Refreshed originally at Task 15, which is where
 * both of those directories came from:
 * each file tripped its OWN trigger at Task 14 and both cuts were deferred,
 * together, to that task's opening commit — their headers carry the history. A
 * ledger nobody updates is worse than none: it reads as a measurement and is a
 * memory, and the next author budgets against it.)
 *
 * SO THE 1800-LINE CLAUSE IS SPENT. Two cuts took ~640 lines out of this file
 * and Task 12's own Fill wiring put it back over the number, which means the
 * line count has stopped being a useful trigger here: it fires on a file that
 * has just been split twice and has no third category waiting to leave. What
 * is left is store, loaders, guard, render scaffolding and binding — one
 * subject. R-C has since been and gone WITHOUT shrinking it — the widget
 * retirement deleted a sibling file, not half of this one's job — so this
 * paragraph's old "until R-C" caveat is spent too, and the reading stands on
 * its own: this file is as small as its job allows.
 *
 * THE LIVE TRIGGER IS THEREFORE THE OTHER CLAUSE, and one named cut. A FIFTH
 * stage body is `stages.js`'s problem now (its header carries its own
 * threshold). For THIS file the trigger is the free cut that has been standing
 * since Task 9 — `previewFrom`/`ingestBodyFrom` into a `panel/posting.js`.
 *
 * RECONSIDERED AT R-C AND DECLINED AGAIN, which is worth recording because
 * R-C's storage pass was the arrival this note was waiting for. It was not the
 * trigger: the sweep is four key names and one boot function, it touches
 * neither `previewFrom` nor `ingestBodyFrom`, and it is not posting-shaped at
 * all. The original reasoning is unchanged — the cut moves 75 lines, leaves
 * the caller behind, and buys no boundary that is not already a function call.
 * TAKE IT when a second POSTING-shaped concern actually arrives, not to make a
 * number smaller.
 *
 * NEITHER SEAM WAS "extract the functions": every body and every action reads
 * `card` and writes `card`, so a split that published the store would have
 * traded one long file for a mutable global that several files share. The store
 * stays module-private HERE, and what crosses is different in each direction
 * because the two categories are different shapes:
 *
 * - a BODY renders once and returns, so it gets a per-render snapshot of the
 *   facts it may read plus the callbacks it may fire — see `stageContext`;
 * - an ACTION spans awaits and writes as it goes, so it gets a HANDLE with one
 *   write door on it — see `actionStore`, which carries the reasoning for why
 *   the bodies' shape does not stretch to cover it.
 *
 * Both are enforced by scope rather than by agreement, which is the only kind
 * of enforcement this arrangement has.
 *
 * WHAT RENDERS WHAT: three regions are constant chrome — header (mark + the
 * one deep link), identity (title / company / chip / ATS rings), footer
 * (status + exactly one primary CTA) — and the rail is the dynamic one. The
 * active stage is COMPUTED from the store, never from what the user last
 * clicked (design: "stage inference, not stage navigation").
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const { stageFor, rankBaseResumes, restorableSession, sessionTenant } = ns.decisions;

  // `chrome.storage.local`. ONE key, holding the bridge entry that carries a
  // user's pick from the page it was made on to the next page of the same
  // wizard — which is a different page LOAD, and therefore a different panel
  // boot with an empty store.
  //
  // THE NAME IS HISTORICAL AND STAYS THAT WAY. `widget.session` is the key the
  // floating card wrote, back when two surfaces read one entry so that a pick
  // in either showed up in the other. R-C deleted the card; this panel is the
  // only reader and the only writer. The string is not renamed because renaming
  // it would silently drop every live entry — a user mid-wizard would find
  // their pick gone, which is exactly the failure the key exists to prevent —
  // and one stale word in a comment is cheaper than that. (`widget.dock`,
  // `widget.hiddenOrigins` and `widget.hiddenGlobally` were the card's
  // placement and its two levels of dismissal. Nothing writes those now; see
  // `ORPHAN_KEYS` below, which sweeps them.)
  //
  // ONE KEY RATHER THAN TWO, which is worth keeping written down because the
  // second one existed and the reason it went is a rule about this store.
  // Task 8 parked application-less entries on a separate key, and with two keys
  // populated `restoreSession` preferred by KEY — so an older entry beat a
  // fresher one for the whole TTL. One key cannot shadow itself, so the
  // recency tie-break that split needed is not written at all. `panel.pick` is
  // its remains, swept below.
  //
  // WHAT MAKES ONE KEY SAFE is the `if (entry.applicationId)` guard in
  // `restoreSession`. A pick made at the Score stage usually has NO application
  // behind it — that is what the Score stage IS, and "use base as-is" is the
  // same shape — and restoring `{id: undefined}` as an application, then
  // forcing `match = "exact"`, is a surface claiming an application that does
  // not exist on every page load of that tenant. That guard is not optional
  // decoration on this key; it is the condition of sharing it.
  const KEY = { session: "widget.session" };

  // EVERY KEY THIS EXTENSION HAS EVER WRITTEN TO `chrome.storage.local` AND NO
  // LONGER READS. R-C's storage pass, and the documented set: if it is not
  // `KEY.session` and it is not here, nothing in this extension has ever put it
  // in local storage.
  //
  // - `panel.pick` is Task 8's second session key. It can hold one bare base
  //   pick, written by a panel built between Task 8 and the collapse back to
  //   one key.
  // - the three `widget.*` are the floating card's dock placement and its two
  //   levels of dismissal. R-C deleted the card; these are what it left behind
  //   in every user's profile.
  //
  // SWEPT AT BOOT, WHICH IS THE FIX AND NOT JUST THE MOVE. The `panel.pick`
  // sweep used to ride `restoreSession`, and that is only reached when the
  // backend did NOT name an application for the page — so a user whose pages
  // always match never ran it and kept their orphan forever. The note there
  // said so, and deferred the fix to "R-C's own storage pass". This is it.
  // A boot is once per panel OPEN, not once per page load, so the read this
  // costs is nothing like the per-load write that objection was about.
  const ORPHAN_KEYS = [
    "panel.pick",
    "widget.dock",
    "widget.hiddenOrigins",
    "widget.hiddenGlobally",
  ];

  // How long a hand-picked application outlives the page that picked it. An
  // ATS wizard is six page loads and a user can walk away mid-way, so the
  // window has to be long enough to survive the walk and short enough that
  // tomorrow's visit to the same tenant is not answered with yesterday's pick.
  // (Two surfaces once read this entry and the note here said the two TTLs had
  // to stay equal. One does now, so the number is simply this one's.)
  const SESSION_TTL_MS = 30 * 60 * 1000;

  // Rail order, and the numbers the user sees. The keys are `stageFor`'s, so a
  // stage renamed there fails to render rather than rendering blank.
  const STAGES = [
    { key: "job", name: "Job" },
    { key: "score", name: "Score" },
    { key: "resume", name: "Resume" },
    { key: "fill", name: "Fill" },
    { key: "track", name: "Track" },
  ];

  /** The DONE rows a user may reopen, and the whole of that list.
   *
   * THE CASE IT IS FOR is a Workday wizard: My Information → My Experience →
   * … → Review. The first page's fill ticks `done.fill`, the rail moves on, and
   * four more pages of form sit in front of the user with no way back to Start
   * fill.
   *
   * AND IT SURVIVES THE PAGE LOADS, which is the part worth getting right,
   * because a wizard step is usually a real navigation rather than a route
   * change behind one url. `resetPageFacts` clears `touched` on every one of
   * them — so the tick would fall off by itself and the rail would re-offer the
   * fill — except that `startFill` calls `remember()` exactly so it does not:
   * the session entry carries `touched` and `restoreSession` puts it back on
   * the next load (see `restoreSession`, and `startFill`'s own note at
   * actions/fill.js). That bridge is deliberate — being asked to re-fill a form
   * the extension has already finished is the failure it was written for — and
   * it is precisely what makes the ticked row the state a user gets stranded
   * in. So the door is the exit from a state the session bridge is keeping
   * true, not from a store that forgot to reset.
   *
   * Score and Resume are the same shape one step earlier — a base picked in
   * haste, a tailor worth re-running — and reopening either is how a user takes
   * that back without the panel guessing that they want to.
   *
   * JOB IS ON IT ONLY FOR A CLAIM. A pick the user made is theirs to
   * withdraw, so a done Job row is a door when `claimed === true`. A backend
   * exact-match is the page being that posting; the web app is where a wrong
   * JD gets fixed, and that Job row stays a wall. Re-offering "Add job" under
   * a backend-matched row that reads "✓ in library" is still the panel
   * offering to add a job it has just said is added — that case gets no door.
   *
   * TRACK IS NOT ON IT EITHER, for a duller reason: Track is never done while
   * the user is looking at it (`done.track` and `stage === "track"` are the
   * same state, and active outranks done), so a reopen control there would be
   * one nothing can ever render.
   *
   * AND A SKIPPED ROW CAN BE A DOOR TOO, which is the list's other half and
   * why this function is not simply `REOPENABLE.includes`. A done row is a
   * door because the work can be redone; a SKIPPED row is a door only when the
   * skip is a claim the user made — "use base as-is" — because then there is
   * something to withdraw. `stageFor`'s `choiceSkipped` is the provenance and
   * `railModel` carries it onto the row as `skipChoice`; a row skipped by the
   * path's own arithmetic (Score under the shortcut, Job on an unmatched apply
   * url) stays a wall, exactly as a backend-matched Job row does. Reported
   * live on an Itron wizard: the user armed the base, the Resume row read
   * "Skipped — using base as-is", and the only way back to the tailoring fork
   * was to unbind the whole page.
   */
  const REOPENABLE = ["score", "resume", "fill"];

  function isReopenable(row) {
    if (row.state === "skipped") return row.skipChoice === true;
    if (row.state !== "done") return false;
    if (row.key === "job") return card.claimed === true;
    return REOPENABLE.includes(row.key);
  }

  /** The two stable ids the rail builds, and they are stable for two different
   * reasons that happen to want the same thing. `aria-controls` needs an
   * ADDRESS for the region a header discloses, and the focus restore around
   * every rail rebuild needs a HANDLE for the control the user was in — see
   * `withPlaceKept`. `stages/resume.js`'s `TAILOR_OPTIONS_ID` is the same
   * pattern one layer down. */
  const REVISIT_ID = (key) => `stg-open-${key}`;
  const STAGE_BODY_ID = (key) => `stg-body-${key}`;

  /** The ONE primary action per stage — the design's "one primary at a time,
   * always in the footer". The map is here rather than inside the footer
   * renderer because it is the whole of the answer: a stage with no entry has
   * no primary, and adding a second button to this surface has to be a
   * decision someone makes on purpose.
   *
   * ONE OF THREE MAPS keyed on the same stage strings, and it is worth knowing
   * all three when you touch any of them: this one is the LABEL, `STAGE_BODIES`
   * (now `panel/stages/`, gathered by `panel/stages.js`) is what renders under
   * the OPEN row — the active one, or a done one the user reopened — and
   * `STAGE_RUN` is what the button actually does. All three are read for the
   * same key, which is what makes a reopened body's primary its own rather than
   * the inferred stage's (`renderFoot`). A stage may have any subset —
   * Fill has all three, and Track has a body with NO label and NO run (the
   * header link carries its route, the footer segment its one write) — which
   * is exactly why they are three maps and not one table with holes in it.
   *
   * Named STAGE_LABELS since the split, which is when the header parked the
   * rename for: it was the odd one out among three maps that all key on the
   * stage, and a rename costs every reference to it — worth paying once, with
   * the move that took a sibling into its own file. */
  const STAGE_LABELS = {
    job: "Add job",
    score: "Score all bases",
    // The words the stage body's own Quick limb uses, and deliberately the
    // same words: they run one function, and two labels for one behaviour is
    // how a user comes to believe there are two.
    resume: "Quick tailor",
    // Was "Autofill this form" while this primary was inert. The Fill body's
    // own limb reads the same two words for the Resume stage's reason — one
    // function, one label — and they are deliberately short, because this fill
    // is not only a form fill: the mode control above the button is what says
    // which pass is about to run.
    fill: "Start fill",
    // AND NO `track`, which is a decision rather than an omission — this map is
    // documented above as one a stage may be absent from, and Track is the
    // stage that is.
    //
    // The Track stage's way onward is a LINK, and it is already in the header:
    // `deepLink` names the most specific thing we know and labels itself
    // accordingly ("Open application ↗" when there is one, "Open in Maestro CS
    // ↗" when there is not). A footer primary here could not do that — this map
    // holds constant strings — so it would read "Open application" on the one
    // state that has no application, which is exactly the state whose body says
    // nothing has been written down. A button contradicting the sentence six
    // pixels above it is worse than no button.
    //
    // It was "Open application" behind `comingSoon` until Round B, which was
    // honest while a next change was coming and became a false promise the
    // moment this was the last stage. The footer is not empty on this stage:
    // the status segment is its control, permanently, which is design §Footer's
    // whole point.
  };

  // Each rail state in words. "not yet" rather than "locked": nothing on this
  // rail is withheld from the user — a later stage is simply a later stage,
  // and "locked" would describe a product that gates it.
  const STATE_LABELS = {
    active: "current step",
    done: "done",
    skipped: "skipped",
    locked: "not yet",
  };

  // `skipped` NAMES the stages the current path does not require, and this is
  // the copy that says so. It is never a checkmark: "we did not need to" and
  // "we did it" are different claims (decisions.js's rule, rendered).
  const SKIPPED_SUMMARY = "Skipped — using base as-is";

  // The QnA drawer's closed, empty state. FROZEN for `EMPTY_PREVIEW`'s reason:
  // it is the store's initial value and the value every page change resets to,
  // so it is one object several loads share — and a stray write to it would be
  // a default that quietly became the last question anyone typed. Every writer
  // below spreads it into a new object rather than touching it.
  const EMPTY_QNA = Object.freeze(
    { open: false, question: "", answered: null, answer: null, copied: false });

  /** Everything the panel renders. Nothing here is derived: `stageFor` derives
   * the stage from these facts on every render, and no field below caches that
   * answer — a second home for "which stage are we in" is how a surface ends
   * up showing a tick beside a button that asks for the same thing.
   *
   * Named `card`, which is a name inherited from the floating card's store
   * and kept after R-C deleted it. It is a misnomer now and renaming it is a
   * ~200-site edit across nine files touching nothing a user can observe —
   * a change with a real chance of a typo and no chance of a benefit. Read it
   * as "the facts this panel is currently rendering". */
  const card = {
    // The tab this panel is bound to. The binding is the panel's OWN guard:
    // `fanoutTab` verifies who may name a tab, never which, because "the tab
    // the user is looking at" is not a fact a service worker can reach.
    tabId: null,
    url: null,

    settings: null,     // {backendUrl, appUrl, …} from the SW; null until asked
    match: null,        // the backend's verdict about this url; null ≠ "none"
    job: null,          // {id, company, title}
    // {id, status} — and that IS the shape this surface reads. `restoreSession`
    // also copies `job_company`/`job_title` off a session entry because the
    // entry carries them; nothing here reads them, and no other writer adds
    // them (`quickTailor` does not, where `fastTailor` does).
    application: null,
    /** Did the USER bind this page to an application by hand?
     *
     * A pick is a claim; a backend exact-match is not. The Job row is a door
     * back only for a claim — un-pick / re-pick — because a binding the
     * backend made from the page's own URL is the page being that posting,
     * and the web app is where a wrong JD gets fixed.
     *
     * WRITTEN by `pickApplication` and by `restoreSession` when it arms from
     * a session entry (a bridge-restored arming is the same claim, carried
     * forward). `applyMatch` writes false: the backend named this page.
     * Persisted on the session entry so page 2 of a wizard still knows;
     * never a wire field.
     */
    claimed: false,
    pdfReady: false,
    /** What the application has to show for itself: `{pdfName, appliedOn}` or
     * null when it has nothing yet.
     *
     * `evidenceFrom`'s own return, from the ONE read that knows — the
     * application detail — and re-read off the PATCH that marks it applied.
     * Null is "nothing to show", which the Track body renders as no line at
     * all rather than as an empty one: a draft with no rendered PDF has no
     * evidence, and saying so with a dash would be a row reporting its own
     * emptiness as a fact.
     *
     * SEPARATE FROM `pdfReady`, which is the same source read for a different
     * question. That one is a STAGE input (`stageFor` reads it to decide
     * Resume-is-done) and is a boolean because that is all the decision needs;
     * this is what the Track stage SHOWS, and it needs the name and the date.
     * One field doing both would turn a rendering change into a stage change.
     */
    evidence: null,
    touched: false,     // this extension filled or attached HERE, this session
    hasForm: false,
    /** How many upload boxes on this page a résumé could go into.
     *
     * The page's own count, from the SAME detect pass that answers `hasForm`
     * (`detect_page`, content/agent.js) — the panel runs in no page and cannot
     * look for itself. `0` is both "none here" and "we could not ask", exactly
     * as `hasForm: false` is, and it means the same thing to the one reader
     * this has: no attach is offered.
     *
     * THE OFFER IS A THREE-WAY DECISION and this is the whole of its input.
     * One box is an attach. Zero is no affordance at all. MORE than one is a
     * refusal with a sentence rather than a guess: the panel cannot tell a
     * résumé box from a cover-letter box from a transcript box, and putting the
     * résumé in the wrong one is worse than not offering — the user would have
     * to notice, on a page that looks like it worked.
     *
     * FRAME 0's count, because `panel_frame0` is the only door this panel has
     * to a detect. A Greenhouse form in a subframe reports zero here, so the
     * offer does not appear there; the attach fan-out would still reach it.
     * That is the conservative direction and it is stated rather than hidden.
     */
    fileInputs: 0,
    /** What this panel put ON this page, or null. `{filename, count}`.
     *
     * PAGE-SHAPED like `fill` and cleared by `resetPageFacts` for the same
     * reason: an attach is a thing that happened to one document, and a line
     * saying "Attached tailored-resume.pdf" carried to the next tab would be a
     * claim about a page nothing was ever written to.
     *
     * The COUNT is the engine's readback and not the number of frames asked —
     * `attachResumePdf` re-reads `input.files` after the assignment, so this is
     * how many boxes really hold the file.
     */
    attached: null,
    baseSlug: null,
    baseSelected: false,
    baseArmed: false,   // the base-resume shortcut, restored from the session
    resumes: null,      // the base-resume library; null = not asked, [] = none
    /** Recent draft applications, for the Job-stage picker.
     *
     * TAB-INDEPENDENT, like `resumes`, and for the same reason: the library
     * of drafts is not a fact about a posting. `resetPageFacts` keeps it so a
     * tab switch does not re-fetch. `null` is "not asked", `[]` is none.
     * Loaded lazily — only when the Job stage is active, the page has a form,
     * and nothing has matched — because a read on every tab is the always-on
     * cost `loadHasForm` refuses to pay for detection.
     */
    applications: null,
    scores: null,       // latest_scores rows; null = not asked, [] = none
    busy: null,         // the stage key of the action currently running, or null
    note: null,         // {text, error} — the last thing that happened HERE
    /** The posting on the page, as the user may still edit it, or null until
     * we have asked.
     *
     * IN THE STORE, and this is the whole of Task 6's warning acted on. The
     * render loop rebuilds every region from `card`, so an input's in-DOM value
     * is not state this surface can keep: a score read landing mid-keystroke
     * REPLACES the element and the characters go with it. The three editable
     * fields are therefore written here on every `input` event and rendered
     * back from here, which makes an unrelated repaint cost nothing.
     *
     * FIVE keys, three of them editable. `text` is the job description itself —
     * not editable in a three-input preview, and it is the entire substance of
     * the ingest, so it has to survive from the extraction to the POST.
     * `source` is where the extraction found it, which is the sub note's line.
     *
     * `null` is "not asked", and nothing more than that since the re-ask: a
     * non-null preview may be the page's first answer, a better one that landed
     * a few seconds later, or the user's own typing, and WHICH of those it is
     * is `previewTyped`'s question rather than this field's. It used to double
     * as the latch, and that is precisely the bug — see below.
     */
    preview: null,
    /** Has the USER typed into the preview?
     *
     * The discriminator the re-ask needed, and the reason it is a field rather
     * than an inference: `card.preview !== null` used to stand in for it, which
     * conflated "a person put characters here" with "extraction has answered".
     * The two came apart the moment extraction was allowed to answer twice —
     * and they had already come apart live, because an extraction that answered
     * EMPTY on a page that had not rendered yet then locked that emptiness in
     * for as long as the panel stayed bound (itron.wd5, 2026-08-19: a full JD
     * on screen under three empty boxes, with Add job refusing to save it).
     *
     * WRITTEN by `editPreview` and by nothing else, so it means exactly one
     * thing. NEVER cleared while the page stands: a user who typed a title and
     * then deleted it has still made this preview theirs, and a re-ask that
     * refilled it would be arguing with a deliberate blank.
     *
     * PAGE-SHAPED, so `resetPageFacts` clears it — left standing it would be
     * the same bug turned over, with one page's typing refusing the NEXT page's
     * posting.
     */
    previewTyped: false,
    /** Have we injected the content scripts into this page ourselves?
     *
     * The whole of the once-per-page bound on `preparePage`, and it is a fact
     * about THIS page — `resetPageFacts` clears it — because the injection is.
     * A flag that survived the tab would leave the next page unprepared with
     * the panel believing it had been done.
     *
     * `false` is "we have not", not "the scripts are not there": the ordinary
     * page loaded since the extension started already has them and is never
     * prepared at all. This says only whether the one shot has been spent.
     */
    prepared: false,
    /** Has the user opened the Resume stage's second fork level?
     *
     * IN THE STORE for the reason every other rendered fact is: the render
     * loop rebuilds the rail from `card` on every repaint, so a disclosure
     * kept on the element would close itself the moment a score read landed.
     * It is a fact about this PAGE's fork — `resetPageFacts` clears it — and
     * not a preference: the next posting's Resume stage opens closed, asking
     * the same question from the top rather than resuming a half-made choice
     * about a different job.
     */
    tailorOpen: false,
    /** Which row the user has REOPENED, or `null` when the rail is showing the
     * stage the data infers. `{row, over}` — the stage key whose body is open,
     * and the INFERRED stage it was opened over.
     *
     * Not only a DONE row, which is what this said while done rows were the
     * only doors: a row SKIPPED by the user's own claim reopens too (the
     * base-as-is Resume row). `isReopenable` is the whole list and `openRow`
     * asks it rather than re-stating any part of it.
     *
     * THE ONLY VIEW FIELD IN THIS STORE, and the reason it can be one without
     * breaking "stages advance by data, never clicks": it changes which body
     * is SHOWN and nothing else. `stageFor` never reads it (`cardFacts` does
     * not carry it), no tick moves because of it, and no fact about the
     * application is written by opening or closing a row. `tailorOpen` above
     * is its nearest neighbour — a disclosure kept in the store because the
     * render loop rebuilds the rail from `card` on every repaint — and the
     * difference is only which region it opens.
     *
     * DATA WINS, which is what the second key is for. `over` is the stage the
     * row was opened over, so `openRow` can tell "the rail is where it was" from
     * "the rail has moved on" and drop the view when it has: a re-pick that
     * sends the journey back to Score, a tailor that lands a PDF, a page change
     * that resets the facts. View state must never outlive the facts it was
     * opened over. One field rather than two because the pair is meaningless
     * apart — a `revisit` with no `over` cannot yield, and an `over` with no
     * `revisit` is a fact about nothing — and two keys would be two things that
     * have to be cleared together, forever, by every writer.
     *
     * PAGE-SHAPED, so `resetPageFacts` clears it: the row was reopened over one
     * posting's facts, and a body carried to the next tab would be the previous
     * job's Fill report under the new job's rail.
     *
     * NEVER PERSISTED. `sessionEntryFrom` does not carry it and nothing sends
     * it anywhere: which body a user is looking at is not a fact the other
     * surface, or the backend, has any business restoring.
     */
    revisit: null,
    /** Which pass the Fill stage runs: `"assist"` (rules, then /choose for the
     * remainder) or `"rules"` (the deterministic pass alone). The runner's
     * `aiAssist` is `fillMode === "assist"` and nothing else reads it.
     *
     * A PREFERENCE, not a page fact, which is why it survives
     * `resetPageFacts`: the user who wants nothing sent to a model wants that
     * on every posting, not until their next tab switch. It lives in
     * `chrome.storage.sync` under `fillMode` so it follows the profile, and it
     * arrives here through `read_settings` at boot — the SW owns the default,
     * like every other setting, because a second copy is the one that drifts.
     */
    fillMode: "assist",
    /** The RULE pass's reconciliation, or null until one has run.
     *
     * `reconcileFill`'s own return, unchanged (`shared/decisions.js`) — the
     * counts the progress rows print come out of its table rather than out of a
     * second one written here. Null is "no fill has run on this page", which is
     * what the Fill body renders as an offer rather than as a report of zero.
     */
    fill: null,
    /** The backend's standing EEO consent, as `/api/autofill/context` reported
     * it on the last run. `{enabled, consent_forms}` or null.
     *
     * READ, never decided: disclosing protected characteristics is the
     * backend's record to hold, and a local toggle that could turn it on is
     * exactly what design §R1 forbids. The Voluntary-disclosures row says
     * "skipped — EEO off" from THIS, so a user who has never granted consent
     * sees why nothing was written rather than a silence.
     */
    eeoConsent: null,
    /** The fields the run could not answer, and the questions that want a
     * written one. Both are the runner's own arrays, kept apart because they
     * are answered on different paths — residue is a control on the page,
     * essays go to `/api/qa` — and shown together because the user's question
     * is "what is still open".
     */
    residue: null,
    essays: null,
    /** The per-qid outcomes of the run's ONE `guided_write`. The Application
     * questions row counts what was written from this and the residue, which
     * is the run's own reconciliation rather than a second reading of the
     * engine's outcome vocabulary.
     */
    writeResults: null,
    /** The pause rows' drafts, by qid: `{[qid]: {text, learn}}`.
     *
     * IN THE STORE for `preview`'s reason, and the reason is sharper here
     * because there are several of them: the render loop rebuilds the rail
     * from `card` on every repaint, so an input holding its own characters
     * loses them the moment ANY other row submits, a note lands, or a load
     * returns. Written on every `input`/`change` event without rendering, and
     * read back by the body.
     *
     * `{}` rather than null, because "no draft" and "not asked" are the same
     * thing here: a row with no entry renders an empty box (or its known
     * value), which is exactly what a row nobody has typed into should show.
     * A submitted row's entry is dropped with the row.
     *
     * PAGE-SHAPED, so `resetPageFacts` clears it: a qid is a per-frame token
     * stamped by the collect that produced it, so a draft carried to the next
     * tab addresses a control that does not exist.
     */
    answers: {},
    /** The QnA drawer: the composer at the foot of the Fill stage.
     *
     * `{open, question, answered, answer, copied}`, and every field is here for
     * the reason `preview` and `answers` are — the render loop rebuilds the rail
     * from `card` on every repaint, so a textarea holding its own characters
     * loses them the moment a note lands or another row submits.
     *
     * `answered` IS THE PAIR'S OTHER HALF, and it is what keeps a standing
     * answer honest while the box above it is being retyped. It is the question
     * this answer was given for; the drawer prints it beside the text. Without
     * it the alternatives were both bad: clear the answer on every keystroke
     * (a render mid-typing, which costs the caret this loop already struggles
     * to keep) or leave a paragraph about the last question sitting under a new
     * one, unlabelled — the confident wrong thing this surface keeps refusing
     * to say.
     *
     * `copied` is the Copy button's own state and nothing else: it says what
     * the press DID, in the control the user pressed, rather than spending the
     * panel's one note slot on it. It is cleared by anything that replaces the
     * answer, so it can never describe a different paragraph than the one on
     * screen.
     *
     * PAGE-SHAPED, so `resetPageFacts` clears it: the question is about the
     * posting in front of the user and the answer is grounded in that
     * application. A draft carried to the next tab would be a paragraph about a
     * job the user has left.
     */
    qna: EMPTY_QNA,
    // A fault in the panel's own plumbing rather than a fact about a page. It
    // survives `resetPageFacts`, which `note` deliberately does not — a broken
    // panel is broken on every tab, and a user who saw the sentence once and
    // never again learns nothing from it.
    //
    // NARROWER TWICE, and worth saying so, because what is left is now one
    // thing. Task 6 gave the unreachable-backend sentence to `applyMatch`,
    // which writes it as a page NOTE on every tab. The base-as-is round then
    // took the settings ask away too: a `read_settings` that answers nothing
    // boots the panel on defaults with a `console.warn` (see `readSettings`),
    // because the message it used to print here was the wire's words for a
    // failure the user can neither read nor act on.
    //
    // WHAT REMAINS is a throw out of `boot()` — in practice `bindActiveTab`,
    // which is what binds this panel to a tab at all. A panel that never bound
    // shows a rail nothing will ever move, and nothing else in this file
    // narrates that. One tenant is why the slot still falls back rather than
    // showing only the note; it is not a reason to give it new ones.
    fault: null,        // {text, error}
  };

  /** Everything above that is a claim about the PAGE, forgotten when the page
   * changes. Called at the top of `onTab`, before anything is loaded.
   *
   * The render loop's full rebuild protects the DOM, not the store: a region
   * rebuilt from a fact that belongs to the tab you just left is still the
   * previous job's title, chip and rings presented as facts about the new
   * page — the most confident wrong thing this surface could say. It is not
   * theoretical now that the loads are real: a round trip that fails would
   * otherwise leave EVERYTHING from the previous page in place, and this is
   * what makes that a blank panel instead of a confident lie. (`applyMatch`
   * clears the same four facts again when the ask itself fails — belt and
   * braces on purpose, because the two run at different moments: this one
   * before the load, that one when the load comes back empty-handed.)
   *
   * `settings`, `tabId` and `url` survive: none of them is about the posting.
   * `resumes` survives too — the base-resume library is not a fact about a
   * page, and re-fetching it on every tab switch would be a request per glance.
   * So does `applications`, the recent-drafts list the Job picker reads, for
   * the same reason. So does `fault`, which is about this panel rather than
   * about any page.
   *
   * Takes the store rather than closing over it, the shape Task 6's
   * `applyMatch(result, card)` uses for the same reason: WHICH keys a page
   * change clears is a list, and a list is worth handing a test whole.
   */
  function resetPageFacts(store) {
    store.match = null;
    store.job = null;
    store.application = null;
    store.claimed = false;
    store.pdfReady = false;
    // The evidence with the application it belongs to: a PDF name and an
    // applied date carried to the next tab would be one employer's receipt
    // shown under another employer's posting.
    store.evidence = null;
    store.touched = false;
    store.hasForm = false;
    // Both halves of the attach, and both for `hasForm`'s reason: how many
    // upload boxes a page has is a fact about that page, and what we put in one
    // of them is a claim about it. Carried to the next tab, the first would
    // offer an attach on a page with no box and the second would show one
    // employer's filename under another employer's posting.
    store.fileInputs = 0;
    store.attached = null;
    store.baseSlug = null;
    store.baseSelected = false;
    store.baseArmed = false;
    store.scores = null;
    // The fork the user opened belonged to the posting they opened it on.
    store.tailorOpen = false;
    // And so did the done row they reopened. Every fact the reopened body
    // renders is cleared by the lines around this one, so a `revisit` that
    // survived would hold open a Fill report about a form the user has left —
    // and it would be holding it open over a rail that has just reset to Job,
    // which is the view outliving the facts it was opened over.
    store.revisit = null;
    // Everything the Fill stage learned, and every word of it is about ONE
    // page: which fields were filled, which are still open, and what the
    // backend said about EEO consent at the moment that run asked. Carrying
    // any of it to the next tab would report a Workday form's residue over a
    // Greenhouse posting. `fillMode` is NOT here — it is the user's standing
    // choice about how to fill, not a fact about what was filled.
    store.fill = null;
    store.eeoConsent = null;
    store.residue = null;
    store.essays = null;
    store.writeResults = null;
    // The half-typed answers with them: a qid is a token the collect stamped
    // into THAT page's DOM, so a draft that outlived its page names a control
    // nothing can find.
    store.answers = {};
    // The composer too, both halves. The question was asked about this posting
    // and the answer was grounded in this application, so a drawer that
    // survived the tab would offer a paragraph about a job the user has left —
    // ready to be copied into a different employer's form, which is the worst
    // version of that mistake. Closed as well as emptied: an open drawer on the
    // next page would be this panel asking a question nobody typed.
    store.qna = EMPTY_QNA;
    // Cleared HERE is what lets a stale action simply RETURN without unwinding
    // anything: `generation` is bumped in `onTab` immediately after this runs,
    // so by the time an in-flight `addJob` finds its token stale, its `busy`
    // has already been cleared by the page change that made it stale. Every
    // action gets that for free — `scoreAllBases` inherited it whole — and it
    // is only true while these two lines stay adjacent and in this order.
    store.busy = null;
    store.note = null;
    // The preview is the most page-shaped fact of all — it is READ OFF the
    // page — so carrying it to the next tab would offer to save one posting
    // under another one's url.
    store.preview = null;
    // And the flag that protects it, for the same reason read the other way
    // round: it says a person typed on THIS page, so carrying it would make the
    // next page's extraction land on a preview it is not allowed to write —
    // three empty boxes over a posting, permanently.
    store.previewTyped = false;
    // The injection is about one tab's frames, so the permission to make one is
    // too: carried across, the next page would be treated as already prepared
    // and the one shot would have been spent on a page the user has left.
    store.prepared = false;
  }

  // ---------- talking to the service worker ----------

  /** Every message the panel sends. Errors travel as data across the message
   * boundary (`{ok, error}`), so this is where they become exceptions again.
   *
   * `status` COMES BACK WITH THEM, and it is the one field on the failure
   * envelope that is not prose. The SW's `api()` hangs the HTTP status on the
   * Error it throws and its router copies it onto the reply (an Error itself
   * does not survive the boundary); here it goes back onto an Error, so a
   * caller's `catch` sees the same shape it would have seen from a direct
   * `fetch`. WHY THE PANEL NEEDS IT: "this application no longer exists" and
   * "the backend is unreachable" are opposite instructions — the first says
   * forget the binding, the second says keep it and wait — and by the time a
   * failure reaches here the only thing telling them apart is 404 versus a
   * status that never existed. Matching on the sentence instead would be
   * matching on text the backend is free to rewrite.
   *
   * NOT SET when the far side sent none, deliberately: a message that never
   * reached the SW, a `fetch` that rejected, a handler that threw for its own
   * reasons. `undefined` there is "we do not know", which is exactly what the
   * bridge's offline tolerance is built on. */
  async function ask(type, payload = {}) {
    const reply = await chrome.runtime.sendMessage({ type, ...payload });
    if (reply?.ok) return reply.data;
    const err = new Error(reply?.error ?? `no answer to ${type}`);
    if (Number.isInteger(reply?.status)) err.status = reply.status;
    throw err;
  }

  /** Every backend read, through the service worker's ONE fetch site.
   *
   * A panel is an extension page, so it could call `fetch` itself and the
   * requests would even work. It does not, and this line is the whole of why
   * not: the backend URL, its default, the path allow-list (`assertBackendPath`)
   * and the error shape all live in sw.js, and a second caller would be a
   * second copy of every one of them — the copy that drifts while both still
   * look right. */
  const api = (path, init) => ask("api", { path, init });

  /** The shared store, and the one liveness check this document does NOT need.
   *
   * A content script has to guard a storage read on the extension still being
   * alive, because it keeps running on a page after the extension it came from
   * is reloaded. Nothing analogous can happen here: this document IS the
   * extension, and it is torn down with it. What is worth keeping is the rest —
   * ask with defaults, and treat a failed read as "nothing remembered" rather
   * than as an error the user has to see. A storage read that fails must not
   * cost anyone the panel. */
  // ONE key, because there is one. The orphans are not read back here — they
  // are removed once at boot (`sweepOrphanKeys`) and never consulted.
  const STORE_DEFAULTS = { [KEY.session]: null };

  async function readStore() {
    try {
      return await chrome.storage.local.get(STORE_DEFAULTS);
    } catch (err) {
      console.warn("[maestro-cs] storage read failed:", err);
      return { ...STORE_DEFAULTS };
    }
  }

  /** The other half of `readStore`, with the same posture: a storage failure
   * costs the memory, never the panel.
   *
   * A CONTENT SCRIPT would need more, and the difference is worth knowing
   * before anyone copies this the other way: `chrome.storage.local.set` throws
   * SYNCHRONOUSLY once a content script's context is invalidated, so a
   * `.catch()` alone is not a guard there. Neither hazard exists in this
   * document, which IS the extension and is torn down with it; the `try`
   * stays because a write can still fail for ordinary reasons (quota, a
   * profile in trouble), and losing a remembered pick must not also lose the
   * panel. */
  async function writeStore(patch) {
    try {
      await chrome.storage.local.set(patch);
    } catch (err) {
      console.warn("[maestro-cs] storage write failed:", err);
    }
  }

  /** The settings, or nothing — `readStore`'s posture applied to the ask that
   * boots this panel.
   *
   * WHY IT IS A FUNCTION AND NOT A `try` AROUND ONE LINE IN `boot`: it used to
   * be the `try`, and the `catch` wrote `card.fault`, so a `read_settings` that
   * failed printed its exception into the footer. A mid-update mixed-version
   * window did exactly that live — the panel had reloaded and the service
   * worker had not, `sendMessage` answered nothing, and the raw wire string "no
   * answer to read_settings" (the message `ask` builds for a reply it cannot
   * read) sat in red under the rail. That sentence is addressed to whoever
   * wrote this file, not to whoever is filling in an application form, and the
   * slot it took is the panel's ONE line about what the user just asked for.
   *
   * THE DEFAULTS ARE ALREADY EVERYWHERE, which is what makes silence honest
   * here rather than a swallow. `sw.js`'s `DEFAULTS` owns the real values and
   * every reader of this answer already has a rule for not having it: no
   * `appUrl`, no link (`deepLink`, `customLink`); an unreadable `fillMode`
   * narrows to `"assist"` (`boot`). A backend that is genuinely unreachable is
   * still said out loud on every page, by `applyMatch`, in the words of the
   * question the user actually asked.
   *
   * NOT A BLANKET CATCH. `boot`'s outer `.catch` still writes the fault slot,
   * because a throw out of `bindActiveTab` leaves a panel that is bound to no
   * tab and can do nothing at all — that IS a fault, and one nothing else
   * narrates.
   */
  async function readSettings() {
    try {
      return await ask("read_settings");
    } catch (err) {
      console.warn("[maestro-cs] settings read failed:", err);
      return null;
    }
  }

  /** The same posture, one store over: `chrome.storage.sync` is where the
   * SETTINGS live, so a preference written here follows the profile rather
   * than the machine.
   *
   * A second function rather than a parameter on `writeStore`, because the two
   * stores hold different KINDS of thing and mixing them is how a session pick
   * ends up syncing to every browser the user owns. Reads still go through the
   * service worker (`read_settings`) so that `DEFAULTS` stays the one place a
   * default lives; a write needs no defaults, which is why this direction is
   * allowed to be direct.
   */
  async function writeSyncSetting(patch) {
    try {
      await chrome.storage.sync.set(patch);
    } catch (err) {
      console.warn("[maestro-cs] settings write failed:", err);
    }
  }

  // ---------- the pure parts ----------

  /** One descriptor per rail row, in rail order, from one decision.
   *
   * Four states, and the order they are tested in is the whole of the rule:
   *
   * ACTIVE outranks everything, including `done`. The terminal stage is both —
   * an applied job has `done.track` and `stage === "track"` — and a rail that
   * let `done` win there would have no active row at all: where the user IS is
   * not merely a thing they finished.
   *
   * DONE is `stageFor`'s claim and only ever that. It carries no summary here;
   * the stage bodies fill those in from data they can actually see.
   *
   * SKIPPED is "not required on the path you took", which is why it is tested
   * BEFORE locked and never merged into done. The base-resume shortcut reaches
   * Fill without Score or Resume, and — when the job is not in the library at
   * all — without Job either: that row is greyed and still re-askable, never
   * ticked (decisions.js: "the rail greys the row and still offers Add job").
   *
   * LOCKED is the remainder: a later stage, visible but not yet reachable.
   *
   * `stateLabel` is the same four-way answer in words, because the visual one
   * — a tick, a border, an opacity — reaches nobody using a screen reader, and
   * the rail is the whole of "where am I".
   *
   * `ticked` IS A SECOND ANSWER TO A SECOND QUESTION, and adding it is what
   * made the rail able to finish. The tick is a claim about `done`, and it was
   * being read off `state` — where `active` had already won — so the ONE row
   * that is both never got one: an application marked applied sat on a blue
   * "5" forever, and completing the whole journey looked like stopping
   * half-way through the last step.
   *
   * READ OFF `done` DIRECTLY, for every stage, which is why this is not a
   * Track special case. It is also why it changes nothing anywhere else: walk
   * the ladder in `stageFor` and every other rung is guarded by the negation of
   * its own done-ness — `!jobDone ? "job"`, `!scoreDone ? "score"`,
   * `!resumeDone ? "resume"`, `!fillDone ? "fill"` (and `fillFromBase`'s short
   * rail takes the same shape, `fillDone ? "track" : "fill"`). Track is the
   * only stage the ladder can reach while its own `done` is true, so "read the
   * tick from `done`" and "tick the applied Track row" are the same edit. If a
   * future stage becomes reachable while done, it ticks too, which is the
   * answer this rule already gives rather than one someone has to add.
   *
   * WHAT WAS NOT DONE, and why the paragraph above it still stands: the
   * PRECEDENCE is untouched. Letting `done` outrank `active` would have ticked
   * the row by taking `active` away from it — no `aria-current` anywhere, the
   * blue border gone, and a finished rail whose answer to "where am I" is
   * nothing at all. Where the user IS is still not merely a thing they
   * finished; it is now also allowed to be a thing they finished.
   */
  function railModel(decision) {
    return STAGES.map((stage, index) => {
      const state =
        decision.stage === stage.key ? "active"
          : decision.done[stage.key] === true ? "done"
            : decision.skipped.includes(stage.key) ? "skipped"
              : "locked";
      const ticked = decision.done[stage.key] === true;
      return {
        key: stage.key,
        n: index + 1,
        name: stage.name,
        state,
        ticked,
        // BOTH WORDS when both are true, because the two facts are separately
        // useful and a reader that heard only one of them would be told either
        // that the last step is unfinished or that it is not where they are.
        stateLabel: state === "active" && ticked
          ? `${STATE_LABELS.active}, ${STATE_LABELS.done}`
          : STATE_LABELS[state],
        // Is this skip the user's own choice? Carried rather than recomputed
        // because the provenance is `stageFor`'s answer and this file has no
        // business having a second opinion about it. It is `false` on every row
        // that is not skipped — the question is about a skip, and a row that is
        // done or active has not been skipped by anyone.
        skipChoice: state === "skipped"
          && decision.choiceSkipped.includes(stage.key),
        summary: state === "skipped" ? SKIPPED_SUMMARY : "",
      };
    });
  }

  /** Where the identity block's link goes, or null when there is nowhere
   * honest to send anyone. Two rules, both learned the hard way:
   *
   * - the most specific thing we know wins — a tracked APPLICATION beats its
   *   job, because "Application ready" used to send users to the job page
   *   where finding the application again meant searching by hand;
   * - no `appUrl`, no link. We ask the SW where the web app is rather than
   *   keeping a copy of the default, so until that answer arrives we do not
   *   know — and a link that resolves to nothing, or to a guess, is the
   *   failure this project keeps naming. The label names the destination, so
   *   the same corner of the panel is never a mystery link.
   *
   * `name` IS THE THIRD FIELD, and it arrived with the brand row's deletion
   * rather than for its own sake. "Open application ↗" used to sit beside the
   * words "Maestro CS", which is what said WHERE it went; alone beside a job
   * title and a company it reads like the posting's own apply page — the one
   * destination it is not. The visible label is unchanged (short, and the
   * arrow does the "leaves this surface" work); the accessible name spells
   * the destination out, which is the header rule from the a11y side.
   */
  function deepLink({ appUrl, job, application }) {
    if (!appUrl) return null;
    if (application?.id) {
      return {
        href: `${appUrl}/applications/${application.id}`,
        label: "Open application ↗",
        name: "Open this application in Maestro CS",
      };
    }
    return {
      href: job?.id ? `${appUrl}/jobs/${job.id}` : appUrl,
      label: "Open in Maestro CS ↗",
      name: "Open in Maestro CS",
    };
  }

  const stageAction = (stage) => STAGE_LABELS[stage] ?? null;

  /** Would this stage's primary be a button that cannot do what it says?
   *
   * TWO REFUSALS, and they are one rule: a label in `STAGE_LABELS` is a
   * CONSTANT, so a stage whose primary is only sometimes possible has to say
   * so here rather than by rewording itself. Both cases are a control that
   * would run into nothing.
   *
   * - JOB, when the binding is the user's own claim. "Add job" under a row the
   *   user has already bound by hand is an offer to add what is added; the
   *   body offers the switcher and the un-pick instead.
   * - FILL, without a form on the page. This is where the shortcut's old
   *   `hasForm` gate went (`stageFor`'s note): the stage is now decided by
   *   whose question is still open, and "can it run HERE" is decided by the
   *   button. Start fill over a posting page would report "0 filled" about a
   *   page that never had a field in it.
   *
   * ABSENT AND NOT DISABLED, which is `attachRow`'s three-way rule one region
   * down: a dead button whose reason lives in another region is furniture that
   * asks the user to work out why. The Fill body carries the sentence, and the
   * detect ladder's late `form: true` gives the button back with no stage
   * change at all — the repaint is the whole of it.
   */
  function primaryRefused(stage) {
    if (stage === "job") return card.claimed === true;
    if (stage === "fill") return card.hasForm !== true;
    return false;
  }

  /** What `/api/jobs/match` said about this tab's url, folded into the store —
   * or what its failure means, folded into the same four fields.
   *
   * A function taking `(result, store)` rather than inline code, for
   * `resetPageFacts`'s reason: WHICH facts a failed match
   * clears is a list, and a list is worth handing a test whole. `loadContext`
   * turns its exception into `{error}` so that one function owns both
   * outcomes instead of two places agreeing to.
   */
  function applyMatch(result, store) {
    if (result?.error) {
      // The four facts are CLEARED rather than left alone, which was a real
      // bug found by driving this page: on an SPA route change the ask can
      // fail while the PREVIOUS posting's match is still in `card`, and the
      // surface would then offer to autofill the application belonging to the
      // job the user just navigated away from. `null` is what `stageFor` reads
      // as "we do not know" — not as "none" — and it opens the journey at Job,
      // which re-asks.
      store.match = null;
      store.job = null;
      store.application = null;
      store.claimed = false;
      store.pdfReady = false;
      // §11.4: one line, naming the configured URL. Never a login-shaped card,
      // because there is no account to log in to.
      //
      // A `note` and not a `fault`, which is Task 5's split applied: this is
      // the answer to "what is this page?" — asked about ONE url, on ONE tab —
      // so it belongs to the page and dies with it. The settings failure is
      // the other kind: not knowing where the web app is stays true on every
      // tab, so that one survives `resetPageFacts` and this must not.
      store.note = {
        text: `Maestro CS is not reachable${
          store.settings ? ` at ${store.settings.backendUrl}` : ""}: ${result.error}`,
        error: true,
      };
      return store;
    }
    store.match = result.match;
    store.job = result.job
      ? { id: result.job.id, company: result.job.company, title: result.job.title }
      : null;
    store.application = result.application ?? null;
    // The backend named this page (or named nothing). That is not a claim
    // the user made, so a leftover `claimed` from a pick on the previous
    // posting must not open an un-pick door here.
    store.claimed = false;
    return store;
  }

  /** The three editable preview fields, in rail order, with the labels the
   * user reads AND the labels the extraction writes — they are the same three
   * strings, which is the point. `agent.js`'s `extractJobPosting` prefixes a
   * JSON-LD posting's text with `Title: …` / `Company: …` / `Location: …`
   * lines, so this table is read in both directions: `previewFrom` lifts those
   * lines out of the text and `ingestBodyFrom` writes them back. */
  const PREVIEW_FIELDS = [
    ["title", "Title"], ["company", "Company"], ["location", "Location"],
  ];
  // FROZEN: it is spread into every new preview and read as the fallback in
  // both the renderer and the input handler, so it is one object shared by
  // everything that has no preview yet. A stray write to it would be a default
  // that quietly became a claim about the last page anyone looked at.
  const EMPTY_PREVIEW = Object.freeze(
    { title: "", company: "", location: "", text: "", source: null });

  /** What the page said about itself, split into the parts the user may edit
   * and the part they may not.
   *
   * The INVERSE of `extractJobPosting`'s assembly, and it has to be: that
   * function reports one text blob, with the title, company and location as
   * labelled lines on the front of it when the posting described them. Showing
   * those lines inside a 60,000-character textarea is not an editable preview,
   * and prefixing the blob a SECOND time from three inputs would send the
   * backend two of each. So they come off here and go back on there.
   *
   * Total, and empty rather than absent when there is nothing: a page with no
   * posting on it produces three empty fields, which is exactly what the Job
   * stage should render for it. "We found nothing" is not an error, and an
   * empty form the user can type into is the honest rendering of it.
   *
   * THE ONE THING IT REFUSES TO CONFLATE is a page that answered with no
   * posting and a page that did not answer. `extractJobPosting` always returns
   * an object — it falls back to `document.body.innerText` — so a null posting
   * here can only mean the ask itself got nothing back, which is a fact about
   * OUR REACH into the tab and not about what is on it. That is what
   * `UNREACHABLE` records, and the Job stage's sub line says the two things
   * differently: "no job description here" is a claim about the page, and the
   * panel is not entitled to make it about a page it never read.
   */
  const UNREACHABLE = "unreachable";

  function previewFrom(posting) {
    const preview = {
      ...EMPTY_PREVIEW,
      source: posting === null || posting === undefined
        ? UNREACHABLE : (posting.source ?? null),
    };
    const labelled = new Map(PREVIEW_FIELDS.map(([key, label]) => [label, key]));
    const lines = String(posting?.text ?? "").split("\n");
    let i = 0;
    for (; i < lines.length; i += 1) {
      const found = /^([A-Za-z]+): (.*)$/.exec(lines[i]);
      const key = found ? labelled.get(found[1]) : null;
      // `preview[key]` STOPS the lift on a repeat, and that is a content
      // guard rather than a tidiness one: the extractor writes each header
      // line at most once, so a SECOND `Location: …` belongs to the
      // description and has to stay in it. Without this the field would be
      // overwritten by prose and the line would vanish from the JD entirely.
      if (!found || !key || preview[key]) break;
      preview[key] = found[2];
    }
    // The blank line the extractor writes between its header and the
    // description. Consuming it makes a round trip through both functions the
    // identity on an unedited posting — but the reason it is SAFE to lift a
    // header at all is that agent.js:33 pushes that blank UNCONDITIONALLY, on
    // every JSON-LD path. The blank matches no header pattern, so it is what
    // terminates the loop above, which is why a description whose own first
    // line reads "Location: Remote" is never eaten. Were that push ever made
    // conditional, this loop would walk out of the header and into the
    // description a line at a time; the repeat guard above is the only other
    // thing standing there.
    if (lines[i] === "") i += 1;
    preview.text = lines.slice(i).join("\n");
    return preview;
  }

  /** The body of `POST /api/jobs`, from the preview and the tab's url.
   *
   * TWO KEYS AND NO MORE, because `POST /api/jobs` has one client and this is
   * it. Two things about the shape are worth writing down:
   *
   * - the text is REBUILT from the preview rather than passed through, which is
   *   the whole point of an editable preview: a title the user corrected has to
   *   be the title the extraction step reads.
   * - the url is the TAB's (`card.url`), never `location.href` — in this
   *   document that address is the panel's own `chrome-extension://` one, and
   *   a `location.href` fallback here would post the extension as the job.
   *
   * UNSTRIPPED, deliberately: tracking parameters and all. Whether two urls are
   * the same posting is the SERVER's question (`is_same_posting`, SYSTEM.md §11
   * item 9), and a client that quietly trimmed a query string would be
   * answering it — differently from the server, on some board where the query
   * string IS the job id.
   *
   * An empty field contributes no line at all, mirroring `extractJobPosting`'s
   * own `if (posting.title)` guards: a `Title: ` prefix with nothing after it
   * is a claim that the posting has an empty title.
   */
  function ingestBodyFrom(preview, url) {
    const parts = [];
    for (const [key, label] of PREVIEW_FIELDS) {
      const value = String(preview?.[key] ?? "").trim();
      if (value) parts.push(`${label}: ${value}`);
    }
    // A separator only when there is a header to separate — asymmetric with
    // `previewFrom`, which consumes a leading blank wherever it finds one, and
    // deliberately so. A page with no described posting has no header lines at
    // all, and emitting a blank first line for it would put an empty line in
    // front of every plain-text JD that `previewFrom` would then eat back off
    // it: the round trip would drift by one line per save.
    if (parts.length) parts.push("");
    parts.push(String(preview?.text ?? "").trim());
    // The extraction's own ceiling, applied again because the header lines are
    // added after it sliced.
    return { raw_text: parts.join("\n").trim().slice(0, 60000), source_url: url };
  }

  // Every count this surface prints goes through it, because "1 skills" is the
  // sentence that tells a user nobody read the copy.
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

  /** The composite `latest_scores` holds for one target, or null when there is
   * no row. Rendered, never computed: the panel does no scoring (design §4.2,
   * "render them; compute nothing new"), and a missing row means "not scored",
   * which is not a zero. */
  function compositeFor(scores, targetType, targetId, phase) {
    const row = (scores ?? []).find(
      (entry) => entry?.target_type === targetType
        && entry?.phase === phase
        && String(entry?.target_id) === String(targetId));
    const composite = Number(row?.composite);
    return Number.isFinite(composite) ? Math.round(composite) : null;
  }

  /** The day part of an ISO timestamp, and nothing else matches. */
  const ISO_DAY = /^\d{4}-\d{2}-\d{2}/;

  /** What an application has to show for itself, out of the one read that
   * knows: `GET /api/applications/{id}` (and the PATCH that marks it applied,
   * which answers with the same shape).
   *
   * TWO FACTS, because two are what the endpoint carries. `pdf_path` is the
   * document this application sends and `applied_at` is the day it went out.
   * There is no `evidence` field on `ApplicationDetail` and the panel does not
   * invent one: the proposal ledger's `evidence_json` — the receipts and
   * confirmation screenshots the mockup's line was drawn from — belongs to the
   * agent-apply flow, and this surface is not a client of it. A receipt line
   * here would be a claim with nothing behind it, which is the one thing this
   * panel keeps refusing to make.
   *
   * `null` WHEN THERE IS NEITHER, and that is the Track body's honest absence:
   * a draft with no rendered PDF has nothing to show, and a line that said so
   * with a dash would report its own emptiness as a fact about the application.
   *
   * THE DATE IS SLICED, NOT FORMATTED. `toLocaleDateString` would read the
   * user's locale into one date inside an English sentence — `grouped`'s rule
   * in the Job body, for `grouped`'s reason — and parsing it into a `Date` to
   * re-render it would be this panel taking a position on a timezone the
   * backend already resolved. The regex is what makes that safe: a value that
   * is not an ISO timestamp produces no date rather than a slice of whatever
   * arrived.
   *
   * THE FILENAME is split on both separators and takes the last part, because
   * `pdf_path` is a server path and the user has no use for the directories
   * above it. Both separators because the server that wrote it may not be the
   * platform reading it.
   */
  function evidenceFrom(detail) {
    const pdfName = String(detail?.pdf_path ?? "").split(/[\\/]/).pop() || null;
    const appliedOn = ISO_DAY.exec(String(detail?.applied_at ?? ""))?.[0] ?? null;
    return pdfName || appliedOn ? { pdfName, appliedOn } : null;
  }

  /** The store, in the shape `stageFor` reads. `hasScores` is deliberately
   * "we have at least one row", not "we asked": null and [] mean different
   * things everywhere else in this file too.
   *
   * Takes the store rather than closing over it, like `resetPageFacts` and
   * `applyMatch` — this section is "the pure parts", and a function that reads
   * a module-level `card` is not one of them however pure its arithmetic. */
  function cardFacts(store) {
    return {
      match: store.match,
      hasApplication: store.application !== null,
      pdfReady: store.pdfReady,
      status: store.application?.status ?? null,
      touched: store.touched,
      hasForm: store.hasForm,
      baseArmed: store.baseArmed,
      hasScores: Array.isArray(store.scores) && store.scores.length > 0,
      baseSelected: store.baseSelected,
    };
  }

  /** Is this a page the extension has any business talking about?
   *
   * ONE SITE for the rule, because two of them now ask it and they must not
   * drift: `onTab` decides whether to LOAD anything at all, and the stage
   * snapshot decides whether the draft picker may be OFFERED. A settings tab,
   * a new tab, a PDF viewer and `about:blank` are all "no" to both.
   *
   * Total for `hostOf`'s reason: a tab that has not committed a url reports an
   * empty string, and the honest answer about it is no. */
  function isWebPage(url) {
    return /^https?:/i.test(String(url ?? ""));
  }

  /** Total, like `sessionTenant` and for the same reason: this asks about
   * whatever a TAB currently holds, and a tab that has not committed a url
   * reports an empty string, which `new URL` throws on. */
  function hostOf(url) {
    try {
      return new URL(url).hostname;
    } catch {
      return "";
    }
  }

  /** Total for `hostOf`'s reason, and `null` rather than `""` because this one
   * is COMPARED rather than shown: a stored entry always carries a real origin
   * string, so a tab with no url refuses every remembered pick instead of
   * matching some other empty thing. */
  function originOf(url) {
    try {
      return new URL(url).origin;
    } catch {
      return null;
    }
  }

  /** What this panel remembers about the page.
   *
   * EVERY FIELD HERE IS READ BACK by `restoreSession`, and that is a rule this
   * entry did not always keep. It used to carry three more —
   * `attachedBase`, `guidedArmed` and `claimed` — written on every save and
   * read by nothing, because two surfaces shared one key and the shape had to
   * satisfy the other one's reader. R-C deleted that reader, and rather than
   * leave three constants being serialized to disk on every page of every
   * wizard, they went. Whatever is added here next has to be read back or it
   * does not belong.
   *
   * `claimed` IS THE ONE WORTH EXPLAINING, because it looks like a fact the
   * bridge should carry: page 2 of a wizard does need to know the binding was
   * the user's own pick, or the Job row has no door back. It gets that from
   * `applicationId` — `restoreSession` sets `card.claimed = true` for any entry
   * naming an application, and that inference is CORRECT rather than a
   * shortcut. The backend's own match runs before restore and wins, so
   * anything that reaches the restore path is a memory the user created. A
   * stored `claimed` would be a second source for one fact, and the kind that
   * disagrees quietly.
   *
   * `now` is a PARAMETER rather than a `Date.now()` inside, so this is a
   * function of its arguments — the same reason `restorableSession` takes one.
   *
   * `null` when the tab's url has no tenant identity, and that is a refusal
   * rather than a default. `restorableSession` compares `entry.tenant` on the
   * way back in and a real page never produces `null`, so an entry written
   * without one could never be restored by anything — and writing it would
   * replace a usable memory with an unusable one.
   *
   * `baseArmed` IS REMEMBERED AND NOT DERIVED. The tempting derivation is
   * `application === null && Boolean(baseSlug)`, which arms the shortcut for
   * every user who owns a base resume and skips Score and Resume for people who
   * never asked. Here it is a deliberate answer ("use base as-is"), made on the
   * posting and spent on the apply page — a different page load, which is
   * exactly what this entry exists to cross.
   */
  function sessionEntryFrom(store, now) {
    const tenant = sessionTenant(store.url);
    const origin = originOf(store.url);
    if (!tenant || !origin) return null;
    return {
      origin,
      tenant,
      at: now,
      applicationId: store.application?.id ?? null,
      status: store.application?.status ?? "draft",
      jobId: store.job?.id ?? null,
      company: store.job?.company ?? null,
      title: store.job?.title ?? null,
      pdfReady: store.pdfReady === true,
      touched: store.touched === true,
      baseSlug: store.baseSlug,
      baseArmed: store.baseArmed === true,
    };
  }

  // ---------- render ----------
  //
  // `render()` is the only thing that writes to the document and it rebuilds
  // each region from `card` every time — deliberately dumber than patching,
  // for a reason this codebase learned the expensive way: a targeted update
  // that forgets a region leaves a stale sentence about a job the user is no
  // longer looking at.
  //
  // THE PRICE, stated rather than discovered. Every element is replaced, so
  // focus identity dies with it: a render while a control is focused drops the
  // user back to the document, and since Task 7 the stage bodies hold text
  // inputs.
  //
  // WHAT TASK 7 DID ABOUT IT, and what it did not. Renders are not click-driven
  // — four loads land asynchronously and each one repaints — so a user typing
  // into the Job preview can meet a render mid-keystroke. The CHARACTERS are
  // safe: `card.preview` holds them, written on every `input` event and
  // rendered back from there, so the replacement element carries what was
  // typed. An in-DOM value is not state this loop can keep, and that is the
  // rule for every input added after this one.
  //
  // Still outstanding: the CARET, and — since Task 9 — something wider than a
  // caret. Two cases, and they are not the same size:
  //
  // A RACE, which is what this paragraph used to describe on its own. A render
  // during typing re-creates the Job preview's input with the right text and
  // the user is no longer in it. The window is a load landing late — the four
  // are usually done before the first keystroke — so it is a real cost, not a
  // common one.
  //
  // AND A CERTAINTY, which Task 9 introduced and which no window bounds. The
  // Resume fork's "Tailor" limb is this surface's first DISCLOSURE: pressing it
  // renders, the rail is rebuilt, and the button the user just activated is a
  // different element — so keyboard focus lands on `document.body`, 100% of the
  // time, at the exact moment two new controls appear that the user pressed it
  // in order to reach. `aria-expanded`/`aria-controls` name the region for a
  // screen reader; neither puts anyone in it. Tabbing forward from the document
  // start walks the whole panel to get back to where they were.
  //
  // The same rebuild resets the rail's `scrollTop`. All three wanted ONE answer
  // — capture around the rail rebuild and restore after — and TAKING IT IS
  // `withPlaceKept`, which this render calls around `renderRail` and around
  // nothing else. It arrived with the reopenable done row, as the debt said it
  // would: that feature puts a click handler on rows halfway down a scrolling
  // rail, so every one of them lands the disclosure's certainty (press, rebuild,
  // focus on `document.body`) plus a jump to the top of the list. One fix
  // serves all three because they are one cause.
  //
  // WHAT IT DOES NOT FIX, said out loud rather than left to be discovered: the
  // CARET inside a restored text input. Focus is restored by id, so the element
  // is right and the characters are right (`card.preview` and friends hold
  // them), but the selection lands wherever a fresh `focus()` puts it. That is
  // a strictly smaller cost than the one this replaced — the user was in the
  // document body before — and closing it means capturing `selectionStart` per
  // input, which is a second mechanism for a caret nobody has yet complained
  // about.
  //
  // AND NOT REGION PATCHING, which is the fix this deliberately is not: it
  // would trade a visible cost for an invisible one, and the invisible one is
  // the stale sentence about a job the user is no longer looking at.
  //
  // The footer note is the one exception: it is a live region, so it is
  // written through `textContent` and never replaced (see panel.html).
  //
  // Everything dynamic goes through `textContent`. A job title, a company name
  // and a backend error are all attacker-influenced text on an ATS that lets
  // employers write their own postings.

  const region = (id) => document.getElementById(id);

  function node(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined && text !== null) el.textContent = String(text);
    return el;
  }

  /** `null` children are skipped, so a renderer can put a conditional inline
   * — and because `append(null)` prints the word "null" rather than nothing. */
  function attach(parent, ...children) {
    parent.append(...children.filter(Boolean));
    return parent;
  }

  /** The footer's primary, and the ONLY caller left.
   *
   * `comingSoon` LIVED HERE as this function's default `onClick`, and it is
   * gone rather than kept: the primaries landed one task at a time and it stood
   * in for the ones that had not, saying "lands in the next change" out loud so
   * that no control on this surface could look live and not be. Every label
   * this map still holds now has a `STAGE_RUN` entry, and the one that did not
   * — Track's — is not a label any more (see `STAGE_LABELS`). A placeholder
   * with nothing to stand in for is a sentence that has become false, which is
   * the thing it existed to prevent.
   *
   * So `onClick` is REQUIRED. A caller that forgets it now builds a button that
   * throws on the first press rather than one that quietly does nothing — the
   * loud failure, which is the one this file keeps choosing. */
  function actionButton(className, label, onClick) {
    const button = node("button", className, label);
    button.type = "button";
    button.addEventListener("click", onClick);
    return button;
  }

  /** The one way out of this panel, or nothing at all.
   *
   * It had a REGION of its own — `#head`, a mark plus the words "Maestro CS"
   * plus this anchor — and that region is gone. Chrome draws its own side-panel
   * title bar above this document reading the extension's name, so the brand
   * row was the same name a second time, in the scarcest 40 pixels the surface
   * has. What it carried that the native bar cannot is this link, so the link
   * is what survived; it renders into the identity row beside the match chip.
   */
  function deepLinkAnchor() {
    const link = deepLink({
      appUrl: card.settings?.appUrl, job: card.job, application: card.application,
    });
    if (!link) return null;
    const anchor = node("a", "linkish", link.label);
    anchor.href = link.href;
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    anchor.setAttribute("aria-label", link.name);
    return anchor;
  }

  /** The match chip, or nothing at all. `match === null` is the backend not
   * asked or not reachable, which is NOT "New": the panel never converts a
   * missing answer into a claim about the library. */
  function matchChip() {
    if (card.application) {
      return node("span", "chip app", `Application · ${card.application.status ?? "draft"}`);
    }
    if (card.match === "exact") return node("span", "chip lib", "In library");
    if (card.match === "none") return node("span", "chip new", "New");
    return null;
  }

  /** One ATS ring. `null` renders the empty state — a dash in a grey ring —
   * because "not scored yet" is not a low score. */
  function ring(value, color) {
    const el = node("div", value === null ? "ring empty" : "ring",
                    value === null ? "–" : String(value));
    el.style.setProperty("--v", value === null ? "0" : String(value));
    if (value !== null) el.style.setProperty("--ring-color", color);
    return el;
  }

  function ringColumn(value, color, label) {
    const column = node("div");
    attach(column, ring(value, color), node("div", "lbl", label));
    return column;
  }

  /** Before → After, always in the same place: the base resume's composite and
   * the tailored application's, both read from `latest_scores` rows. One ring
   * when only one number exists, the empty pair when neither does. */
  function renderAts() {
    const before = card.baseSlug
      ? compositeFor(card.scores, "base_resume", card.baseSlug, "base") : null;
    const after = card.application
      ? compositeFor(card.scores, "application", card.application.id, "tailored") : null;

    const ats = node("div", "ats");
    attach(ats, ringColumn(before, "var(--cs-primary)", before === null ? "ATS" : "Base"));
    if (after === null) {
      attach(ats, node("span", "hint",
                  before === null ? "score after adding the job" : "tailor to raise it"));
      return ats;
    }
    attach(ats, node("span", "arrow", "→"),
           ringColumn(after, "var(--cs-good)", "Tailored"));
    if (before !== null) {
      const delta = after - before;
      attach(ats, node("span", "delta", `${delta >= 0 ? "+" : ""}${delta}`));
    }
    return ats;
  }

  function renderIdentity(decision) {
    const who = node("div", "who");
    // With no job in the library, the tab's host is the only thing we honestly
    // know about the page — and it is also the visible proof of which tab this
    // panel is bound to.
    attach(who,
           node("div", "title",
                card.job ? (card.job.title || "Untitled job") : hostOf(card.url)),
           node("div", "co", card.job?.company ?? ""));
    const row1 = attach(node("div", "row1"), who, matchChip());

    const children = [row1, renderAts()];
    // The shortcut's own copy, under the identity rather than in the footer:
    // it explains what the rail is about to skip, so it belongs beside what it
    // is about.
    if (decision.shortcutNote) children.push(node("div", "sub", decision.shortcutNote));
    // THE LINK IS LAST, on a line of its own, and it took a measurement to get
    // there. Beside the chip in `row1` was the obvious home and the wrong one:
    // `who` and a `flex: none` link compete for one axis, and at the widths a
    // side panel is actually dragged to (measured at 320/360/400) the job title
    // was left 104px and five wrapped lines — a header that pushed the rail off
    // screen to make room for a link. Down here it competes with nothing, and
    // the block's bottom-right is where a card's one way out belongs anyway.
    const link = deepLinkAnchor();
    if (link) children.push(link);
    region("identity").replaceChildren(...children);
  }

  // ---- what a stage body is handed ----

  /** THE CONTEXT: everything a stage body in `panel/stages/` may read, and
   * everything it may do. Built fresh per render, handed in, and never kept.
   *
   * THIS IS THE SEAM, and the whole reason the bodies could move out at all.
   * Every body reads `card` and writes `card`, so "extract the renderers" over
   * a published store would have traded one long file for a mutable global
   * that several files share. `card` stays module-private HERE; what crosses
   * the boundary is a snapshot of the facts a body needs and the callbacks it
   * may fire. Enforced by scope rather than by agreement, which is the only
   * kind of enforcement this arrangement has.
   *
   * THREE GROUPS, and which one a new entry belongs to is the whole rule:
   *
   * - `facts` — READ-ONLY, and a copy rather than the store. One entry per
   *   thing a body renders, so this list IS the answer to "what do the bodies
   *   know". Defaults are resolved here (the preview falls back to
   *   `EMPTY_PREVIEW`) so no body owns a second copy of that rule.
   * - `act` — the callbacks. Firing one is a body's ONLY way to change
   *   anything: they write the store, they render, and they are the functions
   *   the footer's primaries already call, so a fork button and a footer button
   *   cannot drift into two behaviours.
   * - `build` — the shared builders. `node`/`attach` so a body builds elements
   *   the way the rest of the panel does (`textContent`, null children
   *   dropped), and `plural` because "1 skills" is the sentence that tells a
   *   user nobody read the copy.
   *
   * DESIGNED FROM THREE BODIES rather than from the first one: Job needs
   * free-text fields plus a write on every keystroke, Score needs a list plus
   * a selection callback, Resume needs an anchor's href plus three triggers.
   * The groups are what all three have in common; the KEYS grow with the
   * bodies, and a body that wants something not on this list adds it here
   * rather than reaching for the store.
   */
  function stageContext() {
    return {
      facts: {
        preview: card.preview ?? EMPTY_PREVIEW,
        // The label table, handed over because two things that never render —
        // `previewFrom` and `ingestBodyFrom` — read it too, so it stays where
        // they are rather than moving to the one place that draws it.
        previewFields: PREVIEW_FIELDS,
        resumes: card.resumes,
        scores: card.scores,
        baseSlug: card.baseSlug,
        job: card.job,
        // `hasForm` IS BACK ON THIS SNAPSHOT, with ONE reader, and the reader
        // is the change. It was dropped when the Job picker stopped gating on
        // it — a fact handed to five bodies that none of them wants is an
        // invitation to re-derive a deleted gate one file over — and it
        // returns because the Fill body now has to say something true about a
        // page with no form on it ("filling starts on the employer's Apply
        // page"). That is a sentence about the PAGE, which is exactly the kind
        // of fact this snapshot carries; the stage no longer reads it at all
        // (`stageFor` dropped the form gate, and `cardFacts` still hands it
        // over for the shortcut's copy alone).
        hasForm: card.hasForm === true,
        // The Job picker's list. Null until asked; the body treats that the
        // same as empty — honest absence, nothing rendered.
        applications: card.applications,
        // Is the panel bound to a page at all? The list survives a tab switch
        // (it is not a fact about a posting), so without this the drafts would
        // be offered on `chrome://settings` the moment the user glanced at it
        // — an offer to fill a form on a page the extension cannot even reach,
        // and a pick there arms the rail against a tab with no tenant. `onTab`
        // refuses to LOAD anything on these urls; this is the same rule on the
        // paint side, and it is what the dropped form gate was incidentally
        // doing for non-web tabs.
        webPage: isWebPage(card.url),
        // Provenance of the current binding. The Job body is a switcher /
        // un-pick door only for a claim; a backend match is not one.
        claimed: card.claimed === true,
        application: card.application,
        evidence: card.evidence,
        // Resolved here rather than handed the settings object: a body needs
        // somewhere to send the user, not the panel's configuration. `null`
        // until the SW answers, and a body that gets null renders no link —
        // the same rule `deepLink` follows for the header.
        appUrl: card.settings?.appUrl ?? null,
        tailorOpen: card.tailorOpen === true,
        // The base-as-is CLAIM, and the Resume body is the only reader: armed,
        // that body names the choice and offers the way out of it instead of
        // re-offering the limb the user already pressed. It also feeds
        // `stageFor` off `cardFacts` — the same split `hasForm` and `pdfReady`
        // have, and for the same reason: a body that had to derive "did I arm
        // this" would be deriving a stage decision one file over.
        baseArmed: card.baseArmed === true,
        // Is an action running? A boolean rather than the stage key `card.busy`
        // holds, because a body never needs to know WHICH — the footer keys its
        // spinner on the stage because one stage has one primary, and a body
        // only has to stop offering a second one.
        busy: card.busy !== null,
        // The Fill stage's five, and they split the same way the body renders
        // them: `fillMode` is the control at the top, `fill`/`writeResults`/
        // `residue`/`essays` are what the last run reported, and `eeoConsent`
        // is the one row whose answer comes from the backend rather than from
        // the page. All five are null until a run has happened, which the body
        // renders as an offer rather than as a report of zero.
        fillMode: card.fillMode,
        // THE ATTACH's three, and they are three questions rather than one
        // state: `pdfReady` is whether there is a document to attach at all,
        // `fileInputs` is whether this page has somewhere to put it (and
        // whether that somewhere is unambiguous), and `attached` is what
        // happened if the user pressed. A body that had to derive any of them
        // would be deriving a fact about a page it may not reach for.
        //
        // `pdfReady` also feeds `stageFor` off `cardFacts`, which is a
        // different snapshot with a different job — the same split `hasForm`
        // has, and the reason both can be here without either becoming the
        // second home for a stage decision.
        pdfReady: card.pdfReady === true,
        fileInputs: card.fileInputs,
        attached: card.attached,
        // The REAL filename, which the panel already knows: `evidenceFrom`
        // takes it off the application detail's `pdf_path`. Handed over so the
        // offer can name the document rather than saying "your resume" about a
        // file the user has a specific name for. Null before the detail lands,
        // which the body renders as the generic sentence.
        attachName: card.evidence?.pdfName ?? null,
        fill: card.fill,
        writeResults: card.writeResults,
        residue: card.residue,
        essays: card.essays,
        eeoConsent: card.eeoConsent,
        // The pause rows' drafts. Handed over whole rather than per row: a body
        // renders the whole list in one pass, and a per-row lookup callback
        // would be a second way to read one store field.
        answers: card.answers,
        // The composer, whole: open-ness, the draft question, the answer and
        // the question it answers. One object rather than five keys because
        // the body renders them as one control and they are written together.
        qna: card.qna,
      },
      act: { editPreview, pickApplication, unpickApplication, pickBase, useBaseAsIs,
             stopUsingBaseAsIs, openTailor, quickTailor,
             setFillMode, startFill, attachResume, scrollToField, editAnswer,
             rememberAnswer, submitAnswer, toggleQna, askAbout, editQuestion,
             askQuestion, copyAnswer, trackThis },
      build: { node, attach, plural },
    };
  }

  /** One preview field, as the user typed it. The body fires this on every
   * `input` event; see `card.preview` for why the characters live in the store
   * and not in the element.
   *
   * THE ONE WRITER of `previewTyped`, which is what makes that flag mean what
   * it says: this function is reached from an `input` handler and from nowhere
   * else, so setting it here is the panel learning that a person is typing.
   * `landPosting` reads it to refuse every later extraction. */
  function editPreview(key, value) {
    card.preview = { ...(card.preview ?? EMPTY_PREVIEW), [key]: value };
    card.previewTyped = true;
  }

  /** One pause row's draft answer, as the user typed it. `editPreview`'s twin,
   * for `editPreview`'s reason and with the same deliberate omission: NO
   * render. The store write is what makes the character survive the next
   * repaint; rendering here would destroy the input being typed into on every
   * keystroke, and nothing else on this surface reads a draft while it is
   * being written. */
  function editAnswer(qid, value) {
    card.answers = { ...card.answers, [qid]: { ...card.answers[qid], text: value } };
  }

  /** Whether this row's answer should be learned. Same store, same no-render
   * rule — the checkbox's own DOM state is what the user sees change, and a
   * render would rebuild the box mid-click. */
  function rememberAnswer(qid, learn) {
    card.answers = { ...card.answers, [qid]: { ...card.answers[qid], learn } };
  }

  /** Open or close the QnA drawer. A disclosure and nothing else, `openTailor`'s
   * shape: it asks the backend for nothing and writes nothing down, because
   * "I am looking at the composer" is not a choice anyone has made.
   *
   * The draft and the answer SURVIVE a close, which is what makes this a drawer
   * rather than a reset button: a user who folds the composer away to read the
   * residue list under it has not withdrawn their question. Only a page change
   * clears them (`resetPageFacts`), and that is a different event with a
   * different meaning. */
  function toggleQna() {
    card.qna = { ...card.qna, open: !card.qna.open };
    render();
  }

  /** Open the drawer with THIS question in it — the essay rows' handoff.
   *
   * The runner routes a QUESTIONY textarea to the essay lane precisely because
   * it wants a written answer rather than a control on the page, and the drawer
   * is where that answer is written. So the row hands its label over instead of
   * asking the user to retype a paragraph-long question into the box below it.
   *
   * THE ANSWER GOES WITH THE QUESTION. A paragraph written for the previous
   * question, left standing under a new one, is exactly what `answered` exists
   * to prevent — and here we know the question changed, so clearing is honest
   * rather than cautious. Re-pressing the SAME row keeps what is there: it is
   * the same question, and re-fetching an answer already on screen is a round
   * trip for nothing.
   */
  function askAbout(question) {
    card.qna = question === card.qna.question
      ? { ...card.qna, open: true }
      : { open: true, question, answered: null, answer: null, copied: false };
    render();
  }

  /** The composer's draft question, as the user typed it. `editPreview`'s twin
   * with `editPreview`'s deliberate omission: NO render. The store write is what
   * makes the character survive the next repaint, and rendering here would
   * destroy the textarea being typed into on every keystroke.
   *
   * The standing answer is NOT cleared, and that is what `answered` buys: the
   * drawer prints the question each answer was given for, so an answer under a
   * half-retyped question stays a true statement instead of becoming a stale
   * one. Clearing it here would need a render to be visible, which is the
   * caret-destroying repaint this rule exists to avoid.
   */
  function editQuestion(value) {
    card.qna = { ...card.qna, question: value };
  }

  /** Put the answer on the clipboard, and say so in the control that did it.
   *
   * THE PANEL CAN JUST DO THIS, which a content script could not have. This
   * document is the extension — a secure context with a real user gesture
   * behind the click — so `navigator.clipboard.writeText` is the whole of it:
   * no permission beyond the gesture, no relay through a content script, and
   * no `execCommand` fallback.
   *
   * GENERATION-GUARDED like every other write that spans an await. The clipboard
   * write is a promise, and a user is free to switch tabs across it — without
   * the check, `copied` would land on the NEXT page's drawer and claim a copy of
   * a paragraph that page never had. The failure is the note slot's, because it
   * is the one thing here the user cannot see for themselves: a Copy button that
   * silently did nothing is the Jobscan failure this surface keeps naming.
   */
  function copyAnswer() {
    const token = generation;
    const answer = card.qna.answer;
    if (!answer) return;
    navigator.clipboard.writeText(answer).then(() => {
      if (!current(token)) return;
      card.qna = { ...card.qna, copied: true };
      render();
    }).catch((err) => {
      if (!current(token)) return;
      card.note = { text: `Could not copy: ${String(err?.message ?? err)}`,
                    error: true };
      render();
    });
  }

  /** Take this base resume, and remember it.
   *
   * THE PICK IS THE USER'S. `baseSelected` is what `stageFor` reads to call
   * the Score stage done, and only this function and a restore ever set it —
   * `loadBaseScores` moves `baseSlug` by ranking and leaves `baseSelected`
   * alone on purpose, because a panel that ticked the step off by sorting a
   * list would be answering on the user's behalf. It follows that this is also
   * the one place the ranking may be overridden: clicking the second row means
   * the second row, and the next score read must not slide off it.
   *
   * The write is what makes the pick outlive the page. An ATS wizard is six
   * page loads and each one rebuilds this panel's facts from scratch
   * (`resetPageFacts` clears `baseSlug` and `baseSelected` both), so without
   * it the user would pick again on every step.
   */
  function pickBase(slug) {
    card.baseSlug = slug;
    card.baseSelected = true;
    // Painted BEFORE the write, and the order is the point: the store is the
    // truth this surface renders, storage is only where it survives. A picked
    // row that waited for a storage round trip to look picked would be a
    // control that feels broken for as long as the disk takes.
    render();
    rememberSession();
  }

  /** Write down what this panel is armed with, under the bridge key.
   *
   * IT WRITES AN APPLICATION-LESS ENTRY, which is the whole of Task 9's session
   * decision and the thing to be careful about. A base picked at the Score
   * stage and a base-as-is arming are choices made BEFORE any application
   * exists, and they are exactly what has to survive the next page of a wizard
   * — so refusing to write them (the older behaviour) loses the user's answer
   * at the page boundary. `restoreSession`'s `if (entry.applicationId)` guard
   * is what makes such an entry safe to read back: without it, an entry naming
   * no application restores as `{id: undefined}` and the surface claims an
   * application that does not exist.
   *
   * NOT generation-guarded, and this is the one store-writing path in the file
   * where that is correct rather than forgotten. The entry is built from
   * `card` SYNCHRONOUSLY — before the first await, by a click made on the
   * render the user is looking at — so there is no window in which a tab
   * switch could make it stale. It is also scoped to the url it was built
   * from, so even a write that lands late lands under a tenant that only that
   * tab's pages read back.
   */
  function rememberSession() {
    const entry = sessionEntryFrom(card, Date.now());
    // No tenant, nothing to scope a memory to. See `sessionEntryFrom`: this is
    // a refusal, not a fallback.
    if (!entry) return;
    writeStore({ [KEY.session]: entry });
  }

  /** Open the second fork level. A disclosure and nothing else: it asks the
   * backend for nothing and writes nothing down, because "I am looking at the
   * tailoring options" is not a choice anyone has made yet. */
  function openTailor() {
    card.tailorOpen = true;
    render();
  }

  /** Rules only, or rules plus the model. A body callback rather than an
   * action: it asks the backend for nothing, takes no `busy`, and there is no
   * await for a tab switch to race across.
   *
   * PAINTED BEFORE THE WRITE, `pickBase`'s order and its reason: the store is
   * the truth this surface renders and storage is only where it survives, so a
   * segment that waited for a round trip to look pressed would be a control
   * that feels broken for as long as the disk takes.
   *
   * It writes `chrome.storage.sync` DIRECTLY where every read of a setting goes
   * through the service worker, and the asymmetry is deliberate: a read needs
   * the defaults, which live in exactly one place (sw.js's
   * `DEFAULTS`), and a write needs none. `card.settings` is left alone —
   * `card.fillMode` is what the body and the action read, and a second copy
   * inside the settings object would be the drift this arrangement avoids.
   */
  function setFillMode(mode) {
    card.fillMode = mode;
    render();
    writeSyncSetting({ fillMode: mode });
  }

  /** Put a residue field in front of the user, in whichever frame holds it.
   *
   * The panel is in no page, so the scroll is a message; it is a FAN-OUT
   * because the control can be in the application's subframe, which is where
   * Greenhouse and Lever put the whole form. The payload is the qid and
   * nothing else — see `page_broadcast`'s allow-list for why that is the
   * property, not an economy.
   *
   * Fire-and-forget, and silent when it fails: a jump that does not land is
   * not something the panel's one sentence should be spent on, and the row the
   * user clicked is still on screen with the field's own name on it.
   */
  function scrollToField(qid) {
    ask("page_broadcast", {
      tabId: card.tabId, message: { type: "scroll_to_field", qid },
    }).catch((err) => console.warn(`[maestro-cs] could not scroll to ${qid}:`, err));
  }

  /** The stage bodies, from the roster that gathers them.
   *
   * Read at load, so a panel.html that forgot the `<script>` tag fails on the
   * first render rather than rendering a rail with no bodies under it — the
   * quiet version of the same fault, and the one a user would have to notice
   * for us.
   */
  const STAGE_BODIES = ns.panelStages;

  /** WHICH ROW'S BODY IS OPEN — `revisit ?? stage` — and the ONE place a
   * reopened view yields to the data.
   *
   * EXACTLY ONE BODY, which is why this returns a key rather than a set. Two
   * open bodies on a 400px rail is a surface where the user has to work out
   * which one their next press belongs to — and the footer's single primary is
   * keyed on THIS answer (`renderFoot`), so with two of them that button would
   * belong to one body and sit under the other.
   *
   * THE TWO WAYS A REOPENED ROW DIES, and both are the same rule: the view may
   * not outlive the facts it was opened over.
   *
   * - THE RAIL MOVED ON (`over`). The user reopened Score while standing at
   *   Fill; a tailor lands a PDF, or a pick sends the journey back, and the
   *   stage the row was opened beside is not the stage any more. Yielding is
   *   what "data always wins" means here — the alternative is a panel showing a
   *   step the user chose two facts ago.
   * - THE ROW IS NO LONGER A DOOR. Narrower and still reachable: under the base
   *   shortcut the stage is pinned to `fill`/`track` by the shortcut rung, so
   *   `done.score` can fall (a score re-read that comes back empty) while the
   *   stage sits exactly where it was. Without this limb the rail would then
   *   render the Score body under a row it has just re-drawn as SKIPPED, which
   *   is the un-skip feature arriving by accident rather than by decision.
   *
   *   IT IS `isReopenable`'S OWN ANSWER, over the rows the rail is about to
   *   draw, and asking it here rather than re-stating "still done" is what lets
   *   a skipped row be reopened at all: a base-as-is Resume row is a door while
   *   `done.resume` is false, so the old test would have closed it on the very
   *   next render. One rule, asked twice — the door the rail draws and the body
   *   this keeps open can never disagree about which rows open.
   *
   * IT CLEARS AS IT READS, which is the one thing worth knowing before calling
   * it twice: a stale `revisit` is dropped from the store here rather than
   * merely ignored, so the next render starts from a store that agrees with
   * what was painted. The alternative — a getter that quietly returns something
   * other than what is stored — is the second home for "which stage are we in"
   * that this store's own header refuses.
   */
  function openRow(decision) {
    const revisit = card.revisit;
    if (!revisit) return decision.stage;
    const row = railModel(decision).find((one) => one.key === revisit.row);
    if (revisit.over !== decision.stage || !row || !isReopenable(row)) {
      card.revisit = null;
      return decision.stage;
    }
    return revisit.row;
  }

  /** Open this reopenable row's body, or close it again if it is the open one.
   * "Reopenable" and not "done": `isReopenable` also opens a row skipped by
   * the user's own claim, and this handler is hung on whatever it opens.
   *
   * A VIEW WRITE AND NOTHING ELSE. It asks the backend for nothing, takes no
   * `busy`, clears no tick and resets no fact — reopening Fill after a wizard
   * page turn must not unmake the claim that page 1 was filled. `toggleQna`
   * and `openTailor` are the same shape one layer down.
   *
   * THE DECISION IS RECOMPUTED rather than closed over from the render that
   * built this handler, and the difference is real: `over` has to be the stage
   * at the moment of the CLICK. `stageFor` is pure and reads the store, so
   * recomputing is both cheap and the only reading that cannot be stale.
   */
  function toggleRevisit(key) {
    const closing = card.revisit?.row === key;
    card.revisit = closing
      ? null
      : { row: key, over: stageFor(cardFacts(card)).stage };
    render();
    // A claimed Job body needs the draft list to offer a switch. Unmatched
    // Job already loads it via shouldLoadApplications; a restored pick on
    // page 2 of a wizard never went through that door.
    if (!closing && key === "job" && card.applications == null) {
      loadApplications(generation);
    }
  }

  function renderRail(decision, open) {
    region("rail").replaceChildren(...railModel(decision).map((row) => {
      const stage = node("li", `stg ${row.state}`);
      // Announced, not merely coloured: the rail IS "where am I", and a screen
      // reader gets none of the border, the tick, or the opacity. `aria-current`
      // marks the one you are on; the numeral carries the rest in words.
      //
      // ON THE DATA-ACTIVE ROW, always — including while another row's body is
      // open under it. The rail must not fake its state to match the view: the
      // step the user is ON is a fact about their application, the body they
      // have opened is a fact about what they are looking at, and a rail that
      // moved `aria-current` (or the border) onto a reopened row would be
      // reporting the second as the first.
      if (row.state === "active") stage.setAttribute("aria-current", "step");
      // `row.ticked` and not `row.state === "done"` — see `railModel`. The tick
      // answers "is this step finished", which is `done`'s question, and the
      // terminal row is both finished and current: it keeps the active border
      // and the active numeral chip (`.stg.active .stg-num`, panel.css) and
      // prints a ✓ in it, which is what a rail that has ENDED looks like.
      const numeral = node("span", "stg-num", row.ticked ? "✓" : row.n);
      numeral.setAttribute("aria-label", row.stateLabel);
      // A DONE ROW IS A DOOR — for Score/Resume/Fill always, and for Job when
      // the binding is a user claim; so is a row SKIPPED by a claim, which is
      // the base-as-is Resume row. `isReopenable` carries which and why. A REAL BUTTON rather than a click handler on the
      // row: the whole line is the target, it has to be reachable and pressable
      // from the keyboard, and `aria-expanded` is how a screen reader is told
      // that this is a thing that opens rather than a heading that moved.
      const reopenable = isReopenable(row);
      const line = node(reopenable ? "button" : "div", "stg-row");
      if (reopenable) {
        line.type = "button";
        // Stable across the rebuild this press causes — see `withPlaceKept`.
        // Without it the user's own click would leave them on `document.body`
        // at the exact moment a body they asked for appeared below.
        line.id = REVISIT_ID(row.key);
        // `statusSegment`'s rule, for `statusSegment`'s reason: every control on
        // this surface reads `busy`, and a reopen that stayed live during a run
        // would swap the body out from under a fill the user is watching.
        line.disabled = card.busy !== null;
        line.setAttribute("aria-expanded", row.key === open ? "true" : "false");
        // ONLY WHILE THE REGION EXISTS, which is the Tailor fork's rule
        // (`stages/resume.js`) and the same reasoning: `aria-controls` naming
        // an id nothing carries offers a jump that goes nowhere.
        if (row.key === open) line.setAttribute("aria-controls", STAGE_BODY_ID(row.key));
        line.addEventListener("click", () => toggleRevisit(row.key));
      }
      attach(line, numeral,
             node("span", "stg-name", row.name),
             node("span", "stg-sum", row.summary),
             reopenable ? caret(row.key === open) : null);
      // `?.()` and the `open` test together: one body, under whichever row is
      // open — the data's row, or the done row the user reopened — and no body
      // at all for a stage that has not built one. `attach` drops the null.
      const body = row.key === open ? STAGE_BODIES[row.key]?.(stageContext()) : null;
      // The address `aria-controls` names, and the reason it is set HERE rather
      // than in each body: the id belongs to the rail's grammar (which row is
      // open) and not to what any one stage renders.
      if (body) body.id = STAGE_BODY_ID(row.key);
      attach(stage, line, body);
      return stage;
    }));
  }

  /** The open/closed mark on a reopenable row — the AFFORDANCE, and the reason
   * it is not left to the cursor: a done row that opens looks exactly like a
   * done row that does not until something says so, and "hover to find out" is
   * not a thing a keyboard can do.
   *
   * `aria-hidden`, because the button it sits in already says the same thing in
   * `aria-expanded`, and a reader announcing both would announce it twice. */
  function caret(open) {
    const mark = node("span", "stg-caret", open ? "▾" : "▸");
    mark.setAttribute("aria-hidden", "true");
    return mark;
  }

  /** Rebuild the rail without losing the user's place in it.
   *
   * THE RENDER COST BLOCK ABOVE IS THIS FUNCTION'S REASON, in full: every
   * element is replaced on every render, so focus identity dies with the
   * element and the rail's `scrollTop` goes back to zero. Both are paid by a
   * user who did nothing but press a control the rail rebuilds — a disclosure,
   * and now a reopened row — and by one who was typing when a load landed.
   *
   * BY ID, and only by id. `document.activeElement` is a live node that this
   * rebuild is about to throw away, so the identity that survives it has to be
   * a string: the controls worth restoring carry a stable one for exactly this
   * (`stg-open-<stage>`, `tailor-options`, `preview-<key>`, `answer-<qid>`,
   * `qna-question`). A control with no id gets no restore, which is the honest
   * behaviour rather than a gap — there is nothing to find it by, and guessing
   * by position is how focus lands on the wrong control after a list reorders.
   *
   * FOCUS IS NEVER TAKEN, only given back: with nothing focused,
   * `document.activeElement` is the body, whose id is empty, and this does not
   * touch focus at all. A render that stole focus into the rail would fight the
   * user for the address bar.
   *
   * THE LOOKUP IS DOCUMENT-WIDE and the restore happens BETWEEN the rail's
   * rebuild and the footer's, which is a constraint rather than a detail: it
   * works today because every stable id on this surface belongs to the rail. A
   * footer control that gained one would be found here and focused a moment
   * before `renderFoot` replaced it, which is a restore onto a node about to be
   * thrown away. Scoping the search to the rail is the fix IF that day comes;
   * it is not taken now because it buys nothing against the ids that exist and
   * would need a selector the panel does not otherwise use.
   */
  function withPlaceKept(rebuild) {
    const rail = region("rail");
    const top = rail.scrollTop;
    const focused = document.activeElement?.id || null;
    rebuild();
    // AFTER the rebuild, and both in this order: the scroll belongs to the new
    // list.
    rail.scrollTop = top;
    // `preventScroll`, and it is the line that makes the one above mean
    // anything. Focusing an element the browser judges to be out of view
    // scrolls the nearest scrollable ancestor to reveal it — and the rebuild
    // has just changed the layout, so the position we have restored frequently
    // does NOT contain the control we are about to focus. Without the flag the
    // restore is silently overridden by the very next statement, and the two
    // halves of this function fight: the scroll is put back and then thrown
    // away, every time, invisibly. Asking for focus without scrolling is what
    // makes the restore authoritative.
    if (focused) document.getElementById(focused)?.focus({ preventScroll: true });
  }

  /** The two statuses this panel WRITES, which is not the two it can read.
   *
   * `ALLOWED_STATUSES` (backend/app/schemas/application.py) has seven —
   * interviewing, offered, accepted, rejected, withdrawn follow these two — and
   * the tracker in the web app is where that vocabulary belongs: it is a list
   * with filters and a history, and a 400px rail is not. What the panel owns is
   * the one transition it is standing next to: the user has just filled a form,
   * and "did you submit it" is the question the page in front of them answers.
   */
  const STATUS_OPTIONS = [["draft", "Draft"], ["applied", "Applied"]];

  /** Draft / Applied — the ONE control on this surface that writes a status.
   *
   * IT LIVES IN THE FOOTER, permanently, and that is the design's own decision
   * rather than a placement: "the mark-applied nudge lives here permanently —
   * no more hunting" (design §Footer) replaced a nudge that appeared and
   * disappeared under a 25-field strip. The Track stage's BODY
   * therefore renders no status control at all — see `panel/stages/track.js` —
   * because two Draft/Applied pairs on one screen are two writers for one
   * field, and the user cannot tell which one they pressed.
   *
   * A RADIOGROUP on real buttons, `baseRow`'s and `modeControl`'s shape and
   * their reasoning: the segment IS the control, and `aria-checked` rather than
   * the tint alone, because "is this application marked applied" is exactly the
   * thing a user must not have to infer from a background colour. (No roving
   * tabindex here either — the third site of the debt Task 12 counted and
   * deliberately left for the pass that owns the rail's focus.)
   *
   * TWO REFUSALS, and both are the same rule: do not offer a control that would
   * lie.
   *
   * - NO APPLICATION, no segment. A status control with nothing to be draft
   *   ABOUT is a control naming a thing that does not exist.
   * - A STATUS OUTSIDE THE PAIR, no segment either — an application moved to
   *   `interviewing` in the web app would render with NEITHER button checked,
   *   and pressing Draft would silently walk the record backwards past three
   *   states. The identity chip still names it ("Application · interviewing")
   *   and the Track body's own sentence says where to change it, so nothing is
   *   hidden; what is withheld is a two-value control over a seven-value field.
   */
  function statusSegment() {
    const status = card.application?.status ?? null;
    if (!STATUS_OPTIONS.some(([value]) => value === status)) return null;
    const segment = node("div", "status-seg");
    segment.setAttribute("role", "radiogroup");
    segment.setAttribute("aria-label", "Application status");
    for (const [value, label] of STATUS_OPTIONS) {
      const on = status === value;
      // `draft-on` and `on` are two different tints for two different states,
      // which is the mockup's own pair: a draft is a warning colour because it
      // is unfinished business, an applied one is the good colour because it is
      // the end of the journey.
      const button = node("button", on ? (value === "draft" ? "draft-on" : "on") : null,
                          label);
      button.type = "button";
      button.setAttribute("role", "radio");
      button.setAttribute("aria-checked", on ? "true" : "false");
      // `actingLimb`'s rule, one region over: the footer's primary greys for
      // the length of any action, and a status button that stayed live beside
      // it would send a PATCH into a page a fill is still walking.
      button.disabled = card.busy !== null;
      button.addEventListener("click", () => setStatus(value));
      attach(segment, button);
    }
    return segment;
  }

  function renderFoot(open) {
    // Written, not rebuilt — the live region has to outlive the render that
    // changes it. Two kinds of sentence share the slot and must not read
    // alike: "the backend is unreachable" is not "that button is coming".
    //
    // The page note wins when there is one, because it is the answer to
    // something the user just did; the standing fault is what the slot says
    // the rest of the time.
    const said = card.note ?? card.fault;
    const note = region("note");
    note.textContent = said?.text ?? "";
    note.className = said?.error ? "note error" : "note";

    // THE MARK-APPLIED NUDGE IS THIS CONTROL. The card rendered a prompt under
    // its strip that appeared and disappeared; design §Footer replaced it with
    // a status segment that is simply always there when there is a status —
    // "no more hunting" — so honouring `stageFor().nudge` here means rendering
    // the control, not rendering something beside it.
    //
    // AND IT IS NOT GATED ON THE DECISION, which is a correction rather than a
    // simplification. `nudge === "mark-applied" || done.track` is exactly
    // `hasApplication` — the two limbs are the draft and the non-draft halves
    // of one condition — and `statusSegment` re-reads `card.application` for
    // itself anyway, so the test was an inert twin: it could be replaced with
    // `true` without changing a pixel. An `if` that cannot fail is worse than
    // no `if`, because it reads as a guard. ONE site decides whether there is a
    // status to show, and it is the function that draws it.
    //
    // `track-this` GETS NO CONTROL HERE, and that is honest rather than a gap.
    // The route exists backend-side (`POST /api/applications/from-base`) but
    // this PANEL has no action for it, so a button here would be one this
    // surface cannot press. The Track BODY carries that state instead,
    // where the user is reading: it names what happened and sends them to
    // Maestro CS through the header's own link.
    const controls = [];
    const segment = statusSegment();
    if (segment) controls.push(segment);
    // THE PRIMARY BELONGS TO THE OPEN ROW, not to the inferred stage, and the
    // two are the same thing until a done row is reopened. It has to be this
    // way for the feature to be one: the design's promise is "one primary at a
    // time, always in the footer", so the Fill body a user reopens on page 3 of
    // a Workday wizard has its Start fill exactly where every other stage's
    // primary has always been. Keyed on the stage instead, that body would be a
    // report with no way to act on it — a door that opens onto a wall — and the
    // alternative (a second Start fill inside the body) is the two-writers-for-
    // one-behaviour this footer exists to prevent.
    //
    // THE RAIL IS UNAFFECTED. `decision.stage` still decides which row is
    // active, which row is ticked and what the identity line says; this is the
    // one control that follows the body, because it is the body's.
    const label = primaryRefused(open) ? null : stageAction(open);
    if (label) {
      // Busy is keyed on the STAGE, because one stage has one primary. (A
      // surface whose several primaries share ONE button has to key its
      // spinner on an action id instead; this one does not.)
      //
      // Disabled while ANY action runs, spinning only on the one that is
      // running: a second POST of the same posting is the "you saved this last
      // week" path at best, and the click that starts it is the click the user
      // makes when nothing on screen says the first one is still going.
      const cta = actionButton(card.busy === open ? "cta spin" : "cta",
                               label, STAGE_RUN[open]);
      cta.disabled = card.busy !== null;
      controls.push(cta);
    }
    region("foot-controls").replaceChildren(...controls);
  }

  function render() {
    const decision = stageFor(cardFacts(card));
    // ONCE PER RENDER, and passed to both readers rather than asked twice: this
    // is the call that drops a stale `revisit`, so a second one would be a
    // second place the store can change during a paint.
    const open = openRow(decision);
    renderIdentity(decision);
    // AROUND THE RAIL AND NOTHING ELSE. The other two regions hold no scroll
    // and — bar the footer's primary, which is where a press LEAVES the user
    // rather than where it takes them from — nothing worth keeping a place in.
    withPlaceKept(() => renderRail(decision, open));
    renderFoot(open);
  }

  // ---------- the tab binding ----------

  /** Bind to the active tab and stay bound: activation and same-tab
   * navigation both re-run the load. The PANEL outlives page loads — that is
   * the point — so navigation events are its only signal a page changed. */
  async function bindActiveTab() {
    // Registered BEFORE the first load is awaited, not after. From Task 6 that
    // load is a backend round trip, and a slow or hanging one would leave the
    // panel unbound — which fails silently: it keeps showing the tab it opened
    // on and nothing ever says the following stopped.
    //
    // A tab can be closed, discarded or replaced between the event and the
    // read, so both callbacks end in a warn-and-skip rather than a note: the
    // note is the panel's one line about the page in front of the user, and an
    // apology about a tab they have already left is not that. The next
    // activation rebinds, which is the recovery.
    chrome.tabs.onActivated.addListener(({ tabId }) => {
      chrome.tabs.get(tabId)
        .then((activated) => onTab(tabId, activated.url ?? ""))
        .catch((err) => console.warn(`[maestro-cs] panel could not follow tab ${tabId}:`, err));
    });
    // `onUpdated` fires for every tab in the window, and for reasons that are
    // not navigations (a title, a favicon, a load state). Both narrowings are
    // the guard: acting on another tab's url would leave the panel showing —
    // and then acting on — a page the user is not looking at.
    chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
      if (tabId !== card.tabId) return;
      if (changeInfo.url) {
        onTab(tabId, changeInfo.url).catch(
          (err) => console.warn(`[maestro-cs] panel could not reload tab ${tabId}:`, err));
        return;
      }
      // A LOAD THAT CHANGED NO URL — which is what a reload of the same page
      // is. `changeInfo.url` is only sent when the address actually changes, so
      // the branch above never sees a reload and the panel used to sit through
      // one holding whatever it had learned before it. That is a dead end for
      // exactly one sentence: "the companion cannot see this page — reload the
      // tab" asks the user to do the one thing the panel was not watching for.
      // Anything else is left alone (see `healPosting` for how narrow this is).
      if (changeInfo.status !== "complete") return;
      healPosting(generation).catch(
        (err) => console.warn(`[maestro-cs] panel could not re-read tab ${tabId}:`, err));
    });
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (tab) await onTab(tab.id, tab.url ?? "");
  }

  async function onTab(tabId, url) {
    // FIRST, and before anything is loaded: everything the store holds is
    // about the page we are leaving.
    resetPageFacts(card);
    card.tabId = tabId;
    card.url = url;
    // Every load still in flight is now about a tab the user has left. See
    // `current` for what that costs and what stops it.
    generation += 1;
    // A settings tab, a new tab, a PDF viewer, `about:blank`. The panel is open
    // across all of them and the user tabs through them constantly, so asking
    // the backend about a `chrome://` url would be a round trip per glance for
    // an answer that can only be "no" — the same always-on cost `loadHasForm`
    // refuses to pay for detection. It still resets and repaints: a panel that
    // kept the previous posting's title while showing a settings tab is the
    // confident lie `resetPageFacts` exists to prevent.
    if (!isWebPage(url)) {
      render();
      return;
    }
    await loadContext(generation);
  }

  // ---------- loading, and whose answers are allowed to land ----------
  //
  // THE BINDING IS THE GUARD, and it is the panel's alone: `fanoutTab` verifies
  // WHO may name a tab, never WHICH, because "the tab the user is looking at"
  // is not a fact a service worker can reach. Task 5 made the panel follow the
  // active tab; this is the half that only matters once the loads are real.
  //
  // A load is four round trips and a page read, and the user is free to switch
  // tabs during any of them. Every one of those answers resolves into the SAME
  // store — so without a guard, tab A's match, scores and application id paint
  // over tab B's a moment after tab B finished loading, and the panel then
  // offers a fill and a PDF attach aimed at a job the user is not looking at.
  // The SW would pass both, because a stale `card.tabId` is a valid tab id.
  //
  // `generation` is bumped at `onTab`, once, beside the binding it protects.
  //
  // THE RULE, for EVERY async function in this file that writes the store —
  // not just the loaders below. Tasks 7 and 8 add user-initiated actions (add
  // job, score all bases) and those are equally raceable: a POST is a round
  // trip like any other, and the user may switch tabs while it is open.
  //
  //   1. land the answer in a LOCAL;
  //   2. assign to the store only past `if (!current(token)) return;`;
  //   3. render only past the same check.
  //
  // Why the rule needs writing down rather than trusting: `card.scores = await
  // api(…)` does not LOOK like a write-after-await. It reads as one statement,
  // and the assignment happening at settle time — after any check that came
  // before it, before any check that comes after — is invisible in the shape of
  // the line. That is exactly how the bug fixed in 14c6957 was written, in a
  // function whose other four checks were all correct.
  //
  // ONE audited exception: `card.resumes`, which is assigned at settle time on
  // purpose. The base-resume library is TAB-INDEPENDENT — the same rows for
  // every posting, which is why `resetPageFacts` keeps it — so a late answer
  // there is the same fact arriving late rather than a stale claim about a page.
  // Anything read as a fact ABOUT the posting follows the three steps.
  let generation = 0;
  const current = (token) => token === generation;

  // WHEN THIS PAINTS: after every landing, not once at the end. A surface
  // whose loads run before it is on screen can afford one render at the end;
  // this panel is already open and being read while these are in flight, so a
  // single render at the end is several seconds of a surface that says nothing
  // about the page. Each loader below therefore ends in
  // `render()`, and the guard above is what keeps a stale one from painting.

  /** Tier C (design §5), plus the things its answer cannot carry.
   *
   * ONE URL, and it is `card.url`, the TAB's — never `location.href`, which in
   * this document is the panel's own `chrome-extension://` address.
   *
   * `ApplicationSummary` has no `pdf_path`, so a matched application costs a
   * SECOND read, and it is worth it here because the answer feeds a STAGE:
   * `pdfReady` is what `stageFor` reads to decide Resume-is-done, so without
   * it the rail asks a user with a rendered PDF to tailor one.
   */
  async function loadContext(token) {
    // Paint the binding BEFORE the first round trip. `resetPageFacts` has just
    // emptied the store, so without this the panel shows an empty identity for
    // as long as the match takes — and the tab's host is a fact we already
    // have, and the visible proof of which tab this panel is bound to.
    render();
    let result;
    try {
      result = await api(`/api/jobs/match?url=${encodeURIComponent(card.url)}`);
    } catch (err) {
      result = { error: String(err?.message ?? err) };
    }
    if (!current(token)) return;
    applyMatch(result, card);
    render();

    // The backend did not put an application on this page. Before falling back
    // to "nothing armed", see whether this browser remembers one being picked
    // here — a wizard step is a fresh page load, and losing the pick on every
    // one of them is what makes a surface look like it forgot what it was
    // doing.
    // `restorableSession` owns whether the memory may be used; the backend's
    // own answer always wins over it.
    if (!card.application) await restoreSession(token);
    if (!current(token)) return;

    // AWAITED, where the scores are not: this one decides a STAGE. A rail that
    // shows Score and then jumps to Fill a beat later is stage navigation by
    // accident, which is the one thing this design says it never does.
    await loadHasForm(token);
    if (!current(token)) return;
    render();

    // LAST of the stage-deciding loads, so the question it asks is the real
    // one: the Job stage is what the user is on only once the match, the
    // remembered pick and the form verdict have all had their say. Reading a
    // posting off a page whose stage is Fill would be a read nobody asked for.
    if (stageFor(cardFacts(card)).stage === "job") await loadPosting(token);
    if (!current(token)) return;

    // The picker is a Job-stage cost, and only when a form is in front of the
    // user with nothing matched to it. Awaiting it the way `loadPosting` is
    // awaited: the list is what the active body renders, so a rail that
    // paints Add job and then sprouts five rows a beat later is the same
    // stage-navigation-by-accident that posting-load was written to refuse.
    if (shouldLoadApplications(card)) await loadApplications(token);
    if (!current(token)) return;

    // Cheap, and it makes the base list a ranking rather than a guess. NOT
    // awaited: the ranking is presentation (design §4.2), so a slow or failed
    // read costs the ordering and nothing else — no stage waits on it.
    loadBaseScores(token);

    // THE READ THAT IS ALSO A VALIDATION, and since the ghost-binding round it
    // is named as one. `restoreSession` above deliberately makes no round trip
    // — it arms from what this browser remembers — so on a wizard's second page
    // the binding on screen has never been checked against the backend at all.
    // This GET is already being made for the PDF and the status, and it is
    // aimed at the application's own resource, so a 404 from it is the backend
    // saying the row is gone: authoritative, free, and the only place the panel
    // can learn it. See the catch for the rule about what is NOT authoritative.
    if (card.application) {
      try {
        const detail = await api(`/api/applications/${card.application.id}`);
        if (!current(token)) return;
        card.pdfReady = Boolean(detail.pdf_path);
        // The Track stage's evidence line, out of the read that was already
        // being made: `pdf_path` is here for `pdfReady` anyway, and
        // `applied_at` costs nothing beside it.
        card.evidence = evidenceFrom(detail);
        // The status may have moved on since the pick — marked applied in the
        // web app, or in another tab. The row is truth; the memory is a cache.
        card.application = { ...card.application, status: detail.status ?? "draft" };
      } catch (err) {
        if (!current(token)) return;
        // A 404 IS THE ONE FAILURE THAT MEANS SOMETHING, and the whole
        // discrimination is this line. The user deleted the draft in the web
        // app; the bridge restored it anyway, because a restore reads disk and
        // asks nothing. Below this branch is every other failure — the SW
        // asleep, no network, a 500, a message that got no answer — and each
        // one says nothing whatever about whether the application exists. They
        // must keep the binding: the bridge's tolerance of an unreachable
        // backend is a deliberate design (a wizard is six page loads and a
        // flaky connection must not cost the user their pick), and unbinding on
        // one of them would be this panel forgetting a real application while
        // OFFLINE — the same lie in the mirror.
        //
        // WHICH bindings may be dropped is not decided here.
        // `dropDeletedApplication` owns that rule — a claim, never the
        // backend's own match, and its docstring is where the reasoning lives
        // — so this call is a REQUEST and the line after it reads the answer.
        // One owner, because two places agreeing about which bindings are
        // droppable is two places free to stop agreeing.
        if (err?.status === 404) {
          dropDeletedApplication();
          if (!card.application) {
            // The user is unbound on a page that still has a form in front of
            // them, so the way back is offered rather than left for the next
            // page load: this is the door `shouldLoadApplications` describes,
            // and a restored pick never went through it (the binding was
            // already there when it was asked).
            //
            // A list ALREADY READ is not re-read, and does not need to be:
            // `dropDeletedApplication` has taken the dead row out of it, which
            // is the one thing this panel has learned about it. A round trip
            // to hear the rest of the same list again is a fetch the user did
            // not ask for.
            if (shouldLoadApplications(card)) await loadApplications(token);
            return;
          }
        }
        card.pdfReady = false; // unknown reads as not-ready: it offers to tailor.
        // And nothing to show, for the same reason: a read that failed told us
        // nothing about what this application holds, and the last page's
        // answer is not an answer about this one.
        card.evidence = null;
      }
      render();
    }
  }

  /** Re-arm the panel from a remembered pick, if one survives the guards.
   *
   * The application is NOT re-fetched here:
   * `loadContext` re-reads it right after, for the pdf and the status, and
   * doing it twice would spend a round-trip to learn the same thing. What is
   * restored is what the page itself cannot say — which application the user
   * chose, and that they have already filled or attached here.
   *
   * THE SCOPE COMES FROM `card.url`, NEVER FROM `location`, because this
   * document is not in the page — `location` here is the panel's own
   * `chrome-extension://` address, which would scope every pick to the
   * extension itself and hand one board's entry to another. `sessionTenant` is
   * total precisely so that a tab with no committed url answers `null` instead
   * of throwing. Nothing restores onto
   * a null tenant — a pick made on a real board carries a real tenant string —
   * and `originOf` refuses it a second time for the same reason.
   */
  async function restoreSession(token) {
    const stored = await readStore();
    if (!current(token)) return;
    const scope = {
      now: Date.now(),
      origin: originOf(card.url),
      tenant: sessionTenant(card.url),
      matchedJobId: card.job?.id ?? null,
      ttlMs: SESSION_TTL_MS,
    };
    // ONE KEY, ONE SET OF GUARDS, and no tie-break — see `KEY` for the
    // decision that collapsed Task 8's second key. What was a choice between
    // two entries is a single read: one key cannot shadow itself, so the
    // "an older entry beats a fresher pick for the whole TTL" hazard is gone
    // rather than ordered.
    const entry = restorableSession(stored[KEY.session], scope);
    if (!entry) return;
    // GUARDED: an entry may name no application at all. This panel writes
    // exactly those — a base picked at the Score stage, and the base-as-is
    // arming — where the whole point is a choice made BEFORE an application
    // exists, and `{id: undefined}` restored as an application is the "ready
    // state claiming an application" bug in the shape that produced it. This
    // guard is the condition of writing such an entry at all — see
    // `rememberSession`, which is the writer that does.
    if (entry.applicationId) {
      card.application = {
        id: entry.applicationId,
        status: entry.status ?? "draft",
        job_company: entry.company,
        job_title: entry.title,
      };
      // The user chose this target by hand; `stageFor` reads anything but
      // "exact" as "we do not know" and would put Add job over the top of it.
      // Only when an application came back, though: forcing it for a bare
      // base-as-is arming would claim the job is in the library, which is a
      // claim about the LIBRARY and not about the choice being restored.
      card.match = "exact";
      // THE INFERENCE IS THE DESIGN, not a gap where a stored field should be.
      // `sessionEntryFrom` deliberately does not write `claimed` (see its note):
      // an entry that names an application is one the USER created, because the
      // backend's own match runs before restore and wins outright — so anything
      // that gets this far is a pick, and `applicationId` already says so. A
      // stored flag would be a second source for one fact, free to disagree.
      card.claimed = true;
    }
    card.pdfReady = entry.pdfReady === true;
    card.touched = entry.touched === true;
    if (entry.baseSlug) {
      card.baseSlug = entry.baseSlug;
      // A restored slug is the user's earlier choice, so the ranking in
      // `loadBaseScores` must not quietly move off it (that function's
      // `basePickedByUser` rule).
      card.baseSelected = true;
    }
    card.baseArmed = entry.baseArmed === true;
    if (!card.job && entry.jobId) {
      card.job = { id: entry.jobId, company: entry.company, title: entry.title };
    }
  }

  /** Does the tab in front of the user hold an application form?
   *
   * The panel cannot answer this itself: detection is a page function and this
   * document is in no page. So it asks frame 0 through the one door that may
   * name a frame.
   *
   * WITHOUT `panel_prepare` FIRST, deliberately, and that is now the whole of
   * the claim. Preparing means injecting the content scripts into every frame
   * of the tab, and doing that BEFORE asking, on every tab switch, is exactly
   * the always-on cost the detection gate exists to avoid (autoMount's rule: a
   * read on every page on the web is the cost design §11 rejects). Content
   * scripts are already in every page loaded since the extension started, which
   * is the ordinary case, so the speculative injection buys an answer we
   * already have. Preparing first would not even buy a better one:
   * `panel_prepare` reports a constant `{injected: true}`, which says the call
   * did not throw — not that any frame received anything.
   *
   * WHAT THIS PARAGRAPH USED TO SAY AND NO LONGER DOES: that injection stays
   * reserved for an explicit user action, and that a tab our scripts never
   * reached simply reads as `hasForm: false` forever. The second half is the
   * bug — an extension reload orphans the scripts in every open tab, so
   * "forever" is the state a user lands in routinely and there is nothing they
   * can do about it that they would ever think of. `preparePage` (below) now
   * spends ONE injection per page, after a silence rather than before an ask,
   * and this detect does not call it: the POSTING path does. WHEN a posting is
   * being read — the Job stage, which is most unmatched pages — this function's
   * own re-ask schedule finds the injected scripts on a later rung; when it is
   * not, nothing prepares the tab and the verdict stays a silence-shaped false.
   * The cost argument is untouched — nothing here injects speculatively — and
   * that gap is named again, with its reasoning, at `preparePage`.
   *
   * A silence still reads as `hasForm: false` in the moment, which is the
   * honest rendering of "we do not know whether this page has a form".
   *
   * Failing is not a note. "This tab has no content scripts" is a fact about
   * our own reach, not about the page and not about anything the user did; the
   * panel's one sentence belongs to what they just asked for. */
  async function loadHasForm(token) {
    const verdict = await askDetectPrepared(token);
    if (!current(token)) return;
    card.hasForm = verdict?.form === true;
    card.fileInputs = countFileInputs(verdict);
    // AN IMMEDIATE YES IS THE WHOLE ANSWER. A Greenhouse-class page whose form
    // is in the first paint costs exactly the one round trip it always did —
    // the retry below is for the pages that answered no, and nothing else.
    if (!card.hasForm) retryHasForm(token);
  }

  /** The upload-box count off a detect verdict, defensively.
   *
   * A silence, an old content script that answers three keys, or a page that
   * somehow reported a non-number all mean the same thing to the one reader
   * this has: we do not know of a box, so no attach is offered. `Number(…) || 0`
   * folds every one of those to zero, which is the honest floor — the failure
   * direction here is offering an attach that has nowhere to go, and this
   * cannot take it.
   *
   * Written out rather than inlined at both call sites, because there are two
   * (the first ask and each retry) and a count that disagreed between them
   * would be a rail whose offer flickered. */
  const countFileInputs = (verdict) => Number(verdict?.fileInputs) || 0;

  /** Ask whether this page has a form, and if NOTHING answers, put our scripts
   * there and ask once more. `askPostingPrepared`'s twin, deliberately the same
   * three lines, and it arrived on 2026-08-19 with the stage change above.
   *
   * WHY IT HAD TO: `preparePage`'s own docstring named the gap it was leaving —
   * an orphaned tab that never reaches the Job stage is never injected into,
   * and its form verdict stays a silence-shaped `false` forever — and the
   * stage change WIDENED it. A user with a base armed now stands at Fill on
   * every page, so the posting read (the only caller there was) no longer runs
   * for them, and an extension reload would have left them reading "no
   * application form on this page" over a full Workday form with nothing that
   * could ever correct it.
   *
   * THE COST ARGUMENT IS UNCHANGED, and this is why it is a silence and not a
   * `false` that triggers it. Content scripts are declared for every http(s)
   * page (manifest `content_scripts`), so the ordinary form-less page ANSWERS —
   * "no form here" is a verdict, and no injection is spent on it. `null` means
   * nobody was home, which is the one failure this cures. The bound is
   * `preparePage`'s own `card.prepared`: one injection per page whatever asks
   * for it, so a page that is silent to both ladders is injected into once and
   * not twice.
   *
   * THROUGH IT ON EVERY RUNG, the posting ladder's rule for the posting
   * ladder's reason: the cure for a silent tab is not something only the first
   * attempt gets, and the once-per-page bound is what makes that free.
   */
  async function askDetectPrepared(token) {
    const answer = await askDetect();
    if (answer !== null || !current(token)) return answer;
    if (!await preparePage(token) || !current(token)) return null;
    // The scripts that could not answer a moment ago are there now.
    return await askDetect();
  }

  /** The one detection ask, so the first attempt and every retry are the same
   * message with the same silence-is-no reading. */
  async function askDetect() {
    try {
      return await ask("panel_frame0", {
        tabId: card.tabId, message: { type: "detect_page" },
      });
    } catch (_) {
      return null;
    }
  }

  /** How long the panel keeps re-asking a page that has not finished rendering.
   *
   * WHY A RETRY AT ALL: every page read this file makes runs ONCE, at tab-bind,
   * and a Workday page has not rendered at that moment — the SPA is still
   * fetching. The answer then freezes for as long as the panel stays bound.
   * Live, twice, on the same ATS class: elevancehealth.wd1 (2026-08-18) reported
   * a full visible form as `hasForm: false`, which hid the base-fill shortcut;
   * itron.wd5 (2026-08-19) reported no posting at all over a full JD, which left
   * three empty boxes and an Add job that refused to save them.
   *
   * THE PICKER IS NO LONGER AMONG THE THINGS THIS RESCUES. The same live
   * session that produced the retry also killed the picker's form gate
   * (`shouldLoadApplications`): the offer stands on any unmatched page, so it
   * does not wait for this schedule and does not fail when the schedule runs
   * out. What is left riding on a late yes is the Fill stage's OFFER — its
   * body and the footer's primary — rather than the stage itself, which
   * stopped reading the form verdict with the 2026-08-19 change.
   *
   * WHY BOUNDED, and why growing: unbounded polling on every page is the
   * always-on cost the one-shot was avoiding, and a page that has not grown a
   * form seven seconds after it was bound is a posting, not a slow form. Three
   * retries over 1s/2s/4s spans the SPA render without turning the panel into a
   * background poller: the early one catches the common case, the late one
   * covers a cold cache, and then it stops. It stops SILENTLY — a permanently
   * form-less page ends exactly as it does today, because "no form here" is the
   * ordinary answer for most of the web and not something to report, and the
   * same goes for "no posting here", which is true of most of the web too.
   *
   * WHY NOT AWAITED by `loadContext`: this spans seven seconds. The posting
   * read, the ranking and the application detail would all sit behind it, so
   * every ordinary posting page would paint its Job stage seven seconds late to
   * buy an answer it already has.
   *
   * ONE CADENCE, TWO LADDERS, and the constant is the only thing they share.
   * `retryHasForm` starts only when the first answer was no and stops at the
   * first yes; `retryPosting` starts on every Job-stage page and stops when an
   * answer stops improving. They do not even begin together — a page with a
   * form the user has armed no base for sits at Job, so the posting ladder runs
   * there while the form ladder never started, and a page that is not a posting
   * at all runs the form ladder alone — so folding them into one loop would be
   * two independent stop conditions sharing a `for`, each having to remember
   * whether the other was still interested. Renamed off `DETECT_RETRY_MS` when
   * the second rider arrived: a constant named for one of its two readers
   * reads as that reader's private business.
   */
  const PAGE_RETRY_MS = [1000, 2000, 4000];

  async function retryHasForm(token) {
    for (const delay of PAGE_RETRY_MS) {
      await sleep(delay);
      // Before the ASK, because `askDetect` names `card.tabId` and that field
      // has already moved: without this the retries of every page the user
      // passes through are re-aimed at whatever tab they land on.
      if (!current(token)) return;
      const verdict = await askDetectPrepared(token);
      // And again before the WRITE, which is the file's standing rule: a
      // seven-second window is the widest one here, so this is the answer most
      // likely to come back to a tab the user has left.
      if (!current(token)) return;
      // THE COUNT IS TAKEN ON EVERY ANSWER, above the form gate rather than
      // below it, because the two facts are independent: an SPA that has
      // rendered its upload box but not enough of a form to clear Tier B's
      // threshold still has a box to attach to, and a count only written on a
      // `form: true` answer would leave the offer permanently hidden there.
      //
      // ONLY WHEN A VERDICT CAME BACK. `askDetect` returns null for a page that
      // did not answer, and null is "we could not ask" — the same reading
      // `loadHasForm` gives it. Writing zero on a silence would take a box the
      // first ask really found back off the screen a second later, which is a
      // control that appears and vanishes for no reason the user can see.
      if (verdict) {
        const before = card.fileInputs;
        card.fileInputs = countFileInputs(verdict);
        // A late box is worth a repaint on its own: `hasForm` may never flip on
        // a posting page whose only form-ish thing is an upload control, and
        // the offer would then wait for some unrelated render.
        if (card.fileInputs !== before) render();
      }
      if (verdict?.form !== true) continue;
      card.hasForm = true;
      // A REPAINT IS THE WHOLE OF IT, and that is a shrink rather than an
      // oversight. A late yes MOVES NO STAGE any more — `stageFor` stopped
      // reading the form when the shortcut's gate went to the button — so what
      // this render changes is what the Fill stage OFFERS: the body swaps its
      // "no application form on this page" sentence for the mode control, and
      // `primaryRefused` stops withholding Start fill. The user was already
      // standing on the step; the page has just become able to answer it.
      //
      // WHAT USED TO BE HERE: a re-run of `shouldLoadApplications` +
      // `loadApplications`, because that gate read `hasForm` and `loadContext`
      // had evaluated it once, on the way past, while the answer was still no.
      // The gate no longer reads it, and the flip can only move the stage AWAY
      // from Job (into `fill`) — never into it — so that call could not fire
      // any more. A call that cannot fire under a comment calling itself the
      // whole point is worse than no call: it reads as the mechanism keeping
      // the picker alive, and the picker no longer needs one.
      render();
      return;
    }
  }

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  /** The posting on the page, for the Job stage's editable preview.
   *
   * The same door `loadHasForm` uses and for the same reason: extraction is a
   * page function and this document is in no page. `extract_job_posting` reads
   * the TOP frame only — a posting's JSON-LD is in the top document, and the
   * subframes are the application FORM's business, not the posting's — which
   * is exactly what `panel_frame0` addresses.
   *
   * A failure is not a note and not a fault. The panel asked the page a
   * question about itself and got nothing; three empty boxes say that, and they
   * are also still typeable, so the user is not stuck with our silence. A
   * sentence in the note slot would spend the panel's one line on a page that
   * simply is not a job posting — which is most pages.
   *
   * ASKED MORE THAN ONCE since the SPA re-ask: this is the first rung and
   * `retryPosting` is the rest of the ladder. `landPosting` owns every write on
   * both paths, including this one, so the first answer and the last are
   * governed by exactly the same rule.
   */
  async function loadPosting(token) {
    const posting = await askPostingPrepared(token);
    if (!current(token)) return;
    // The first answer lands on a preview that is still null, so it always
    // lands — including when it found nothing, which is what paints the empty
    // form on the pages that are not postings.
    if (landPosting(previewFrom(posting))) render();
    // NOT AWAITED, for `retryHasForm`'s reason: `loadContext` awaits this
    // function to settle the Job stage, and the ladder spans seven seconds.
    retryPosting(token);
  }

  /** The one extraction ask, so the first attempt and every retry are the same
   * message read the same way — `askDetect`'s twin, and split out for the same
   * reason: two copies of a silence-is-nothing rule would eventually disagree
   * about what a page that did not answer means. */
  async function askPosting() {
    try {
      return await ask("panel_frame0", {
        tabId: card.tabId, message: { type: "extract_job_posting" },
      });
    } catch (_) {
      return null;
    }
  }

  /** Ask the page for its posting, and if it does not answer, put our scripts
   * there and ask once more. The one ask both the first attempt and every retry
   * rung go through, so the cure for a silent tab is not something only the
   * first attempt gets.
   *
   * SILENCE IS NOT AN ANSWER ABOUT THE PAGE — it is an answer about our reach
   * into it — and it is the one failure on this path the panel can do something
   * about. `preparePage` holds the once-per-page bound, so a page that never
   * answers is injected into once and asked three more times, not injected into
   * four times.
   */
  async function askPostingPrepared(token) {
    const answer = await askPosting();
    if (answer !== null || !current(token)) return answer;
    if (!await preparePage(token) || !current(token)) return null;
    // The scripts that could not answer a moment ago are there now.
    return await askPosting();
  }

  /** Put this extension's content scripts into the bound tab — ONCE per page —
   * and say whether asking it again is worth anything.
   *
   * WHY THIS EXISTS, and it is not the SPA case. An MV3 extension that is
   * reloaded (every install, every update, and every reload during a fix round)
   * orphans the content scripts in every tab that is already open: the frames
   * are still there, nothing in them answers, and `panel_frame0` comes back
   * empty. The page is fully rendered and the panel says "No job description
   * found on this page" over a visible JD, forever, because no schedule can
   * out-wait a script that is not running (elevancehealth.wd1 and philips.wd3,
   * live 2026-08-19, on pages that had extracted correctly earlier the same
   * day). `chrome.scripting.executeScript` is the only cure, and
   * `panel_prepare` is the door to it that already exists.
   *
   * WHAT CHANGED IN THE ARGUMENT, stated because `loadHasForm` above spent a
   * paragraph refusing exactly this. That paragraph was about preparing
   * SPECULATIVELY — on every tab switch, before asking, to buy an answer we
   * usually already have — and that cost is still refused: the first ask of any
   * page still goes out cold. This fires only AFTER a page has failed to
   * answer, at most once per page, and only on a page we are allowed to inject
   * into. What it costs on the ordinary web is nothing at all, because the
   * ordinary page answers.
   *
   * THE THREE BOUNDS, all of them here rather than at the call site so a second
   * caller cannot lose one:
   * - `card.prepared` — one injection per page, whatever asks for it, and it is
   *   set BEFORE the await so two loaders in flight cannot both spend it;
   * - `isWebPage` — no injecting into `chrome://`, the PDF viewer or a new tab,
   *   which is `onTab`'s own rule about where this extension has business;
   * - `current(token)` on the way out — an injection that finishes after the
   *   user has switched tabs must not tell the caller to re-ask, because the
   *   re-ask would name the tab they left.
   *
   * A REFUSAL IS NOT A FAULT and never a note: "we could not put our scripts in
   * that tab" is a fact about our reach, and what the user sees instead is the
   * Job stage's sub line saying the panel cannot see this page — which is the
   * honest sentence, and one they can act on by reloading the tab.
   *
   * TWO CALLERS, `askPostingPrepared` and `askDetectPrepared`, and the second
   * one closes the gap this paragraph used to name: a posting is only read at
   * the Job stage, so an orphaned tab that reaches any other stage was never
   * injected into and its form verdict stayed a silence-shaped `false`
   * forever. The 2026-08-19 stage change made that reachable for every user
   * with a base armed, which is the evidence the fix was waiting for. The
   * always-on cost the older note feared is not paid, because the trigger is a
   * SILENCE and not a `false`: an ordinary form-less page answers, and an
   * answer spends no injection. The two callers cannot double-spend one
   * either — `card.prepared` is set here, before the await, whoever asks.
   */
  async function preparePage(token) {
    if (card.prepared || !isWebPage(card.url)) return false;
    card.prepared = true;
    try {
      await ask("panel_prepare", { tabId: card.tabId });
    } catch (_) {
      return false;
    }
    return current(token);
  }

  /** How much posting an extraction actually found, in characters.
   *
   * The ordering behind "a better answer replaces a worse one", and it is
   * deliberately crude: the panel cannot judge whether one JD is more CORRECT
   * than another, but it can tell a shell from a posting. A Workday page caught
   * mid-render answers with its own chrome rather than with nothing —
   * `extractJobPosting` falls back to `document.body.innerText` (agent.js:54),
   * so the early answer is usually a small WRONG one — and the answer that
   * arrives once the description is up is thousands of characters longer. A
   * rule that only replaced an EMPTY preview would therefore miss the live case
   * entirely.
   *
   * The three header fields count as well as the description, because a
   * header-first render (title up, JD still fetching) is a real intermediate
   * state on exactly these pages. `source` does not count here — it is
   * provenance, not posting — and provenance is a SEPARATE comparison that runs
   * before this one: see `sourceRank`. */
  const postingWeight = (preview) =>
    ["text", ...PREVIEW_FIELDS.map(([key]) => key)]
      .reduce((total, key) => total + String(preview?.[key] ?? "").trim().length, 0);

  /** How much an extraction's PROVENANCE is worth, which outranks how much of
   * it there is.
   *
   * WHY THIS BEATS SIZE, and it is a live race rather than a theory: on a page
   * carrying a JSON-LD posting, `extractJobPosting` returns the described
   * posting (`json-ld`); a retry that lands a moment later on a page whose
   * markup has shifted can fall through to the visible-content branch and
   * answer `body`, which is `document.body.innerText` — the posting PLUS the
   * nav, the cookie bar and the footer. That answer is strictly LONGER and
   * strictly worse: it wipes the three header boxes the JSON-LD filled and
   * reports the noise as "JD grabbed · 171 words". Size cannot tell those
   * apart; where the extractor found it can.
   *
   * FOUR RANKS, and the bottom one is not a source at all. `unreachable` is
   * what `previewFrom` writes when the ask came back with nothing, so ANY
   * answer from the page outranks it — including an answer that found no
   * posting, which is how "the companion cannot see this page" stops being a
   * sentence the panel cannot take back (a page that has started talking to us
   * has, at minimum, told us that much). An answered source we do not recognise
   * ranks with `body`: it is an answer, and nothing more is claimed for it. */
  const SOURCE_RANK = { "json-ld": 3, content: 2, body: 1 };
  const sourceRank = (preview) =>
    preview?.source === UNREACHABLE ? 0 : (SOURCE_RANK[preview?.source] ?? 1);

  /** Write an extraction into the preview, or refuse — the ONE place that
   * decides whether an answer from the page may land, first ask and retries
   * alike. Returns whether it wrote, which the ladder reads as one half of its
   * stop condition.
   *
   * THE REFUSALS, in the order they are asked, because they are different facts
   * and the `card.preview !== null` guard this replaces conflated the first two:
   *
   * - THE USER HAS TYPED. Their characters win over any answer, however good: a
   *   re-ask landing while someone corrects a title would take the correction
   *   back out from under them mid-word. `previewTyped` is written by
   *   `editPreview` alone, so this is asking the real question rather than
   *   inferring it from a field being populated. The refusal is WHOLE — a
   *   partial merge would rewrite the boxes around a cursor.
   * - THE PROVENANCE IS WORSE. A lower-ranked answer never lands whatever its
   *   size, and a higher-ranked one always does whatever its size. `sourceRank`
   *   carries the live race this exists for.
   * - AT EQUAL PROVENANCE, THE ANSWER IS NOT BIGGER. An SPA navigating out from
   *   under the ladder, a frame mid-teardown, a read that caught a re-render —
   *   all come back lighter, and any of them would otherwise blank a preview
   *   that was already right.
   *
   * Not `>=` by accident: an answer of EQUAL weight AND equal provenance is a
   * page that has settled, and rewriting the store with a same-sized rewording
   * would repaint the inputs for nothing. */
  function landPosting(preview) {
    if (card.previewTyped) return false;
    if (card.preview !== null) {
      const rank = sourceRank(preview);
      const standing = sourceRank(card.preview);
      if (rank < standing) return false;
      if (rank === standing
          && postingWeight(preview) <= postingWeight(card.preview)) return false;
    }
    card.preview = preview;
    return true;
  }

  /** The posting's own ladder: `retryHasForm`'s shape, `PAGE_RETRY_MS`'s
   * cadence, and its own stop condition (that constant carries why the two
   * loops stay separate).
   *
   * IT RUNS ON EVERY JOB-STAGE PAGE rather than only on the ones that answered
   * nothing, and that is the one place it diverges from its sibling. A form
   * verdict is a boolean, so a yes is the whole answer and a retry after one
   * would be asking a question already answered; a posting is not — the first
   * answer on a slow SPA is routinely a NON-EMPTY wrong one (see
   * `postingWeight`), so "it answered" says nothing about whether it answered
   * with the posting. The cost of that choice is one extra page read, 1s after
   * bind, on a page that had already answered completely: the rung after it
   * comes back no better and the ladder stops there.
   *
   * WHEN A REFUSAL MEANS STOP, and this is the correction that made the ladder
   * reach its own last rung. "The answers stopped improving" is only evidence
   * that the page has settled once the page has given us SOMETHING; while the
   * preview is still empty, a repeated empty answer is not a page with nothing
   * on it, it is a page that has not rendered yet — which is the entire
   * premise. The first version stopped on the first non-improving rung, so a
   * JD that appeared between 1s and 2s was never seen: two empties in a row
   * ended the schedule at 1s and the live Itron timeline failed exactly as
   * before. So: keep climbing while nothing real has landed, stop as soon as
   * something has and the page stops improving on it. A page that answered
   * completely at once still costs exactly one extra read.
   *
   * SILENT, like everything else on this path. A page that never grows a
   * posting ends exactly where it ends today — an empty form, no note — because
   * most of the web is not a job posting and saying so on each of them would
   * spend the panel's one line on our own looking. What it costs is the full
   * schedule of reads on a Job-stage page that never answers with anything,
   * which is the price of catching the ones that answer late. */
  async function retryPosting(token) {
    for (const delay of PAGE_RETRY_MS) {
      await sleep(delay);
      // Before the ASK, for `retryHasForm`'s reason: `askPosting` names
      // `card.tabId` and that field has already moved, so a schedule that woke
      // up unchecked would aim tab A's re-asks at whatever tab the user landed
      // on. `previewTyped` sits beside it because a refusal is already certain
      // once someone is typing, and a page read whose answer cannot be used is
      // the always-on cost this whole path is written around.
      if (!current(token) || card.previewTyped) return;
      const posting = await askPostingPrepared(token);
      // And again before the WRITE, which is the file's standing rule — the
      // user is free to switch tabs while an extraction is in flight, and this
      // one is in flight for as long as the page takes to answer.
      if (!current(token)) return;
      if (landPosting(previewFrom(posting))) {
        render();
        continue;
      }
      // REFUSED — and what that means depends on whether anything real is in
      // the preview yet. With a posting in hand, a refusal is the page saying
      // the same thing twice: it has settled, and asking again buys nothing.
      // With the preview still empty, it is a page that has not rendered yet,
      // which is the case this whole ladder exists for — so keep climbing.
      // (A refusal caused by the user typing lands here too, and the check at
      // the top of the next rung returns before spending an ask on it.)
      if (postingWeight(card.preview) > 0) return;
    }
  }

  /** Read the posting again after the page reloaded under us — the other half
   * of the sentence that tells the user to reload the tab.
   *
   * THE DEAD END THIS CLOSES: an orphaned tab answers nothing, the sub line
   * asks for a reload, the user reloads — and nothing happens. The reload
   * changes no url, so it never reached `onTab`; the ladder ran out seconds
   * ago; and the fresh content scripts sit there with nobody asking them
   * anything. The advice was sound and the panel was not listening for it being
   * taken.
   *
   * DELIBERATELY NARROWER THAN "the preview is empty", which is where this
   * started. Most of the web answers with a posting-less page — weight 0, but
   * ANSWERED — and re-running the ladder for every one of them would double the
   * page reads of every ordinary navigation, since `complete` also arrives at
   * the end of a load `onTab` has already handled. Only an UNREACHABLE preview
   * gets this: the page told us nothing at all, which is the one state a reload
   * plausibly fixes and the only one the copy is about. `preview === null` is
   * excluded for the same reason — a load still in flight is not a dead end.
   *
   * A FULL LADDER rather than a single ask, because a reloaded page is a page
   * that is rendering: the SPA case applies to it exactly as it applies at
   * bind, and `loadPosting` is that whole arrangement already. It carries the
   * generation discipline and the typed guard with it, so this adds neither.
   */
  async function healPosting(token) {
    if (!current(token) || card.previewTyped || !isWebPage(card.url)) return;
    if (card.preview === null || sourceRank(card.preview) !== 0) return;
    await loadPosting(token);
  }

  /** The scores this job already has, ranked against the base-resume library.
   *
   * A READ, and cheap: `GET /api/ats-scores?job_id=`
   * returns whatever has already been computed and computes nothing. Failure is
   * silent on purpose — a panel without the ranking is the panel that shipped
   * at Task 5, so an outage costs the ordering and nothing else.
   */
  async function loadBaseScores(token) {
    // The library first: the ranking is OVER base resumes, and the default
    // pick — which is what the identity card's "Before" ring reads — comes out
    // of that list.
    await loadBaseResumes(token);
    if (!current(token) || !card.job) return;
    let rows;
    try {
      // Into a LOCAL first, and the store only past the guard. `card.scores =
      // await …` writes at settle time, which is before any check can run: a
      // read still in flight for tab A then lands in tab B's store, and the
      // rows do not even look wrong — `compositeFor` keys a base row on the
      // resume SLUG, which is job-independent, so a stale row resolves happily
      // against tab B's default base and renders as tab B's number. `cardFacts`
      // reads the same array for `hasScores`, so it also completes a stage tab
      // B never reached. Nothing repaints at the moment of the bad write, which
      // is what makes it nasty: it sits in the store until the user's next
      // click and surfaces then, far from anything that would explain it.
      rows = await api(`/api/ats-scores?job_id=${encodeURIComponent(card.job.id)}`);
    } catch (_) {
      if (!current(token)) return;
      card.scores = null;   // "we do not know", which is what null means here.
      render();
      return;
    }
    if (!current(token)) return;
    card.scores = rows;
    // Move the selection onto the best resume, unless the user has picked one:
    // a ranking that quietly overrode an explicit choice would be the panel
    // arguing with them. It moves `baseSlug` and NEVER `baseSelected` — the
    // Score stage completes when the USER picks (`pickBase`), and a panel that
    // ticked it off by ranking would be answering on their behalf.
    if (!card.baseSelected) {
      const best = rankBaseResumes(card.resumes, card.scores)[0];
      if (best && best.score !== null) card.baseSlug = best.slug;
    }
    render();
  }

  /** The base-resume library, asked for once per panel rather than once per
   * tab: it is not a fact about a page, which is why `resetPageFacts` keeps it.
   * `resumesRequest` is a latch held as a promise, so two quick tab switches
   * spend one round trip rather than two. */
  let resumesRequest = null;

  async function loadBaseResumes(token) {
    if (card.resumes === null) {
      try {
        resumesRequest ??= api("/api/base-resumes");
        // The ONE settle-time write in this file that is deliberate, and it is
        // safe for a reason that does not generalise: this list is
        // TAB-INDEPENDENT. The library is the same rows whichever posting the
        // user is looking at — `resetPageFacts` keeps it for exactly that
        // reason — so an answer arriving after a tab switch is not a stale fact
        // about the previous page, it is the same fact arriving late. Nothing
        // reads it as a claim about a posting. `card.scores`, which IS read
        // that way, lands in a local and waits for the guard.
        card.resumes = await resumesRequest;
      } catch (_) {
        resumesRequest = null; // a transient failure may retry on the next tab.
        return;
      }
    }
    if (!current(token)) return;
    // The first row is the default, and it is VISIBLE rather than implied:
    // both Quick tailor and the base-as-is shortcut spend it. Per PAGE, unlike
    // the list itself — `baseSlug` is a choice about the posting in front of
    // the user, so `resetPageFacts` clears it and this re-establishes it.
    //
    // `if (!card.baseSlug)` and NOT an unconditional assignment, which is the
    // shape this started as and the shape it must not go back to: this load can
    // land after a session restore, and assigning here would overwrite the slug
    // the user actually picked with the library's first row.
    // `?.[0]` and not `[0]`: `card.resumes` is `[]` for a user with no base
    // resumes yet, and a panel that threw on the empty library would take the
    // whole load down for the one user who needs the empty state most.
    if (!card.baseSlug) card.baseSlug = card.resumes?.[0]?.slug ?? null;
    render();
  }

  /** Recent drafts, asked for once per panel rather than once per tab: the
   * list is not a fact about a page, which is why `resetPageFacts` keeps it.
   *
   * THE WIRE is `GET /api/applications?status=draft`, and both halves are
   * decisions:
   *
   * - `status=draft`, because this picker is drafts the user might still want
   *   to fill. Applied rows would be an offer to re-fill a form they have
   *   already submitted. (A "change target across every status" picker is a
   *   different feature and would need a different sentence on the row.)
   * - Lazy: loaded when Job is active and nothing has matched the page, which
   *   is the only state that renders the list — and once per panel, not once
   *   per tab, which is what the latch below is for.
   *
   * THE SETTLE-TIME WRITE is `loadBaseResumes`'s exception, taken for the
   * same reason: this list is TAB-INDEPENDENT, so an answer arriving after a
   * tab switch is the same fact arriving late rather than a stale claim
   * about a posting. Anything read as a fact ABOUT the posting still follows
   * the three-step generation rule above.
   */
  let applicationsRequest = null;

  /** WHEN THE OFFER IS WORTH A ROUND TRIP: nothing is armed on this page, and
   * the user is standing at Job — which is to say the panel has nothing of its
   * own to show them here and the alternative to offering is guessing.
   *
   * NO FORM GATE, and that is a correction the field made rather than a
   * loosening. `hasForm === true` used to sit at the front of this, on the
   * reasoning that a posting you are only reading is not a reason to pick a
   * target. Workday falsified it (elevancehealth.wd1, console-verified
   * 2026-08-18): every wizard step is its own url so `/api/jobs/match` is
   * silent on all of them, the JD is right there in the DOM, and `hasForm` at
   * bind-time is false — the SPA has not rendered, or the step is a login, or
   * the form finally appears with no url change to re-bind on. So the picker
   * was hidden on precisely the flow it was built for while rendering happily
   * on the fast ATSes that never needed it. The gate protected nothing the two
   * remaining conjuncts do not: an armed page never asks, and a matched page
   * never asks.
   *
   * THOSE TWO ARE ONE CONDITION TODAY, and saying so is better than letting
   * the next reader discover it with a mutation. Everything that writes
   * `application` writes `match: "exact"` beside it — `applyMatch` (the route
   * answers `none` or `exact`, never an application without one),
   * `restoreSession` and `pickApplication` — so `stage === "job"` already
   * implies nothing is armed, and dropping the null check changes no
   * observable behaviour or test. It stays because it is the RULE ("only when
   * we have nothing of our own to show") rather than an inference drawn from
   * three other files, and because the cost of that inference failing later is
   * a fetch nobody wanted.
   *
   * AND AN OFFER IS SAFE WHERE A GUESS IS NOT — the design line this whole
   * picker is built on. Naming a draft is the USER'S claim about the page, not
   * ours; the panel is not asserting that this page is fillable, it is asking
   * which application the user is here about. A wrong offer costs a glance. A
   * wrong guess would autofill somebody else's form.
   *
   * THE `http(s)` GUARD IS `onTab`'s, not restated here. Both callers descend
   * from it — `loadContext` is the only thing that calls this, and it is only
   * reached past that early return — so a `chrome://` tab never reaches this
   * function at all and a conjunct for it would be an `if` that cannot fail,
   * which reads as a guard while guarding nothing. The rule lives at the door;
   * `test_a_chrome_page_is_offered_nothing_and_asks_for_nothing` pins it.
   */
  function shouldLoadApplications(store) {
    return store.application == null
      && stageFor(cardFacts(store)).stage === "job";
  }

  async function loadApplications(token) {
    if (card.applications !== null) return;
    try {
      applicationsRequest ??= api("/api/applications?status=draft&limit=100");
      const rows = await applicationsRequest;
      card.applications = Array.isArray(rows) ? rows : [];
    } catch (_) {
      applicationsRequest = null;
      return;
    }
    if (!current(token)) return;
    render();
  }

  // ---------- the actions' seam: the handle they write the store through -----
  //
  // The actions themselves are `panel/actions/` now. What is left here is the
  // door they go through, and it is the whole of the cut: `card` stays
  // module-private in this file, and what crosses the boundary is a handle with
  // ONE write function on it.
  //
  // WHY NOT `stageContext`'s SEAM, since this file already had one. A stage
  // body reads a per-render snapshot and returns — facts in, elements out. An
  // action is a SEQUENCE that spans awaits: it paints `busy`, opens a POST,
  // writes four fields and a sentence when the answer lands, and then re-runs a
  // load which writes the store again. Three things follow, and each of them
  // rules out the "return a patch and let the caller apply it" shape:
  //
  //   1. a snapshot goes stale INSIDE an action — the four loaders are writing
  //      to this store for the whole length of a POST — so `read()` is a
  //      function an action calls again after every await, not a fact handed to
  //      it once;
  //   2. the writes are interleaved with the awaits, so one returned patch is
  //      either applied too late (losing the `busy` paint the user is watching,
  //      and the note that the re-load must not overwrite) or it is a
  //      generator, which is a much heavier seam than this buys;
  //   3. the generation check has to sit AT each write rather than once at the
  //      end — `duringAction` guards both of its limbs and `loadContext` guards
  //      again inside — and a caller applying a patch past a single check would
  //      move the guard away from the writes it protects.
  //
  // So: a handle. `write(patch)` is the only way anything outside this file
  // changes the store, it names its keys, and it REFUSES a key the store does
  // not have — which is what a typo in another file costs here instead of a
  // field nothing reads. The rest of the handle is what an action needs to be
  // one: the generation, the panel's one backend door, the two flows an action
  // ends with, and the two builders it shares with the rest of the surface.

  /** THE HANDLE: everything `panel/actions/` may read, write, ask and run.
   *
   * FOUR GROUPS, and which one a new entry belongs to is the whole rule:
   *
   * - THE STORE AND THE GENERATION — `read`, `write`, `render`, `token`,
   *   `current`. `read()` is a fresh shallow COPY, not the store: an action can
   *   see everything this panel knows (they are this file's own code, moved)
   *   and can change none of it except through `write`. Shallow, so the nested
   *   objects it hands back are shared — treat all of it as read-only.
   *   `token`/`current` are the generation rule's two halves, exposed because
   *   an action's guard belongs at its own writes.
   * - THE PANEL'S BOUND-TAB DOORS — `api`, `broadcast`, `prepare`,
   *   `telemetry`. Four messages and no more, and every one of them is bound
   *   HERE to the tab this panel is following: `card.tabId` never crosses the
   *   boundary, so an action cannot name a tab. `api` is the single-fetch-site
   *   rule (the actions files get the one door this file uses and never a
   *   `fetch` of its own); `broadcast` and `prepare` are the fill's fan-out and
   *   its one sanctioned injection; `telemetry` is fire-and-forget and stamps
   *   the page host from the same bound url.
   * - THE FLOWS an action ends with — `remember` writes the session entry,
   *   `loadContext`/`loadBaseScores` are the two re-reads that CONFIRM what an
   *   action just claimed. They take the action's own token, which is why they
   *   are passed rather than re-derived.
   * - `build` — the shared builders, for `stageContext`'s reason: `plural`
   *   because "1 skills" is the sentence that tells a user nobody read the
   *   copy, and `ingestBodyFrom` because it is the inverse of `previewFrom` and
   *   the pair is read (and tested) together, so it stays here with its twin.
   *
   * Built ONCE, at load, and handed to the factory — not per render like
   * `stageContext`. A body is rebuilt on every repaint; an action is a function
   * bound to a click handler that outlives them.
   */
  function actionStore() {
    return {
      read: () => ({ ...card }),
      write: (patch) => {
        for (const [key, value] of Object.entries(patch)) {
          // Refused rather than added. An unknown key would otherwise become a
          // field of the store that `resetPageFacts` never clears, `cardFacts`
          // never reads and no render ever paints — a write that looks like it
          // worked, which is the failure this surface keeps naming.
          if (!Object.hasOwn(card, key)) {
            throw new Error(`panel store has no field ${JSON.stringify(key)}`);
          }
          card[key] = value;
        }
      },
      render,
      token: () => generation,
      current,
      api,
      // The tab is bound here, in all three, and never passed in. `fanoutTab`
      // verifies WHO may name a tab and cannot verify WHICH — that is the
      // panel's binding discipline, and an action that could supply its own
      // `tabId` would be a second place that discipline has to hold.
      broadcast: (message) => ask("page_broadcast", { tabId: card.tabId, message }),
      prepare: () => ask("panel_prepare", { tabId: card.tabId }),
      /** The attach's door, and it is a FIFTH bound-tab message rather than a
       * branch of `broadcast` because it is not one: `attach_pdf` makes the SW
       * fetch the PDF and fan out the bytes itself, so the panel never holds
       * them and they cross ONE message boundary instead of two.
       *
       * `path` still goes through `assertBackendPath` on the far side, and the
       * receiving frames still go through `frameMayReceiveUserData` — a résumé
       * is the user's PII and is gated exactly as a fill is. The tab is bound
       * here like the other three, so an action cannot name one. */
      attachPdf: (path, filename, expect) =>
        ask("attach_pdf", { tabId: card.tabId, path, filename, expect }),
      /** The page's upload-box count, asked FRESH.
       *
       * The same frame-0 detect `loadHasForm` runs, exposed because the attach
       * needs it at a second moment: the offer is made on a count taken at bind
       * time, and when the write comes back with nothing the interesting
       * question is whether the page has changed underneath it. Asking again is
       * how the panel turns "nothing attached" into a sentence that says why.
       *
       * Bound to this panel's tab like every other door here, and it carries no
       * user data in either direction — it is a count of controls. */
      detectFileInputs: async () => countFileInputs(await askDetect()),
      // Fire-and-forget and swallowed, which is telemetry's rule everywhere:
      // it may never surface an error or delay a fill. The opt-in check and the
      // key scrub are the service worker's — this is only the hand-off.
      telemetry: (action, observations) => {
        ask("telemetry", { action, observations, page_host: hostOf(card.url) })
          .catch((err) => console.warn("[maestro-cs] telemetry failed:", err));
      },
      remember: rememberSession,
      loadContext,
      loadBaseScores,
      // `evidenceFrom` rides here for `ingestBodyFrom`'s reason: the Track
      // action's PATCH answers with the same shape `loadContext`'s GET does, so
      // both fold it through ONE function rather than each reading `pdf_path`
      // and `applied_at` its own way.
      build: { plural, ingestBodyFrom, evidenceFrom },
    };
  }

  /** The actions, bound to that handle. Read at load, so a panel.html that
   * forgot the `<script>` tag fails on boot rather than rendering a rail whose
   * every primary throws on the first click — the quiet version of the same
   * fault, and the one a user would have to notice for us. */
  const { addJob, pickApplication, unpickApplication, dropDeletedApplication,
          scoreAllBases, quickTailor, useBaseAsIs,
          stopUsingBaseAsIs, startFill,
          attachResume, submitAnswer, askQuestion, setStatus, trackThis } =
    ns.panelActions(actionStore());

  /** The one primary per stage, as BEHAVIOUR — keyed on the same strings as
   * `STAGE_LABELS`, which is what keeps the label and the action from drifting
   * apart. Every entry in `STAGE_LABELS` has one here, and that is now an
   * invariant rather than a coincidence: the placeholder that used to cover the
   * difference is gone with the last label that needed it (see `actionButton`),
   * so a label without a run is a button that throws.
   *
   * `resume` runs the SAME function the stage body's Quick limb fires, and the
   * two are deliberately one behaviour rather than two: the fork is where the
   * user makes the choice, the footer is the panel's standing promise that
   * there is exactly one primary and it is always in the same place. One
   * function means one `busy` key, so pressing both cannot open two tailors,
   * and the labels are the same words so nobody reads them as two features. */
  const STAGE_RUN = { job: addJob, score: scoreAllBases, resume: quickTailor,
                      fill: startFill };

  /** Remove the keys nothing reads any more. Once per panel open, and it is
   * the only thing in this file that touches them.
   *
   * READ FIRST, REMOVE ONLY IF SOMETHING IS THERE, which is what keeps this
   * from being a write on every boot: `chrome.storage.sync` is not involved,
   * but `local` writes still hit the disk and fire `onChanged`, and almost
   * every boot after the first has nothing to sweep. The read is one call
   * against a fixed key list.
   *
   * NOT AWAITED AND NOT GUARDED, deliberately. Nothing downstream reads these
   * keys, so a sweep that loses its race with the rest of boot costs one
   * retry on the next open, and a sweep that throws costs nothing at all —
   * whereas letting either fail the boot would cost the whole panel over
   * housekeeping. The `catch` is why the failure still reaches a log.
   *
   * DELETE THIS whole function once no profile can plausibly still hold one of
   * these — it is a migration, and a migration that outlives its population is
   * just code. The keys it names are documented at `ORPHAN_KEYS`. */
  async function sweepOrphanKeys() {
    try {
      const stored = await chrome.storage.local.get(ORPHAN_KEYS);
      const found = ORPHAN_KEYS.filter((key) => stored[key] !== undefined);
      if (found.length) await chrome.storage.local.remove(found);
    } catch (err) {
      console.warn("[maestro-cs] orphan-key sweep failed:", err);
    }
  }

  /** Settings first so the header link knows where the web app is, then paint,
   * then bind — a panel that cannot reach the SW still opens, on defaults,
   * instead of staying blank. */
  async function boot() {
    sweepOrphanKeys();
    // `null` when the ask failed, and nothing here treats that as an error:
    // `readSettings` carries why, and every reader below already has a rule for
    // a settings object it does not have.
    card.settings = await readSettings();
    // The remembered fill mode, through the ONE settings path. `"rules"` is
    // the only value that turns the model off, so anything else — a missing
    // key, a stored string from an older build, a settings ask that came back
    // without it — means the assist pass. The narrowing is the choice; a
    // value we cannot read is not a user who made it.
    card.fillMode = card.settings?.fillMode === "rules" ? "rules" : "assist";
    render();
    await bindActiveTab();
  }

  ns.panel = { railModel, deepLink, stageAction, resetPageFacts, applyMatch,
               previewFrom, ingestBodyFrom, evidenceFrom, sessionEntryFrom,
               actionStore };
  // Nobody awaits the boot, so an unhandled rejection here would leave a blank
  // panel and an empty log — the exact report sw.js's registration carries its
  // own `.catch` for ("the icon does nothing").
  boot().catch((err) => {
    card.fault = { text: String(err?.message ?? err), error: true };
    render();
  });
})();
