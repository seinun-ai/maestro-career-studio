/* Maestro CS Companion — the side panel's stage bodies, joined.
 *
 * The rail's OPEN row gets a body; `panel/stages/` is all of them, one file
 * per stage key, and this file is the roster that publishes `ns.panelStages`
 * from them. EXACTLY ONE row is open and `renderRail` decides which — normally
 * the active one, and otherwise a DONE row the user has reopened on purpose
 * (`revisit`, panel.js). A locked row is a step that is coming and never has a
 * body; a done row nobody reopened is a tick and a summary.
 *
 * THIS SENTENCE USED TO READ "a body belongs to the active row and to no
 * other", and it is rewritten rather than softened because the change it
 * describes is real: on a Workday wizard the first page's fill ticks Fill and
 * moves the rail to Track while four more pages of form sit in front of the
 * user, so the rail needs a door back to a step it has already ticked. What did
 * NOT change is the reason that sentence existed — a body still appears only
 * where its stage's own controls make sense. `REOPENABLE` (panel.js) is
 * Score/Resume/Fill always, and Job only when the binding is a user claim:
 * a Job body under a backend-matched "✓ in library" would still be the panel
 * offering to add a job it has just said is added, but a claimed pick is
 * the user's to withdraw.
 *
 * REOPENING IS A VIEW, NEVER A STAGE. `stageFor` does not read `revisit`, no
 * tick is cleared by opening a row, and the data-active row keeps its active
 * styling while another row's body is open — the rail may not fake its state to
 * match what the user is looking at. A body cannot tell whether it is the
 * active row's or a reopened one, and nothing here should want to: the context
 * it is handed is the same either way.
 *
 * THE RULE THE WHOLE DIRECTORY OBEYS, and the reason this header outlived the
 * code that used to sit under it: NOTHING IN A BODY REACHES FOR ANYTHING. No
 * `card`, no `chrome`, no `document`, no network — a body builds nodes with the
 * builders it is handed and fires the callbacks it is handed. What travels is a
 * CONTEXT OBJECT passed IN — the facts a body may read and the callbacks it may
 * fire — built per render by panel.js's `stageContext()`, whose comment is that
 * contract's definition and the thing to read before adding a body. `card`
 * itself never leaves panel.js, so the rule is enforced by scope rather than by
 * agreement, which is the only kind of enforcement an arrangement like this can
 * have.
 *
 * IT IS RESTATED IN EVERY FILE UNDER `stages/`, deliberately and not by
 * accident: five files each POINTING at a rule they do not carry is how a body
 * ends up reading `card`, which is the whole failure the seam exists to make
 * impossible. One exception is spelled out where it is taken — a body may read
 * `shared/decisions.js` and `shared/policy.js` off the namespace, because those
 * are DECISIONS both surfaces read one copy of rather than facts about a
 * render.
 *
 * THE SPLIT HAPPENED AT TASK 15, as this header said it would, and it is the
 * one thing here worth knowing the history of. The threshold was written in
 * advance — a FIFTH stage body, or roughly 700 lines, whichever came first —
 * and BOTH clauses fired at Task 14: the QnA drawer took the single file to 887
 * lines, and Task 15's Track body was the fifth. The cut was deferred to Task
 * 15's OPENING commit rather than taken while the Track body was being written,
 * which is the discipline that made panel.js's two cuts clean and that Task 12
 * recorded itself skipping. `panel/actions.js` tripped its own trigger in the
 * same task and made the same call, so both cuts landed together — which is
 * what turns two deferrals into one decision instead of two arrangements that
 * rhyme.
 *
 * THE SEAM WAS ALREADY CUT when the move came: the `// ---- the X stage ----`
 * markers were exactly the boundaries and no helper crossed one (`grouped`,
 * `engineOf`, `forkButton`, `progressRow` each served a single stage), so the
 * move was a move. The pause row and the QnA drawer went with `fill.js` because
 * `fillBody` renders both — one subject, one file — where the ACTIONS behind
 * them are cut three ways, for the reason `panel/actions.js`'s header gives.
 *
 * WHEN THIS DIRECTORY SPLITS AGAIN. It does not: a stage is the unit, the rail
 * has five of them, and a sixth would be a sixth file rather than a decision.
 * The live question is the other direction — a FILE growing past its stage, of
 * which `stages/fill.js` (549 lines: mode control, three progress rows, the
 * open list with its pause rows, the drawer) is the only candidate. TRIGGER
 * for cutting it: a fill sub-concern that `fillBody` does NOT render. Do not
 * cut it because it is the longest file here — the pause row and the drawer are
 * parts of one stage's body, and three files that all have to agree about what
 * a run reported would buy a boundary and cost the agreement.
 *
 * SIZES: job 207 · score 129 · resume 147 · fill 549 · track 128, this roster
 * 104. Stated because a threshold nobody can measure against is not one. (The
 * roster was FOUR for one commit — Task 15's opening cut was the MOVE, and the
 * Track body landed in the commit after it.)
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  /** Stage bodies by stage key, which is how `renderRail` finds one without
   * knowing this directory exists. A stage with no entry renders its row and
   * nothing under it — which is why a MISSING one has to throw here rather than
   * resolve to `undefined`: `STAGE_BODIES[key]?.()` cannot tell "this stage has
   * no body" from "panel.html forgot the script tag", and the second reads to a
   * user as a rail row that simply does nothing. */
  const bodies = {
    job: ns.panelStageJob,
    score: ns.panelStageScore,
    resume: ns.panelStageResume,
    fill: ns.panelStageFill,
    track: ns.panelStageTrack,
  };
  for (const [key, body] of Object.entries(bodies)) {
    if (typeof body !== "function") {
      throw new Error(`panel/stages: nothing published for the ${key} stage — `
        + `is <script src="stages/${key}.js"> in panel.html, before this file?`);
    }
  }
  ns.panelStages = bodies;
})();
