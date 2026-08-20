/* Maestro CS Companion — the Score stage's action.
 *
 * One of the concern files behind `ns.panelActions`; `panel/actions.js` is the
 * joiner and carries the whole contract. Read it before adding anything here.
 *
 * THE RULES, restated because a file that only POINTS at them is a file that
 * half-remembers them:
 *
 * - AN ACTION WRITES THE BACKEND, holds `busy` for as long as that takes, obeys
 *   the generation rule in full, and never assigns a stage — `stageFor`
 *   recomputes the rail from the store on every render.
 * - THE `busy` SPAN IS `duringAction`'s, read off the namespace and never
 *   re-implemented here — see `panel/actions/during.js`.
 * - NOTHING HERE REACHES FOR ANYTHING: an action reads through the handle,
 *   writes through the handle, and asks the handle to paint.
 *
 * ONE EXCEPTION, the same one the stage bodies take: `shared/decisions.js` is
 * read off the namespace because the ranking is a DECISION both surfaces read
 * one copy of, not a fact about this panel.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const duringAction = ns.panelDuringAction;
  const { rankBaseResumes } = ns.decisions;

  /** Score all bases: the one COMPUTE call this surface makes.
   *
   * A BUTTON rather than something that happens on open, and the reason is
   * cost: it scores every base resume against this job, and spending the
   * user's backend on that silently, on every panel open, would be answering a
   * question they had not asked. That is also why the affordance is offered
   * whenever the stage is Score rather than only when `scores` is empty — the
   * panel cannot see whether a stored score predates an engine change, so
   * "re-run it" stays the user's to ask for.
   *
   * NOTHING IS RE-READ AFTERWARDS, which is the one place this diverges from
   * `addJob`'s shape, and the reason is narrower than it first looks: the POST
   * answers for every base slug it can score, so a re-read would learn nothing
   * about the BASES that is not already in hand. That is the whole of it. Its
   * answer is a SUBSET of what the array holds — the non-base rows exist only
   * in the GET — which is why the assignment below merges rather than
   * replaces, and why "the POST's answer is the scores" is a sentence to
   * distrust rather than the reason for this paragraph. Everything else is
   * `addJob`'s: busy for the length of the call, a note on failure, and the
   * generation check on BOTH limbs.
   */
  async function scoreAllBases(store) {
    if (store.read().busy !== null) return;
    if (!store.read().job) {
      // The note slot's rather than a throw: this panel has no exception path
      // a click goes through.
      store.write({ note: { text: "Add the job first." } });
      store.render();
      return;
    }
    const done = await duringAction(store, "score", () =>
      store.api("/api/ats-scores", {
        method: "POST", body: JSON.stringify({ job_id: store.read().job.id }),
      }));
    if (!done) return;
    // No `token` past here, and that is the same divergence the paragraph above
    // names: nothing is re-read, so there is no second round trip to guard.
    const rows = done.out;
    // RE-READ, and this is the handle's rule rather than a nicety: the snapshot
    // taken before the POST describes a store the four loaders have been
    // writing to for the length of it.
    const facts = store.read();
    // MERGED, not replaced, and the difference is a ring the user is looking
    // at. `score_all_bases` returns BASE rows only — one `score_target(…,
    // "base_resume", …)` per slug, backend/app/services/ats_score.py:128 —
    // where the GET returns `latest_scores` for every target on this job, the
    // TAILORED application included. The two answers are schema-equal and this
    // one is a strict SUBSET, which is exactly why "the POST's answer is the
    // scores" reads true and is not: this array has TWO readers. The ranking
    // below is the first; `renderAts`' After
    // ring is the second. A wholesale replace deletes the tailored composite
    // of a draft application — and a job whose base was never picked sits on
    // the Score stage with that pair on screen — so the rings would drop from
    // 72 → 84 to 72 alone, with "tailor to raise it" beside an application
    // that already was, until the next navigation re-read it.
    //
    // Base rows come wholesale from the scorer (it just answered for every
    // slug it could score, so an older base row it did not return is one it
    // could not); everything else is left exactly as it was.
    const scores = [
      ...(facts.scores ?? []).filter((row) => row?.target_type !== "base_resume"),
      ...rows,
    ];
    store.write({ scores });
    const ranked = rankBaseResumes(facts.resumes, scores);
    const best = ranked[0];
    if (best && best.score !== null) {
      // `loadBaseScores`'s rule, and for the same reason: scoring may move the
      // ranking onto a different resume, and it may NOT move a choice the user
      // has already made. It never sets `baseSelected` either — the Score
      // stage completes when the user picks, not when the numbers arrive.
      if (!facts.baseSelected) store.write({ baseSlug: best.slug });
      store.write({ note: { text: `Best match: ${best.display_name || best.slug} · ATS ${
        Math.round(best.score)}.` } });
    } else {
      // Scored, and still nothing to rank: an empty library, or rows the
      // ranking could not put a number on. Saying "best match: undefined"
      // would be the panel claiming a judgement it does not have.
      store.write({ note: { text: "Scored, but no base resume came back with a number." } });
    }
    store.render();
  }

  ns.panelActionsScore = { scoreAllBases };
})();
