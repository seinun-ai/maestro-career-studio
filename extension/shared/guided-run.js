/* Maestro CS Companion — the guided-fill runner.
 *
 * ONE orchestration engine, written for two surfaces and left with one: the
 * panel's Fill stage calls it with its bound tab's transport. The shape is
 * kept rather than inlined back into the caller, because the split it enforces
 * is the useful one — a runner that cannot render, and a caller that cannot
 * sequence. The sequencing and the batching are here; the TRANSPORT is not —
 * `broadcast` and `api` arrive as dependencies, so nothing in this file knows
 * which world it is running in, and neither surface can drift into a second
 * pipeline.
 *
 * Loaded by the manifest's content_scripts AND by panel.html's script tags.
 * It touches no `document`, no `location`, no `chrome.*` and no network of its
 * own, which is what a shared module has to be — and it stays that way now
 * that the panel is the only caller, because the writers it drives run in the
 * page and that is the boundary this file exists to sit on.
 *
 * THE LOADABILITY GAP IS CLOSED AT TASK 12, and this paragraph is the record of
 * what it was. This file reads three functions off the namespace at call time —
 * `ns.routeOpenQuestions`, `ns.requestChoose`, `ns.buildRestFillObservations` —
 * and all three used to live in `content/open-questions.js`, which is a CONTENT
 * SCRIPT: in a panel document those names were simply undefined, whatever the
 * load order, so a <script> tag for this file bought a TypeError on the first
 * Start-fill click. They now live in `shared/choose.js`, which both surfaces
 * load. What did NOT move is the rest of that file — `collectOpenQuestions`,
 * `applyGuidedChoices`, `fillAnswersByQid` are page-DOM writers, and a panel
 * has no page — so the split line is "does it touch the document", and the
 * namespace roster plus the guided-collect drivers name the seam from both
 * sides.
 *
 * The R1 honesty rules this file is the keeper of, all of them moved here
 * WITH the code that keeps them:
 *
 * 1. Identity data never reaches `/choose`. The retryables lane — controls a
 *    rule tried and missed, carrying the known value — goes straight to
 *    `guided_write` and is never offered to the model.
 *
 *    2026-08-18 refinement: RELEASED and RETRYABLE are different facts and
 *    different stores. A retryable has the right rule value and needs delivery;
 *    a released control rejected the rule's value as wrong for its real
 *    options. Released controls re-enter collection as ordinary value-free
 *    questions; no profile value follows them into `/choose`. Policy-blocked
 *    and EEO controls never use that release lane.
 * 2. Abstain by default. An abstain is residue, never a guess; the option
 *    guard itself is SERVER-side (design), and this file only ever writes a
 *    choice whose reason is "matched".
 * 3. A `/choose` failure degrades to the residue list. It never rolls back the
 *    rule pass, and it never blocks the user's navigation.
 * 4. Telemetry carries no values — `buildRestFillObservations` builds it and
 *    the service worker scrubs it, and neither is bypassed from here.
 *
 * WHAT THIS FILE PUBLISHES: ns.guidedRun = { runGuidedFill, collectFromPage,
 * NO_FRAME_REACHED }.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  // The one sentence for "we never got to ask the page", so the places that
  // can hit it cannot drift into several accounts of one failure. Every other
  // message about the page — "no matching fields", "no open questions", "no
  // PDF input" — is a FINDING, and a finding may not be reported about a page
  // nobody read.
  //
  // It lives here, rather than at the call site where it was written, because
  // this module is the first thing that can hit the condition and the callers
  // read it back off the namespace for their own checks (`panel/actions/
  // fill.js` and `panel/actions/pause.js` both throw it). If a later round
  // gives the fan-out a shared module of its own, the sentence belongs there.
  const NO_FRAME_REACHED =
    "Can't reach this page. Reload the tab, then try again. The page script "
    + "loads with the page, so a tab that was already open when the extension "
    + "last reloaded does not have it.";

  /** Every open control on the page, in one fan-out.
   *
   * Retryables: rule-territory (EXCLUDE'd) controls a rule tried and missed,
   * carrying the known value. They go straight to guidedWrite and are NEVER
   * offered to /choose. A rule-released control is not in this list: collection
   * returns it as an ordinary value-free question, because the rule refused its
   * value rather than missing delivery. */
  async function collectFromPage(broadcast) {
    const frames = await broadcast({ type: "collect_open_questions" });
    if (!frames.some((frame) => frame.result !== undefined)) {
      throw new Error(NO_FRAME_REACHED);
    }
    const retryables = frames.flatMap((frame) =>
      (frame.result?.retryables ?? []).map((row) => ({
        ...row,
        frameId: frame.frameId,
        host: frame.result.host,
      })));
    const questions = frames.flatMap((frame) =>
      (frame.result?.questions ?? []).map((question) => ({
        ...question,
        frameId: frame.frameId,
        host: frame.result.host,
      })));
    return { questions, retryables };
  }

  /** Rule pass → collect → /choose → guidedWrite → residue.
   *
   * A /choose 5xx residues unanswered fields and never rolls back the rule
   * pass. Essays stay on the existing /api/qa path — they are handed back
   * through `onProgress` as they are routed, because a later throw (a page
   * that stopped answering between the collect and the write) must not lose
   * the queue the caller already has an answer for.
   *
   * deps — the three REQUIRED ones are checked by name at the top of the
   * function. A missing dep is a wiring bug in a caller that has not run yet,
   * and its natural failure is a TypeError several awaits downstream, reported
   * to the user as a page problem on a page that is fine; `guided-run: missing
   * dep <name>` says whose bug it is. `api` is required even in rules-only
   * mode: the mode is per RUN, and a caller that cannot ask has not decided
   * anything, it is just incomplete.
   *   broadcast(message)  → the per-frame fan-out. REQUIRED.
   *   api(path, init)     → the backend, and ONLY for /choose. REQUIRED, but
   *                         unused when `aiAssist` is false — which is what
   *                         makes the rules-only mode a mode and not a promise.
   *   onProgress(update)  → REQUIRED. `{phase: "essays", essays}` then
   *                         `{phase: "residue", residue}`, at the two points
   *                         where a surface has something new to show. UI
   *                         writes belong to the caller; a runner that renders
   *                         is a runner only one surface can use.
   *   telemetry(action, observations) → fire-and-forget. OPTIONAL, and it stays
   *                         optional: a caller that passes none sends none, and
   *                         nothing else changes. Telemetry is opt-in at the
   *                         service worker, so a surface that never emits is a
   *                         legitimate surface, not a broken one.
   *   rulePass()          → the deterministic profile fill, run FIRST and
   *                         inside a swallow. OPTIONAL: a caller with no rule
   *                         pass runs the remainder alone, which is a real (if
   *                         thin) run, not a wiring bug. Injected rather than
   *                         owned because it is also a standalone action in
   *                         its own right, and because EEO consent is ITS
   *                         business: the backend's
   *                         standing consent is the only thing that may turn
   *                         protected-characteristic fill on, never a local
   *                         toggle.
   *
   * options:
   *   aiAssist   — false skips /choose entirely. The residue is then everything
   *                the rules could not answer, which is the honest report of a
   *                rules-only run rather than a shorter list.
   *   applicationId — grounds /choose in an application when there is one.
   *
   * returns `{ essays, residue, writeResults }`:
   *   residue      — the list the user is shown. Both surfaces read it.
   *   essays       — the /api/qa queue. It arrives TWICE on purpose: through
   *                  `onProgress` at the moment it is routed, so the caller's
   *                  UI has it before the model is asked and keeps it if a
   *                  later step throws; and here, so a caller that only wants
   *                  the finished picture does not have to reassemble it from
   *                  callbacks. Same array, not a copy.
   *   writeResults — the per-qid outcomes, which the panel's progress rows
   *                  read: its "N filled · N need you" is these minus the
   *                  residue, and NOT the rule pass's reconciliation, which
   *                  knows nothing about the model's half of the run.
   *
   * There is deliberately NO `host` option. Telemetry attributes each
   * observation to `q.host`, which `collectFromPage` stamps from the FRAME
   * that answered — the truthful host for an iframe-embedded form, and the
   * only one a panel could trust anyway. A run-level host could only ever
   * apply to a row whose frame did not report one, which the shipped collector
   * cannot produce; passing one in would be a parameter with no reachable
   * effect, dressed as provenance. */
  async function runGuidedFill(deps, options = {}) {
    const { broadcast, api, onProgress, telemetry, rulePass } = deps ?? {};
    const { aiAssist = true, applicationId = null } = options;

    // Named, and BEFORE the rule pass — so a half-wired caller fails on its
    // own bug instead of after writing half a form.
    for (const [name, dep] of [
      ["broadcast", broadcast], ["api", api], ["onProgress", onProgress],
    ]) {
      if (typeof dep !== "function") {
        throw new Error(`guided-run: missing dep ${name}`);
      }
    }

    if (rulePass) {
      try {
        await rulePass();
      } catch (_) {
        // No profile, or the page had nothing the rules cover: the remainder
        // path is still the primary fill on a rule-sparse form.
      }
    }

    const { questions, retryables } = await collectFromPage(broadcast);
    const routed = ns.routeOpenQuestions(questions);
    onProgress({ phase: "essays", essays: routed.essays });

    const { choices, residue: chooseResidue } = aiAssist
      ? await ns.requestChoose(routed.chooseFields, {
        postChoose: (body) => api("/api/autofill/choose", {
          method: "POST",
          body: JSON.stringify(body),
        }),
        applicationId,
      })
      // Rules only: nothing is asked, so nothing is answered, and every field
      // the rules left open is residue. Shaped exactly like requestChoose's
      // return so one code path follows.
      : { choices: {}, residue: [...routed.chooseFields] };

    // Retryables lead the batch: the rule pass already knows their value, so
    // they cost no model call and their fields render before the choose set.
    const toWrite = [
      ...retryables.map((row) => ({
        qid: row.qid,
        answer: row.known_value,
        kind: row.kind,
        knownValue: row.known_value,
      })),
      ...routed.chooseFields
        .filter((field) => {
          const choice = choices[field.qid];
          return choice && choice.reason === "matched" && choice.answer;
        })
        .map((field) => ({
          qid: field.qid,
          answer: choices[field.qid].answer,
          kind: field.kind,
          knownValue: field.known_value,
        })),
    ];

    // ONE guided_write for the whole batch, and one is the bound: the single
    // bounded retry of a control that would not take the value is the ENGINE's
    // (`content/autofill.js`'s guidedWrite, alternate gesture order, outcome
    // `retry_filled`). A second write from here would be a second retry the
    // engine already decided against, on a form the user is watching.
    let writeResults = [];
    if (toWrite.length) {
      const written = await broadcast({ type: "guided_write", pairs: toWrite });
      if (!written.some((frame) => frame.result !== undefined)) {
        throw new Error(NO_FRAME_REACHED);
      }
      writeResults = written.flatMap((frame) => frame.result ?? []);
    }

    const writtenQids = new Set(writeResults.map((row) => row.qid));
    const residueQids = new Set(chooseResidue.map((field) => field.qid));
    for (const row of writeResults) {
      if (row.outcome === "not_stuck") residueQids.add(row.qid);
    }
    for (const pair of toWrite) {
      if (!writtenQids.has(pair.qid)) residueQids.add(pair.qid);
    }
    const byQid = Object.fromEntries(
      [...questions, ...retryables].map((q) => [q.qid, q]));
    const residue = [...residueQids].map((qid) => byQid[qid]).filter(Boolean);
    onProgress({ phase: "residue", residue });

    const abstained = chooseResidue.filter((field) => {
      const choice = choices[field.qid];
      return choice && choice.reason === "abstained";
    });
    telemetry?.("rest_fill", ns.buildRestFillObservations({
      questions: [...questions, ...retryables],
      writeResults,
      abstained,
    }));

    // The counts, never a sentence: what the user is told about a residue of
    // three is the caller's copy, and the two surfaces say it differently.
    return { essays: routed.essays, residue, writeResults };
  }

  ns.guidedRun = { runGuidedFill, collectFromPage, NO_FRAME_REACHED };
})();
