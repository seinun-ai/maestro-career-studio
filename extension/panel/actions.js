/* Maestro CS Companion — the side panel's actions, joined.
 *
 * An action is neither a loader nor a renderer, which is what makes it a
 * category: it WRITES to the backend, it holds `busy` for as long as that
 * takes, it obeys the generation rule in full, and it ends by re-running a load
 * rather than by assigning a stage. `panel/actions/` is all of them, one file
 * per concern, and this file is the roster that binds them to one store handle
 * and publishes `ns.panelActions`.
 *
 * WHY THEY DO NOT SET THE STAGE. The rail is computed from the store by
 * `stageFor` on every render, so "advance to Score" is not a thing an action
 * can say — it can only make the facts true and let the next render read them.
 * That is the design's "stage inference, not stage navigation", and it is what
 * keeps a tick from appearing beside a button that still asks for the same
 * thing.
 *
 * `ns.panelActions` IS A FACTORY, and that is the seam. It is called ONCE, at
 * load, with the store handle panel.js builds for it, and it returns the
 * actions bound to that handle — so nothing under `panel/actions/` ever sees
 * `card` and none of it can keep a reference to anything. The contract for what
 * the handle carries is written at its definition (`actionStore()` in
 * panel.js), the way `stageContext`'s is; read that before adding an action.
 *
 * WHY NOT THE STAGE BODIES' SEAM, which is the question this cut had to answer:
 * a body reads a per-render SNAPSHOT and returns, so handing it facts is the
 * whole of what it needs. An action is a SEQUENCE — it paints `busy`, awaits a
 * POST, writes four fields and a sentence, then re-runs a load that writes the
 * store again — so a snapshot goes stale inside it (every action re-reads after
 * its await) and a returned patch would be either one patch applied too late or
 * a generator. Worse, the generation check has to sit AT each write rather than
 * once at the end: `duringAction` guards both of its limbs and `loadContext`
 * guards again inside. So what crosses is a WRITE DOOR — `store.write(patch)`,
 * one named function with a key list — and never the store itself. A published
 * mutable `card` shared by several files is the outcome both cuts exist to
 * avoid.
 *
 * SO NOTHING UNDER `actions/` REACHES FOR ANYTHING. No `card`, no `chrome`, no
 * `document`, no `fetch`, no timers: an action reads through the handle, writes
 * through the handle, and asks the handle to paint. Enforced by scope rather
 * than by agreement, which is the only kind of enforcement an arrangement like
 * this has. It is restated in EVERY file under `actions/`, deliberately: files
 * that only point at a rule they do not carry are files that half-remember it.
 *
 * THE SPLIT HAPPENED AT TASK 15, and the history is worth keeping because this
 * file arrived at 664 lines with its siblings' advice in front of it and wrote
 * no threshold of its own, then took Task 13's pause row to 999 without
 * anything firing. The threshold it eventually wrote — a SIXTH action, or
 * roughly 1100 lines — fired on BOTH clauses at Task 14 (`askQuestion` was the
 * seventh function the factory bound, and the QnA drawer took the file past
 * 1100). The cut was deferred to Task 15's OPENING commit, beside
 * `panel/stages.js`'s, so that the two arrangements stay one arrangement rather
 * than two that rhyme.
 *
 * THE CUT IS THE ONE THE OLD HEADER MARKED, plus one. Its three
 * `// ---------- … ----------` boundaries became `actions/fill.js`,
 * `actions/pause.js` and `actions/qna.js`; the unmarked head split by STAGE —
 * `actions/job.js`, `actions/score.js`, `actions/resume.js` — because those are
 * three subjects rather than one, and because mirroring `panel/stages/` is the
 * whole point of the two cuts landing together. The cut commit was the MOVE
 * and nothing else; `actions/track.js` arrived with the Track stage in the
 * commit after it.
 *
 * WHAT SURVIVED THE SPLIT INTACT, and it is the clause that mattered:
 * `duringAction` and the paragraph above it. The `busy` span is this
 * directory's ONE serialization rule, it was broken once by placement (Task
 * 13's learn tail), and per-concern files each half-remembering it is how the
 * next tail ends up outside the span. So it is ONE definition in ONE file of
 * its own — `panel/actions/during.js` — and every concern file reads it off the
 * namespace rather than carrying a `try` of its own.
 *
 * TWO OTHER THINGS CROSS THE FILES, and both are on the namespace for the same
 * reason: `ns.panelFillFinished` (published by `actions/fill.js`, read by
 * `actions/pause.js`, because the last pause row closing must mark the page
 * done exactly as a clean run would) and the pause row's three PURE pieces
 * (`ns.saveTargetFor`, `ns.withCustomAnswer`, `ns.withProfileAnswer`, published
 * by `actions/pause.js` because none of them needs a store handle to be
 * driven). Nothing else does, which is what "self-contained but for
 * `duringAction` and `fillFinished`" meant when it was written.
 *
 * WHEN THIS DIRECTORY SPLITS AGAIN. It does not: a concern is the unit, and a
 * new action either belongs to one that is here or brings its own file. The
 * live question is a FILE growing past its concern, and `actions/fill.js`
 * (337 lines: the rule pass, the finished predicate, the run) is the only
 * candidate. TRIGGER for cutting it: a SECOND full-page pipeline beside
 * `runGuidedFill`. Do not cut it because it is the longest file here.
 *
 * SIZES: during 88 · job 81 · pick 257 · score 112 · resume 214 · fill 337 ·
 * pause 333 · qna 143 · track 180, this roster. Stated because a threshold
 * nobody can measure against is not one.
 *
 * WHAT THIS FILE PUBLISHES: ns.panelActions = (store) => ({ addJob,
 * pickApplication, unpickApplication, dropDeletedApplication, scoreAllBases,
 * quickTailor, useBaseAsIs, stopUsingBaseAsIs, startFill, submitAnswer,
 * askQuestion, setStatus, trackThis }).
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  /** The concern file's contribution, or a sentence naming the missing tag.
   *
   * LOUD rather than `undefined`, for `panel/stages.js`'s reason: panel.js
   * destructures this factory's return at LOAD, so a missing part would surface
   * as `addJob is not a function` on the first click — a panel that looks fine
   * and does nothing, which is the exact failure mode every control on this
   * surface is written to avoid. */
  function need(file, part) {
    if (!part) {
      throw new Error(`panel/actions: nothing published by panel/${file} — `
        + `is its <script> tag in panel.html, before this file?`);
    }
    return part;
  }

  const job = need("actions/job.js", ns.panelActionsJob);
  const pick = need("actions/pick.js", ns.panelActionsPick);
  const score = need("actions/score.js", ns.panelActionsScore);
  const resume = need("actions/resume.js", ns.panelActionsResume);
  const fill = need("actions/fill.js", ns.panelActionsFill);
  const pause = need("actions/pause.js", ns.panelActionsPause);
  const qna = need("actions/qna.js", ns.panelActionsQna);
  const track = need("actions/track.js", ns.panelActionsTrack);

  /** The actions, bound to one store handle. Called once, at load, by panel.js.
   *
   * A factory rather than a plain object because the handle is what makes these
   * functions safe to have moved: bound here, the surface each action presents
   * to its caller is `() => Promise<void>` — a click handler, and nothing that
   * could be passed a different store.
   *
   * WRITTEN OUT rather than folded into a loop over the parts. The roster IS
   * the API panel.js destructures, and a generated one would make a typo in a
   * concern file's export name into a missing key nobody names — which is the
   * quiet failure `need()` above exists to refuse. */
  ns.panelActions = (store) => ({
    addJob: () => job.addJob(store),
    pickApplication: (applicationId) => pick.pickApplication(store, applicationId),
    unpickApplication: () => pick.unpickApplication(store),
    // Bound like the rest, and called by a LOADER rather than by a control —
    // the only entry here with no button behind it. It is an action all the
    // same by this roster's own definition: it writes the store, it rewrites
    // the bridge, and it leaves the rail to `stageFor`. What it is not is a
    // second copy of the unbinding, which is the whole reason it lives beside
    // `unpickApplication` instead of inside panel.js's `loadContext`.
    dropDeletedApplication: () => pick.dropDeletedApplication(store),
    scoreAllBases: () => score.scoreAllBases(store),
    quickTailor: () => resume.quickTailor(store),
    useBaseAsIs: () => resume.useBaseAsIs(store),
    stopUsingBaseAsIs: () => resume.stopUsingBaseAsIs(store),
    startFill: () => fill.startFill(store),
    attachResume: () => fill.attachResume(store),
    submitAnswer: (qid) => pause.submitAnswer(store, qid),
    askQuestion: () => qna.askQuestion(store),
    setStatus: (status) => track.setStatus(store, status),
    trackThis: () => track.trackThis(store),
  });
})();
