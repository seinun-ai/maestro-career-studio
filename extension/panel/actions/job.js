/* Maestro CS Companion — the Job stage's two actions: save the job, and score
 * the base resumes against it (the Score step's action until Score merged into
 * Job, 2026-09-27). A save runs the scoring in the same press.
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
 *   every render, so "advance to Resume" is not a thing an action can say.
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
  const { rankBaseResumes } = ns.decisions;

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
   *
   * THE SCORING RUNS IN THE SAME PRESS, before the re-load: scores need the
   * saved job, and the Job step is not done until a base is chosen, so a save
   * that stopped here would leave the user a second button to press for an
   * answer they already asked for. Always, not only for a new job: the engine
   * is deterministic and base rows upsert, so scoring a job saved last week
   * again costs one local pass per base and changes nothing that was right.
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
        note: { text: "Nothing to save yet. Add a title or open a job page." },
      });
      store.render();
      return;
    }
    // The tab this posting came off may not be the tab the answer arrives on —
    // `duringAction` holds that guard on both limbs and hands back `null` when
    // there is nothing here left to say.
    const done = await duringAction(store, "job", () =>
      store.api("/api/jobs", { method: "POST", body: JSON.stringify(body) }),
    "Couldn't save the job.");
    if (!done) return;
    const { token, out: job } = done;
    const skills = job.extracted_json?.skills?.length ?? 0;
    const saved = job.already_existed === true
      ? "Already saved in Maestro CS."
      : `Saved. Found ${store.build.plural(skills, "skill")}.`;
    store.write({
      job: { id: job.id, company: job.company, title: job.title },
      // The page IS this job now, whatever the url matcher would say about it.
      match: "exact",
      application: null,
      pdfReady: false,
      note: { text: saved },
    });
    store.render();
    await scoreAllBases(store, { lead: `${saved} ` });
    if (!store.current(token)) return;
    // The stage advances because the data moved, not because anything here
    // said so. `loadContext` keeps the note it did not write, so what the user
    // just did survives the reload that confirms it.
    await store.loadContext(token);
  }

  /** Score all bases: the one COMPUTE call this surface makes, and a cheap one.
   * `POST /api/ats-scores` runs the deterministic ATS engine (no model call)
   * once per active base resume and upserts one base row each.
   *
   * THREE WAYS IN, one function: a save (`addJob`, above), the Job step
   * opening on a saved job with no scored base (`loadBaseScores` in panel.js,
   * once per panel and job — every way in records the job with `scored`, so a
   * failure or an empty answer never loops and a tab round trip never re-asks;
   * Refresh forgets it), and the Job step's footer primary, Update scores,
   * which is the retry and the re-run: the panel cannot see whether a stored
   * score predates an engine change, so re-running stays the user's to ask for.
   *
   * `lead` is the sentence the caller already said ("Saved. Found 3 skills. "),
   * kept in front of this one, success or failure, because the note slot holds
   * one line. `quiet` is the automatic way in: no red note on failure, and a
   * success names the best match only in an empty slot, so a sentence the load
   * wrote is never wiped.
   *
   * NOTHING IS RE-READ AFTERWARDS, which is the one place this diverges from
   * `addJob`'s shape, and the reason is narrower than it first looks: the POST
   * answers for every base slug it can score, so a re-read would learn nothing
   * about the BASES that is not already in hand. Its answer is a SUBSET of what
   * the array holds — the non-base rows exist only in the GET — which is why
   * the assignment below merges rather than replaces. Everything else is
   * `addJob`'s: busy for the length of the call (the Job step's key, so the
   * save's spinner keeps turning), a note on failure, and the generation check
   * on BOTH limbs.
   */
  async function scoreAllBases(store, { lead = "", quiet = false } = {}) {
    if (store.read().busy !== null) return;
    const job = store.read().job;
    if (!job) {
      // The note slot's rather than a throw: this panel has no exception path
      // a click goes through.
      store.write({ note: { text: "Save the job first." } });
      store.render();
      return;
    }
    store.scored(job.id);
    const done = await duringAction(store, "job", () =>
      store.api("/api/ats-scores", {
        method: "POST", body: JSON.stringify({ job_id: job.id }),
      }), `${lead}Couldn't score your base resumes.`, { quiet });
    if (!done) return;
    // No `token` past here, and that is the same divergence the paragraph above
    // names: nothing is re-read, so there is no second round trip to guard.
    const rows = done.out;
    // RE-READ, and this is the handle's rule rather than a nicety: the snapshot
    // taken before the POST describes a store the loaders have been writing to
    // for the length of it.
    const facts = store.read();
    // MERGED, not replaced, and the difference is a ring the user is looking
    // at. `score_all_bases` returns BASE rows only — one `score_target(…,
    // "base_resume", …)` per slug, backend/app/services/ats_score.py — where
    // the GET returns `latest_scores` for every target on this job, the
    // TAILORED application included. This array has TWO readers: the ranking
    // below and `renderAts`' After ring. A wholesale replace deletes the
    // tailored composite of a draft application, so the rings would drop from
    // 72 → 84 to 72 alone until the next navigation re-read it.
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
    const say = (text) => {
      if (!quiet || store.read().note === null) store.write({ note: { text } });
    };
    if (best && best.score !== null) {
      // `loadBaseScores`' rule, and for the same reason: scoring may move the
      // ranking onto a different resume, and it may NOT move a choice the user
      // has already made. The preselected best is what closes the Job step
      // (`stageFor`'s `baseChosen`), and it is named in the note and on the
      // Job row's summary rather than chosen silently.
      if (!facts.baseSelected) store.write({ baseSlug: best.slug });
      say(`${lead}Best match: ${best.display_name || best.slug} (ATS score ${
        Math.round(best.score)}).`);
    } else {
      // Scored, and still nothing to rank: an empty library, or rows the
      // ranking could not put a number on. Saying "best match: undefined"
      // would be the panel claiming a judgement it does not have.
      say(`${lead}Scored, but no base resume got an ATS score.`);
    }
    store.render();
  }

  ns.panelActionsJob = { addJob, scoreAllBases };
})();
