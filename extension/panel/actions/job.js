/* Maestro CS Companion — the Job stage's action.
 *
 * One of the concern files behind `ns.panelActions`; `panel/actions.js` is the
 * joiner and carries the whole contract. Read it before adding anything here.
 *
 * THE RULES, restated because a file that only POINTS at them is a file that
 * half-remembers them:
 *
 * - AN ACTION WRITES THE BACKEND, holds `busy` for as long as that takes, obeys
 *   the generation rule in full, and ends by re-running a load rather than by
 *   assigning a stage. The rail is computed from the store by `stageFor` on
 *   every render, so "advance to Score" is not a thing an action can say.
 * - THE `busy` SPAN IS `duringAction`'s, read off the namespace and never
 *   re-implemented here — see `panel/actions/during.js`, which is one function
 *   in one file for exactly that reason.
 * - NOTHING HERE REACHES FOR ANYTHING. No `card`, no `chrome`, no `document`,
 *   no `fetch`, no timers: an action reads through the handle, writes through
 *   the handle, and asks the handle to paint.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const duringAction = ns.panelDuringAction;

  /** Add job: save the posting in front of the user, as they have edited it.
   *
   * TWO SENTENCES AFTERWARDS, not one: `already_existed` is the difference
   * between "saved" and "you saved this last week", and collapsing them tells
   * a user their click did something it did not.
   *
   * The four store assignments are made even though `loadContext` re-runs
   * immediately after: the POST's own answer names
   * the job, so the panel can be truthful about it now rather than after four
   * more round trips. The re-load is what CONFIRMS it — and if the backend then
   * does not recognise this url as that job, the panel says so instead of
   * keeping a claim only we believe.
   */
  async function addJob(store) {
    const facts = store.read();
    if (facts.busy !== null) return;
    const body = store.build.ingestBodyFrom(facts.preview, facts.url);
    if (!body.raw_text) {
      // Nothing was read and nothing was typed. Posting this would spend an
      // extraction on an empty string and leave a nameless row in the library.
      //
      // Not an `error`: the slot's red voice is for something that went wrong,
      // and "this page has no posting on it" is a fact about the page — true of
      // most pages, and already visible in the three empty boxes above.
      store.write({
        note: { text: "Nothing to save yet — add a title, or open a job posting." },
      });
      store.render();
      return;
    }
    // The tab this posting came off may not be the tab the answer arrives on —
    // `duringAction` holds that guard on both limbs and hands back `null` when
    // there is nothing here left to say.
    const done = await duringAction(store, "job", () =>
      store.api("/api/jobs", { method: "POST", body: JSON.stringify(body) }));
    if (!done) return;
    const { token, out: job } = done;
    const skills = job.extracted_json?.skills?.length ?? 0;
    store.write({
      job: { id: job.id, company: job.company, title: job.title },
      // The page IS this job now, whatever the url matcher would say about it.
      match: "exact",
      application: null,
      pdfReady: false,
      note: { text: job.already_existed === true
        ? "Already tracked. This posting was saved earlier."
        : `Saved with ${store.build.plural(skills, "skill")} extracted.` },
    });
    store.render();
    // The stage advances because the data moved, not because anything here
    // said so. `loadContext` keeps the note it did not write, so what the user
    // just did survives the reload that confirms it.
    await store.loadContext(token);
  }

  ns.panelActionsJob = { addJob };
})();
