/* Maestro CS Companion — the Fill stage's body.
 *
 * One of five files behind `ns.panelStages`; `panel/stages.js` is the joiner
 * and carries the whole contract. Read it before adding anything here.
 *
 * THE RULE, restated because a file that only POINTS at it is a file that
 * half-remembers it: NOTHING HERE REACHES FOR ANYTHING. No `card`, no `chrome`,
 * no `document`, no network — everything a body may read is on the CONTEXT it
 * is passed (`stageContext()` in panel.js is that contract's definition), and
 * firing one of its callbacks is the only way it changes anything.
 *
 * ONE EXCEPTION, and it is the same one every file in this directory may make:
 * `shared/policy.js` is read off the namespace rather than handed in, because
 * what may never be filled is a DECISION with a single source rather than a
 * fact about this render. A second opinion about it, carried on the context,
 * is how a password box ends up with an answer in it.
 *
 * THE WHOLE FILL STAGE IS HERE, and that is one subject rather than three: the
 * progress rows, the still-open list with its inline pause rows, and the QnA
 * drawer are all rendered by `fillBody` and all belong to one run. The ACTIONS
 * behind them are cut three ways (`panel/actions/fill.js`, `…/pause.js`,
 * `…/qna.js`) because a round trip is a different kind of thing from a render —
 * see `panel/actions.js`'s header for why the two arrangements differ here.
 *
 * TWO CONTROL-SHAPE TRADES ARE CHOICES, not oversights, and they live in the
 * pause row. A `textarea`-kind field is answered through a one-line `<input>`,
 * and a `select`/`radio` is answered by TYPING rather than by picking: the
 * writer matches the typed string against the page's own options, which is why
 * the row prints them. Both are the same bet — the pause row is a chip in a
 * 400px rail, and a textarea or a rebuilt option list in it would be a second,
 * worse copy of the control that is already on the page a jump away. Revisit
 * either when the residue is shown somewhere with room, never because the
 * shapes look mismatched.
 *
 * Everything dynamic goes through `textContent` (the handed-in `node` is the
 * only way anything here builds an element). A field label and a backend error
 * are attacker-influenced text on an ATS that lets employers write their own
 * forms.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  /** The two passes, in the order the user is asked to choose between them:
   * narrow first, then the one that answers more of the form. `assist` is the
   * default (sw.js's `DEFAULTS`), so this order is NOT "selected last" — it is
   * "least to most", which is how a control that can send text to a model
   * should read. */
  const FILL_MODES = [["rules", "Rules only"], ["assist", "Rules + AI assist"]];

  /** Rules only / Rules + AI assist.
   *
   * A RADIOGROUP on real buttons, `baseRow`'s shape and its reasoning: the
   * segment IS the control, and a hidden input with a label wrapped round the
   * same box would be two elements where one does. `aria-checked` rather than
   * the tint alone, because "which pass is about to run" is the one thing a
   * user must not have to infer from a background colour.
   *
   * OUT OF REACH WHILE A FILL RUNS, `actingLimb`'s rule: the mode is read once,
   * at the top of the action, so a segment pressed mid-run would change the
   * label and not the run — a control that lies about what it did, which is
   * worse than one that is briefly unavailable.
   */
  function modeControl({ facts, act, build }) {
    const seg = build.node("div", "seg");
    seg.setAttribute("role", "radiogroup");
    seg.setAttribute("aria-label", "Fill mode");
    for (const [mode, label] of FILL_MODES) {
      const on = facts.fillMode === mode;
      const button = build.node("button", on ? "on" : null, label);
      button.type = "button";
      button.setAttribute("role", "radio");
      button.setAttribute("aria-checked", on ? "true" : "false");
      button.disabled = facts.busy === true;
      button.addEventListener("click", () => act.setFillMode(mode));
      build.attach(seg, button);
    }
    return seg;
  }

  /** One progress row: a state mark, what it is about, and the count.
   *
   * The mark is an emoji and therefore reaches nobody using a screen reader on
   * its own, so it carries the state IN WORDS — the rail's numeral does exactly
   * this, for exactly this reason.
   */
  function progressRow({ build }, [mark, state], name, detail) {
    const row = build.node("div", "prog");
    const st = build.node("span", "st", mark);
    st.setAttribute("aria-label", state);
    return build.attach(row, st, build.node("span", null, name),
                        build.node("span", "n", detail));
  }

  const DONE = ["✅", "done"];
  const OPEN = ["🟡", "needs you"];
  const SKIPPED = ["⏸", "skipped"];

  /** What the rule pass did, from `reconcileFill`'s own counts.
   *
   * NO SECOND TABLE. The buckets are `shared/decisions.js`'s, so this row
   * reads them and adds nothing. `already` is here for the reason it exists at all: "0 filled" over
   * a visibly full form was a lie on a re-run, and a field that already held
   * the right answer is its own count rather than a failure.
   */
  function profileRow(ctx, fill) {
    const { counts } = fill;
    const parts = [
      `${counts.filled} filled`,
      counts.corrected ? `${counts.corrected} corrected` : null,
      counts.already ? `${counts.already} already filled` : null,
      counts.notStuck ? `${counts.notStuck} didn’t stick` : null,
    ].filter(Boolean);
    const wrote = counts.filled + counts.corrected;
    return progressRow(ctx, counts.notStuck ? OPEN : wrote ? DONE : SKIPPED,
                       "Profile fields", parts.join(" · "));
  }

  /** What the remainder pass did, and what it left.
   *
   * BOTH HALVES COME OFF THE RUN, which is the whole honesty of this row: the
   * written count is the engine's answered qids minus the ones the runner
   * residued, and the open count is the residue plus the essays. Neither is a
   * re-derivation — a row that counted "filled" by re-reading outcome strings
   * would be a second opinion about a question the runner has answered.
   */
  function questionsRow(ctx, { writeResults, residue, essays }) {
    const open = new Set(residue.map((row) => row.qid));
    const written = writeResults.filter((row) => !open.has(row.qid)).length;
    const needsYou = residue.length + essays.length;
    const parts = [
      `${written} filled`,
      // Agreement, not decoration: `plural` exists in this codebase because
      // "1 skills" is the sentence that tells a user nobody read the copy, and
      // "3 needs you" is the same sentence with the verb instead of the noun.
      needsYou ? `${needsYou} ${needsYou === 1 ? "needs" : "need"} you` : null,
    ].filter(Boolean);
    return progressRow(ctx, needsYou ? OPEN : DONE,
                       "Application questions", parts.join(" · "));
  }

  /** Voluntary disclosures, and the ONE thing this row may never do.
   *
   * The answer is the BACKEND's standing consent (`eeo_consent` on
   * `/api/autofill/context`) and there is no local toggle that could turn it
   * on — that is design §R1's rule, and this row is where a user finds out it
   * held. Three states, and they are three different sentences:
   *
   * - consent granted: the count of protected-characteristic fields written;
   * - consent withheld: "skipped — EEO off", which explains a silence that
   *   would otherwise read as a fill that missed a whole section;
   * - no answer at all: "not asked". The endpoint told us nothing about
   *   consent, and reporting that as "off" would be this surface deciding a
   *   question it is not allowed to decide.
   */
  function eeoRow(ctx, fill, consent) {
    if (consent === null) return progressRow(ctx, SKIPPED, "Voluntary disclosures",
                                             "not asked");
    if (consent.enabled !== true) {
      return progressRow(ctx, SKIPPED, "Voluntary disclosures", "skipped — EEO off");
    }
    const filled = fill.eeoFilled.length;
    return progressRow(ctx, filled ? DONE : SKIPPED, "Voluntary disclosures",
                       `${filled} filled`);
  }

  /** "1 upload box" / "3 upload boxes".
   *
   * `plural` (the shared builder) appends a bare "s", which is right for
   * "field" and "skill" and wrong for this word. Teaching the shared builder
   * English irregulars for one caller is a bigger change than saying one word's
   * plural once, here, beside the two lines that use it — and "3 upload boxs"
   * is the sentence that tells a user nobody read the copy, which is the whole
   * reason `plural` exists in the first place.
   */
  const boxes = (n) => `${n} upload box${n === 1 ? "" : "es"}`;

  /** The attach: the tailored PDF into this page's own upload box.
   *
   * OFFERED, NEVER TAKEN. The panel does not attach during a fill and does not
   * attach on a load — a fill writes text a user can read back at a glance, and
   * an upload is a whole document going to an employer. So this is a control
   * and the press is the whole of the decision.
   *
   * THREE STATES OFF ONE NUMBER, and the number is the page's own count of
   * boxes a résumé could go into (`fileInputs`, from the detect pass):
   *
   * - ONE box: the offer, naming the file. Unambiguous, so it is a button.
   * - NONE: nothing at all. Not a disabled button — a control that can never
   *   become pressable on this page is furniture that asks the user to work out
   *   why, and "this page has no upload box" is the ordinary case for most of
   *   the web.
   * - MORE THAN ONE: a sentence and a dead button. The panel cannot tell a
   *   résumé box from a cover-letter box from a transcript box, and putting the
   *   résumé in the wrong one is worse than not offering: the page would look
   *   like it worked. The button stays RENDERED and disabled here — unlike the
   *   zero case — because there IS something to attach and the user needs to
   *   know why the panel is not doing it. A picker is the honest fix and it is
   *   a later round's; this round refuses rather than guesses.
   *
   * AND NOTHING AT ALL WITHOUT A PDF. `pdfReady` is the other gate: an offer to
   * attach a document that has not been rendered is an offer that resolves to
   * an error message, which is the shape of promise this surface keeps refusing
   * to make.
   *
   * ONCE IT HAS HAPPENED the row becomes a report — the same progress-row shape
   * as the rest of this body, because that is what it now is — and it says how
   * many boxes took the file. The count is the engine's readback rather than
   * the number of frames asked, so "1 box" is a box that really holds it.
   * There is no second press: the control is gone, and a re-attach is a page
   * reload away. That is deliberate for this round — the interesting failure is
   * an attach that silently went to the wrong place, and offering to do it
   * again is how a user ends up with two.
   */
  function attachRow(ctx) {
    const { facts, act, build } = ctx;
    if (facts.attached) {
      return progressRow(ctx, DONE, "Resume attached",
                         `${facts.attached.filename} · ${boxes(facts.attached.count)}`);
    }
    if (!facts.pdfReady || facts.fileInputs < 1) return null;
    const many = facts.fileInputs > 1;
    const box = build.node("div", "attach");
    const line = build.node("div", "sub", many
      ? `This page has ${boxes(facts.fileInputs)} — attach your resume by hand `
        + "so it goes to the right one."
      : facts.attachName
        ? `Put ${facts.attachName} in this page's upload box.`
        : "Put your tailored resume in this page's upload box.");
    const button = build.node("button", "save", "Attach resume");
    button.type = "button";
    // `actingLimb`'s rule, and the ambiguity refusal in the same flag: a
    // control that stayed live during a fill would send a document into a page
    // the run is still walking, and one that stayed live over several boxes
    // would make the sentence above it a suggestion.
    button.disabled = facts.busy === true || many;
    // WHY IT IS DEAD RATHER THAN MISSING, said to a screen reader too: a
    // disabled button announces no reason on its own, and the sentence beside
    // it is the reason.
    if (many) button.setAttribute("aria-describedby", ATTACH_NOTE_ID);
    line.id = ATTACH_NOTE_ID;
    button.addEventListener("click", act.attachResume);
    return build.attach(box, line, button);
  }

  /** The id `attachRow`'s refusal sentence carries, for `QNA_BODY_ID`'s reason:
   * two places a few lines apart have to agree on it. */
  const ATTACH_NOTE_ID = "attach-note";

  /** The kinds a pause row can actually WRITE, and the list is the writer's
   * rather than this file's opinion of it.
   *
   * `fillAnswersByQid` (content/open-questions.js) has three limbs: match an
   * option for `select`, click a labelled radio for `radio`, and commit a value
   * for everything else. A `combobox` is a `<button aria-haspopup="listbox">`,
   * and the third limb would set `.value` on a button — so offering an input
   * for one would be this panel taking an answer it cannot deliver, which is
   * worse than saying nothing. It keeps the jump button: the user opens the
   * popover on the page, where the control actually works.
   */
  const ANSWERABLE_KINDS = new Set(["text", "textarea", "select", "radio"]);

  /** May this row be answered from here at all?
   *
   * TWO refusals, and they are different in kind. The policy one is absolute:
   * `shared/policy.js` is the single source for what may never be filled, and
   * a pause row is a fill by another route — an input under "enter your Social
   * Security number" would be this surface asking for the one thing the whole
   * deny-list exists to refuse. It is belt and braces (collection already
   * refuses these, both paths, ahead of EXCLUDE) and it stays that way: a gate
   * that only holds because an earlier gate held is a gate that disappears the
   * day the earlier one narrows.
   *
   * The kind one is a capability: we cannot write it, so we do not offer to.
   */
  const canAnswerHere = (row) =>
    ANSWERABLE_KINDS.has(row.kind) && !ns.isPolicyBlocked(row.label ?? "");

  /** The inline answer box for one open field: type it, optionally remember it,
   * submit.
   *
   * THE DRAFT LIVES IN THE STORE, not in the element, and this is the Job
   * stage's rule for the Job stage's reason — see `card.preview`. Every render
   * rebuilds the rail from scratch, so an input holding its own characters
   * loses them the moment anything else repaints: a note arriving, another row
   * submitting, a load landing. So `input` writes through `act.editAnswer` and
   * does NOT render, and the value below is read back from the store.
   *
   * `known_value` PREFILLS IT. A retryable is a field a rule already knew the
   * answer to and could not land — a Workday country combobox that refused the
   * write — so the honest ask is "confirm this", not "type it again". It is
   * never written without the user pressing: the rule pass already tried that
   * and the page said no, and a panel that silently re-submitted it would be
   * repeating a failed write with no new information.
   *
   * THE SHARPEST INSTANCE IS AN EEO SELECT. When the backend's standing consent
   * is on, the rule pass answers the voluntary-disclosure controls; one that
   * refuses the write arrives here as an ordinary answerable retryable, so the
   * box is prefilled with a PROTECTED CHARACTERISTIC. Three things then hold at
   * once and none of them is a special case bolted on for it: it offers no
   * learn, because the answer is already the profile's; nothing about it is
   * ever emitted, because telemetry carries no values anywhere on this path;
   * and it is only on screen at all because the user granted the consent that
   * put it in the form. A row that could learn one would be this panel writing
   * a protected characteristic somewhere the consent record does not govern.
   *
   * AND IT OFFERS NO CHECKBOX. There is nothing to learn: the value came OUT of
   * the profile, so saving it back is a write that changes nothing. The line
   * that replaces it says so, because a missing control with no explanation
   * reads as a feature that failed to render.
   */
  function pauseRow(ctx, row) {
    const { facts, act, build } = ctx;
    const { node, attach } = build;
    const draft = facts.answers[row.qid] ?? {};
    const known = row.known_value ?? null;
    const box = node("div", "needs");
    const input = node("input");
    input.type = "text";
    input.id = `answer-${row.qid}`;
    // What the box is FOR, addressed rather than merely placed near it. Both
    // extra lines this row can carry — the option list, and the
    // already-in-your-profile sentence — are the difference between a usable
    // box and a guess, and neither reaches a screen reader from proximity
    // alone. One id per row, built the same way the input's is and for the same
    // reason: two places have to agree on it.
    const noteId = `answer-note-${row.qid}`;
    // The store's draft when there is one, the known value when there is not.
    // `??` and not `||`: a draft the user has deliberately emptied is an
    // answer they are rewriting, and falling back to the known value there
    // would refill the box they just cleared.
    input.value = draft.text ?? known ?? "";
    input.setAttribute("aria-label", `Answer for ${row.label}`);
    input.setAttribute("aria-describedby", noteId);
    input.disabled = facts.busy === true;
    input.addEventListener("input", (event) => act.editAnswer(row.qid, event.target.value));
    // ENTER SUBMITS. The box is not in a `<form>` — nothing on this surface is,
    // because a form in a panel that must never submit an application is a
    // shape with the wrong promise on it — so the browser gives this for free
    // nowhere, and a single-line input the user has just finished typing into
    // is exactly where the key is expected. Guarded on `busy` like the button
    // it stands in for: `disabled` stops a click and does not stop a keystroke.
    input.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || facts.busy === true) return;
      act.submitAnswer(row.qid);
    });
    attach(box, input);
    // A closed list, shown. The writer matches the typed answer against these
    // exact strings, so a user who cannot see them is guessing at a menu.
    if (row.options?.length) {
      const opts = node("div", "opts", `one of: ${row.options.join(" · ")}`);
      opts.id = noteId;
      attach(box, opts);
    }
    if (known === null) {
      const learn = node("label", "learn");
      const check = node("input");
      check.type = "checkbox";
      check.id = `learn-${row.qid}`;
      // DEFAULT ON, and the default is the feature: the whole point of pausing
      // once is not pausing again, and a user who has to opt in to that gets
      // the pause every time. Off is a real choice — a one-off answer this
      // employer asked for — and it is one press away.
      check.checked = draft.learn !== false;
      check.disabled = facts.busy === true;
      check.addEventListener("change", (event) => act.rememberAnswer(row.qid, event.target.checked));
      learn.setAttribute("for", check.id);
      attach(box, attach(learn, check, node("span", null, "Remember this answer")));
    } else {
      // THE MISSING CHECKBOX, EXPLAINED — a decision rather than a control that
      // failed to render, which is the difference between a user trusting this
      // row and reporting it. It takes the describedby id when there are no
      // options to take it, because a retryable is a `text` or `combobox` kind
      // and only the former reaches here: it never has a list to print, so the
      // two lines cannot collide over the id.
      const why = node("div", "learn", "Already in your profile — the field "
        + "refused the write, not the answer.");
      if (!row.options?.length) why.id = noteId;
      attach(box, why);
    }
    const save = node("button", "save", "Fill this field");
    save.type = "button";
    // `actingLimb`'s rule: the footer's primary greys for the length of any
    // action, and a row button that stayed live while a fill ran would send a
    // second write into a page the first one is still walking.
    save.disabled = facts.busy === true;
    save.addEventListener("click", () => act.submitAnswer(row.qid));
    return attach(box, save);
  }

  /** The fields still open, each one a jump to the control it names — and, when
   * we can actually answer it from here, a box to answer it in.
   *
   * ONE LIST out of the runner's two, and the split it collapses is real but
   * not the user's: residue is a control on the page and an essay wants a
   * written answer through `/api/qa`, which is a difference about how they get
   * ANSWERED. The question this list answers is "what is still open", and an
   * unanswered essay is exactly as open as an abstained dropdown. Kept apart in
   * the store, shown together here, and the essay rows say what they are.
   *
   * A BUTTON per row rather than an anchor, because it goes nowhere: it asks
   * the page to scroll, which is a message to a frame and not a navigation.
   *
   * ESSAYS GET NO PAUSE ROW. They are the QnA drawer's — a grounded paragraph
   * written against the resume, not a line typed into a chip — and an input
   * here would be a second, worse composer for the same job. What they get
   * instead, since Task 14, is the HANDOFF: a second button that fills the
   * drawer's box with this question and opens it. One list, two destinations,
   * which is the whole reason the essays were shown here rather than in a
   * second list of their own.
   */
  function needsList(ctx, { residue, essays }) {
    const { build, act } = ctx;
    const rows = [...residue.map((row) => [row, null]),
                  ...essays.map((row) => [row, "written answer"])];
    if (!rows.length) return null;
    const list = build.node("ul", "resid");
    list.setAttribute("aria-label", "Fields that still need you");
    for (const [row, kind] of rows) {
      const button = build.node("button", null, row.label);
      button.type = "button";
      button.addEventListener("click", () => act.scrollToField(row.qid));
      const item = build.attach(build.node("li"), button,
                                kind ? build.node("span", "kindmark", ` · ${kind}`) : null);
      // The essay's own way forward, beside the jump rather than instead of it:
      // the user still has to reach the box on the page to paste into, so both
      // are true and both are offered. It says which question it will ask,
      // because the label a screen reader hears out of context is otherwise
      // "Ask below" on every essay row in the list.
      //
      // "BELOW" AND NOT "↗". On this surface the arrow means LEAVES — the
      // header's Open application, the Resume fork's Custom in Studio — and
      // this button goes nowhere: it fills the composer at the foot of this
      // same body. The mockup drew the glyph on its teaser; the convention is
      // the panel's and it wins.
      if (kind !== null) {
        const ask = build.node("button", "ask", "Ask below");
        ask.type = "button";
        ask.setAttribute("aria-label", `Ask about ${row.label}`);
        // Out of reach while anything runs, its row-mates' rule: the pause row
        // greys its input and its save, and a live control beside them that
        // silently refuses (`askQuestion` returns on `busy`) is the broken /
        // busy confusion this surface keeps naming.
        ask.disabled = ctx.facts.busy === true;
        ask.addEventListener("click", () => act.askAbout(row.label));
        build.attach(item, ask);
      }
      // `kind === null` is "this is residue, not an essay" — essays are Task
      // 14's drawer and get no box here. Written as a statement rather than
      // folded into the attach: the ternary read as though the two branches
      // built different rows, where one of them only adds a child.
      if (kind === null && canAnswerHere(row)) build.attach(item, pauseRow(ctx, row));
      build.attach(list, item);
    }
    return list;
  }

  /** The id the drawer trigger's `aria-controls` names, and the handle a focus
   * restore will reach for. A constant for `TAILOR_OPTIONS_ID`'s reason and
   * built the same way: two places forty lines apart have to agree on it. */
  const QNA_BODY_ID = "qna-body";

  /** The answer, with the question it was given for and a way to take it.
   *
   * THE QUESTION IS PRINTED BESIDE IT, and that is the whole reason the store
   * keeps `answered` separately from the draft in the box. The box above is
   * free to be retyped — that is what a composer is for — and a paragraph
   * sitting under a half-written question, unlabelled, would read as the answer
   * to the words currently on screen. Labelled, it stays a true statement no
   * matter what is typed above it.
   *
   * COPY IS THE POINT OF THIS DRAWER. The answer is going into a textarea on
   * the page, and the panel deliberately does not write it there: an essay is
   * the one thing on an application a person should read before it is submitted
   * in their name. So the affordance hands it over and says what it did — in
   * the button, not in the footer's one sentence, because "Copied" is feedback
   * about a press and the note slot is for what happened to the page.
   *
   * NO BUTTON FOR AN EMPTY ANSWER. The backend answered and there was nothing
   * in it; a Copy that would put an empty string on the clipboard is a control
   * that cannot do what it says.
   */
  function answerBlock({ facts, act, build }) {
    const { node, attach } = build;
    const { answered, answer, copied } = facts.qna;
    if (answer === null) return null;
    const block = node("div", "ans");
    attach(block, node("div", "q", `“${answered}”`),
           node("div", "a", answer || "(no answer)"));
    if (!answer) return block;
    const copy = node("button", "copy", copied ? "Copied" : "Copy");
    copy.type = "button";
    copy.addEventListener("click", act.copyAnswer);
    return attach(block, copy);
  }

  /** The QnA drawer: paste any question, get a grounded answer, copy it.
   *
   * CLOSED BY DEFAULT, which is the mockup's shape and its reasoning: the Fill
   * stage's subject is the form, and a composer standing open under it would
   * compete with the list of fields that still need answering. One dashed line
   * and a trigger is the whole of the closed state — it says what is behind it,
   * so nobody has to press it to find out.
   *
   * ALWAYS OFFERED, before a run as well as after. The question a user pastes
   * here is usually the one in front of them on the page rather than one this
   * extension found, so gating it on a fill having happened would withhold it
   * from the person who opened the panel to answer exactly one question.
   *
   * THE BOX IS A TEXTAREA where the pause row's is an input, and the difference
   * is honest rather than cosmetic: a pause row answers a dropdown or a line of
   * text, and this answers "why do you want to work here" — a question that
   * does not fit on one line, pasted from a form that gave it a paragraph's
   * worth of room.
   *
   * OUT OF REACH WHILE ANYTHING RUNS, `actingLimb`'s rule and the pause row's:
   * a second ask started underneath an open one is a second POST nobody asked
   * for, and the answer that came back second would win.
   */
  function qnaDrawer(ctx) {
    const { facts, act, build } = ctx;
    const { node, attach } = build;
    const drawer = node("div", "qna");
    // "Ask", with no arrow: the glyph means LEAVES on this surface (see the
    // essay row's own note), and this discloses a region six pixels below it.
    const trigger = node("button", "linkish", facts.qna.open ? "Hide" : "Ask");
    trigger.type = "button";
    trigger.setAttribute("aria-expanded", facts.qna.open ? "true" : "false");
    // The Tailor fork's disclosure pattern, reused whole: `aria-expanded` is
    // the state, `aria-controls` names WHAT was disclosed — and it is set ONLY
    // while the region exists, because an id nothing carries offers a jump that
    // goes nowhere, which is the same broken promise as a link to a guessed
    // address. `aria-expanded: false` is the whole of the closed state's story.
    if (facts.qna.open) trigger.setAttribute("aria-controls", QNA_BODY_ID);
    trigger.addEventListener("click", act.toggleQna);
    attach(drawer, attach(node("div", "row"),
                          node("span", null,
                               "Paste any question for a grounded answer"),
                          trigger));
    if (!facts.qna.open) return drawer;
    // ONE region, so `aria-controls` has one thing to point at: the box, the
    // button that sends it and the answer that comes back are one disclosure,
    // and a reader sent to the box alone would be sent past the answer.
    const body = node("div");
    body.id = QNA_BODY_ID;
    const box = node("textarea");
    box.id = "qna-question";
    // THE DRAFT LIVES IN THE STORE, the Job stage's rule for the Job stage's
    // reason: every render rebuilds the rail, so characters held in the element
    // are lost to any repaint — and this box holds a paragraph rather than a
    // word. So `input` writes through `act.editQuestion` and does NOT render,
    // and the value is read back from the store.
    box.value = facts.qna.question;
    box.setAttribute("aria-label", "Question to answer from your resume");
    box.setAttribute("placeholder", "Paste one question…");
    box.disabled = facts.busy === true;
    box.addEventListener("input", (event) => act.editQuestion(event.target.value));
    // NO ENTER-SUBMITS HERE, deliberately, where the pause row has one: a
    // newline is a legitimate character in a pasted question, and a box whose
    // Enter key sent the form would make a two-paragraph question unaskable.
    const ask = node("button", "save", "Ask");
    ask.type = "button";
    ask.disabled = facts.busy === true;
    ask.addEventListener("click", act.askQuestion);
    return attach(drawer, attach(body, box, ask, answerBlock(ctx)));
  }

  /** What this stage says on a page that holds no application form.
   *
   * IT TELLS THE USER WHAT TO DO, which is the whole of why it is a sentence
   * about the NEXT page rather than an apology about this one. The state it
   * covers is ordinary and was silent until 2026-08-19: the user presses "use
   * base as-is" on a posting, which answers the Resume stage's question, and
   * the rail moves here — to the one step that has something left to happen —
   * on a page where it cannot happen yet. Before this line the rail simply sat
   * with Fill locked and said nothing, and the missing ingredient (the page)
   * was the one thing the panel already knew.
   *
   * NO LINK, AND THAT IS A REFUSAL RATHER THAN A GAP. The employer's apply
   * page is exactly what this sentence points at, and the panel cannot name
   * it: it holds NO job URL at all (`applyMatch` narrows the match to
   * {id, company, title}), and the one the backend holds — `source_url` —
   * could not ground an anchor anyway: matching is by directional PATH
   * containment (query and fragment stripped), so a matched page is
   * `source_url` itself or below it, never above — an anchor built from it
   * sends the user where they already are, and on an ATS that carries job
   * identity in the query (?gh_jid=) it could even name a different posting
   * at the same path. Naming the apply URL would take a field nothing
   * captures today (see the round's handoff), and a link this surface cannot
   * ground is the guessed address this project keeps refusing to render.
   */
  const NO_FORM_HERE = "No application form on this page — open the employer's "
    + "Apply page; filling starts there.";

  /** The Fill stage: choose the pass, run it, and read what it actually did.
   *
   * ON A PAGE WITH NO FORM none of the below is offered, and that is the
   * newest of this body's gates. The mode control chooses between two passes
   * that cannot run here, and a segment that decides nothing is the same
   * furniture `attachRow` refuses to render over a page with no upload box.
   * What stands instead is `NO_FORM_HERE` — plus the attach and the drawer,
   * which are offers about the PAGE and about the user's own question, and are
   * true whether or not a form is on it. `facts.hasForm` flipping late (the
   * detect ladder's second look) simply repaints this body as the offer and
   * gives the footer its primary back; no stage moves, because the stage never
   * read it.
   *
   * A REPORT OUTRANKS IT, which is why the gate is not the first line. `fill`
   * or a collect is proof this panel wrote into this page, and a run's own
   * report is never a lie however the page answers a later detect — the same
   * independence the three sources below are gated for.
   *
   * BEFORE A RUN there are no progress rows, because there is nothing to
   * report: a row reading "0 filled" over a form nobody has touched is the
   * panel narrating a fill that has not happened. What the user gets is the
   * mode control and one sentence about what the button will do — and the
   * button itself is the footer's, which is where every primary on this
   * surface lives.
   *
   * AFTER A RUN the rows are the report, in the order the fill made them: the
   * deterministic pass, the remainder, and the disclosures the backend decides.
   *
   * A RUN THAT FAILED PART-WAY STILL HAS A REPORT, and this is the thing this
   * body got wrong once and must not again. The fill is a SEQUENCE — rule pass,
   * collect, choose, write — and a throw anywhere after the first step leaves
   * real work standing: the profile fields are IN THE FORM, and the runner has
   * already handed over any essays it routed, which is precisely why it hands
   * them over early (`shared/guided-run.js`). Gating the whole report on the
   * residue therefore erased two filled fields and printed "Can't reach this
   * page" about a page this panel had just written into.
   *
   * So the three sources are gated INDEPENDENTLY, because they arrive
   * independently:
   *
   * - `fill` is the rule pass's reconciliation. Non-null means it reached the
   *   page, whatever happened afterwards.
   * - `residue`/`essays` are the collect's. Either being non-null means the
   *   questions were collected; both null means they never were, and a
   *   questions row would then be reporting zeros about a step that did not
   *   run.
   * - all three null is the only state with nothing to say, and that covers
   *   both "no fill yet" and the page that answered nothing at all.
   *
   * What FAILED is the note slot's, and the action writes a different sentence
   * for the partial case than for the page that was never reached.
   */
  function fillBody(ctx) {
    const { facts, build } = ctx;
    const { node, attach } = build;
    const collected = facts.residue !== null || facts.essays !== null;
    if (facts.hasForm !== true && !facts.fill && !collected) {
      return attach(node("div", "stg-body"), node("div", "sub", NO_FORM_HERE),
                    attachRow(ctx), qnaDrawer(ctx));
    }
    const body = attach(node("div", "stg-body"), modeControl(ctx));
    // THE DRAWER IS LAST ON BOTH PATHS, which is why it is appended here rather
    // than at either return: it is not part of the report, and a composer above
    // the fields that still need answering would compete with them. On the
    // before-a-run path it sits under the one sentence about what the button
    // will do; on the after path it sits under the list of what is still open,
    // which is where the essays that feed it are.
    if (!facts.fill && !collected) {
      return attach(body, node("div", "sub", facts.fillMode === "rules"
        ? "Fills what your profile answers for. Nothing is sent to a model."
        : "Fills what your profile answers for, then asks for the rest. "
          + "Identity fields are never sent."),
                    // ON BOTH PATHS, and gated on neither: the attach is an
                    // offer about the PAGE, not a line of the run's report, so
                    // it stands before a fill as well as after one. A user who
                    // opened the panel to upload a résumé should not have to
                    // run a fill first to be shown the control for it.
                    attachRow(ctx), qnaDrawer(ctx));
    }
    const run = { writeResults: facts.writeResults ?? [],
                  residue: facts.residue ?? [], essays: facts.essays ?? [] };
    if (facts.fill) attach(body, profileRow(ctx, facts.fill));
    if (collected) attach(body, questionsRow(ctx, run));
    if (facts.fill) attach(body, eeoRow(ctx, facts.fill, facts.eeoConsent));
    // AFTER the three run rows and before the still-open list: once it has
    // happened it IS a report row and belongs with them, and while it is still
    // an offer it belongs above the fields that need the user rather than under
    // them, where a control mixed into that list would read as one of them.
    return attach(body, attachRow(ctx), needsList(ctx, run), qnaDrawer(ctx));
  }

  ns.panelStageFill = fillBody;
})();
