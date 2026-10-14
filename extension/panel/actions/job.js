/* Maestro CS Companion — the Job stage's actions: save the job, score the base
 * resumes against it (the Score step's action until Score merged into Job,
 * 2026-09-27), and — with full automation on — Queue and Apply. A save runs the
 * scoring in the same press; Queue is a save plus the user's yes; Apply is
 * Queue plus the resume plus a one-job run in THIS tab, drawn as a checklist with
 * a Stop, and (a Settings switch) split into one press per step.
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
  const { rankBaseResumes, describesJob, applyFacts, httpUrl, applyLink, preselect, applyPress } = ns.decisions;

  /** The backend's two refusals of a job the scorer cannot read yet, both 422:
   * no skills in its description (`normalize_jd`), or no description read at
   * all (`get_scorable_job`). Matched on the sentence because the status is
   * shared with every other refusal of the call; pinned against the backend's
   * own text by `test_the_panel_recognises_the_backends_own_unreadable_job_sentences`.
   * Both name Refresh details, a control of the web app's job page, so the
   * panel's next step says where it is. */
  const UNREADABLE_JOB = /No skills were found in this job's description|This job's description hasn't been read yet/;
  const REFRESH_STEP = "Open the job in Maestro CS and choose Refresh details.";

  /** What Save job says when the page gave it nothing to save: no title and no
   * job description (`describesJob`). Posting the page's text anyway stored a
   * job with no title, no company and no skills — a careers site's navigation,
   * around a posting its iframe held (iCIMS, 2026-09-30). */
  const UNREAD_POSTING = "The Companion couldn't read this job's description from the page. "
    + "Open the job post on its own page, or add the job in Maestro CS.";

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
  async function addJob(store, { as = "job", reload = true, steps = null } = {}) {
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
    // Text, but not a posting: no title to name it, nothing the extractor
    // found by a job signal, and nothing the user typed into the preview (a
    // description pasted into a box is theirs to save).
    if (!String(facts.preview?.title ?? "").trim() && !describesJob(facts.preview)
        && facts.previewTyped !== true) {
      store.write({ note: { text: UNREAD_POSTING } });
      store.render();
      return;
    }
    // The tab this posting came off may not be the tab the answer arrives on —
    // `duringAction` holds that guard on both limbs and hands back `null` when
    // there is nothing here left to say.
    const done = await duringAction(store, as, () => {
      steps?.begin("save", "Saving the job");
      return store.api("/api/jobs", { method: "POST", body: JSON.stringify(body) });
    }, "Couldn't save the job.");
    if (!done) return steps?.fail();
    steps?.done("save");
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
    // A Stop pressed during the save ends the press here: scoring is the next call, and it is not sent.
    if (steps?.halted()) return;
    await scoreAllBases(store, { lead: `${saved} `, as, steps });
    if (!store.current(token)) return;
    // Queue and Apply go on from here and re-read when they end, so they ask for no reload now.
    if (!reload) return;
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
  async function scoreAllBases(store, { lead = "", quiet = false, as = "job", steps = null } = {}) {
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
    const what = `${lead}Couldn't score your base resumes.`;
    const done = await duringAction(store, as, () => {
      steps?.begin("score", "Scoring your resumes");
      return store.api("/api/ats-scores", {
        method: "POST", body: JSON.stringify({ job_id: job.id }),
      });
    }, {
      what,
      answered: (err) => (err.status === 422 && UNREADABLE_JOB.test(String(err.message))
        ? `${what} ${REFRESH_STEP}` : null),
    }, { quiet });
    if (!done) return steps?.fail();
    steps?.done("score");
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
      if (!facts.baseSelected && !facts.baseFromApplication) {
        // The best match, or with full automation on only a clear win (`preselect`): the note below
        // still names the best match, which is a fact about the ranking, not a pick.
        const slug = preselect(facts, ranked);
        if (slug !== undefined) store.write({ baseSlug: slug });
      }
      say(`${lead}Best match: ${best.display_name || best.slug} (match score ${
        Math.round(best.score)}).`);
    } else {
      // Scored, and still nothing to rank: an empty library, or rows the
      // ranking could not put a number on. Saying "best match: undefined"
      // would be the panel claiming a judgement it does not have.
      say(`${lead}Scored, but no base resume got a match score.`);
    }
    store.render();
  }

  // ---------- Queue and Apply (full automation on) ----------

  const QUEUED = "Queued. Apply to queued will pick it up.";
  const ALREADY_APPLIED = "You've already applied to this job.";
  const RUN_GOING = "A run is already going in this tab.";
  const FINISH_FIRST = "You're tailoring this job in Maestro. Finish it, then press Apply.";
  const TAILOR_BLOCKED = "Couldn't tailor your resume. Use Tailor in Maestro CS to see what's in the way.";
  // A proposal that is already in motion in the web app, as its chip words it.
  const IN_MOTION = { needs_decision: "Needs you", needs_human: "Needs you", approved: "Approved" };
  const COMPANION_YES = { status: "accepted", consent: { channel: "companion" } };

  /** An error whose words are already the sentence for the note (`failureNote` passes `shown` ones
   * through untouched). */
  function shown(sentence) {
    return Object.assign(new Error(sentence), { shown: true });
  }

  /** Where a job the always-on copy holds stands, in words. Only reached when the job cannot be run
   * from this copy: with the laptop's own offer pending, Keep it here is Apply's own first move. */
  function heldSentence(ownership) {
    if (ownership.handover === "returning") {
      return "This job is on its way back to your laptop. Try again after the next sync.";
    }
    return "This job is with your bot. Ask for it back with Work on it here in Maestro CS, then press Apply.";
  }

  const canRunHere = (ownership) => !ownership || ownership.owned_here === true || ownership.can_keep_here === true;

  /** The proposal body: the job, and the Job step's pick with the panel's own scores (the web app's
   * Queue sends the same shape, `promoteJobToAgentQueue`, with its best match as the pick). */
  function proposalBody(facts) {
    const rows = (facts.scores ?? []).filter((row) => row?.target_type === "base_resume" && row?.phase === "base");
    return {
      job_id: facts.job.id,
      fit: rows.length && facts.baseSlug
        ? { chosen_base: facts.baseSlug, scores: Object.fromEntries(rows.map((row) => [row.target_id, row.composite])),
            decided_by: "user" }
        : null,
      plan: { summary: "Queued from the Companion by the user" },
      proposed_by: "you",
    };
  }

  /** The user's yes: a proposal for the job, accepted under the Companion's own consent channel (the
   * server takes `companion` from the extension's origin and only to queue). A job already queued is
   * left alone; one that is already in motion in the web app is not ours to move. Returns
   * `{id}` or `{stop}`; the server's own sentence for a refusal (a skipped job, the skip list, the
   * other copy) is shown as it is, because it is written for a person. */
  async function queueProposal(store, facts, read) {
    if (read.queued && read.proposalId) return { id: read.proposalId };
    try {
      let prop = await store.api("/api/proposals", { method: "POST", body: JSON.stringify(proposalBody(facts)) });
      if (prop.status === "pending_review") {
        prop = await store.api(`/api/proposals/${encodeURIComponent(prop.id)}`,
          { method: "PATCH", body: JSON.stringify(COMPANION_YES) });
      }
      if (prop.status === "accepted") return { id: prop.id };
      return { stop: `This job is already in the Agent inbox (${IN_MOTION[prop.status] ?? prop.status}). `
        + "Open it in Maestro CS to carry on." };
    } catch (err) {
      throw err.status === 409 ? shown(`Couldn't queue the job. ${err.message}`) : err;
    }
  }

  /** Queue: save the job as today (extract and score), then the user's yes. The note names what
   * happened; Apply to queued, in the Queue view, picks the job up later. */
  async function queueJob(store) {
    if (store.read().busy !== null || store.read().fullAutomation !== true) return;
    const token = store.token();
    if (!store.read().job) {
      await addJob(store, { as: "queue", reload: false });
      // The press belongs to the tab it was made on: a stale answer finds a different job in the store.
      if (!store.current(token) || !store.read().job) return;
    }
    const facts = store.read();
    const done = await duringAction(store, "queue", async () => {
      const read = await readApplyFacts(store, facts.job.id);
      if (read.applied) return { stop: ALREADY_APPLIED };
      return queueProposal(store, facts, read);
    }, { what: "Couldn't queue the job.", answered: "Couldn't queue the job. Try again." });
    if (!done) return;
    store.write({ note: { text: done.out.stop ?? QUEUED } });
    store.render();
    await store.loadContext(done.token);
  }

  /** What the server holds for the job now (its detail and its tailoring sessions), picked out by
   * `applyFacts`. Read at press time rather than trusted from the page: the user may have started a
   * custom tailoring, or applied, in the web app since. */
  async function readApplyFacts(store, jobId) {
    const id = encodeURIComponent(jobId);
    const [detail, sessions] = await Promise.all([
      store.api(`/api/jobs/${id}/detail`), store.api(`/api/tailoring-sessions?job_id=${id}`)]);
    return applyFacts(detail, sessions);
  }

  /** The job is this copy's to work on, or a sentence saying why not. With sync on, queueing offers
   * the job to the always-on copy at the next round (`mark_when_queued`), and its routes then
   * refuse this copy; Apply is the user saying "here", so it claims the job first (Keep it here).
   * Re-read after the queue write, because that write is what offers it. */
  async function claimHere(store, jobId) {
    const id = encodeURIComponent(jobId);
    const now = await store.api(`/api/jobs/${id}`);
    const held = now?.ownership;
    if (!held || held.owned_here) return null;
    if (!held.can_keep_here) return heldSentence(held);
    await store.api(`/api/jobs/${id}/keep-here`, { method: "POST" });
    return null;
  }

  /** A resume for a job that has none: Quick tailor with the Job step's pick, or the base resume as
   * it stands. Reached only when the job has no application AND no open custom session of the
   * user's (or the user chose Apply with the base resume), so nothing of theirs is replaced. Quick
   * tailor with nothing to change leaves a session open on its own; it is closed here so it does
   * not read as the user's own custom tailoring on the next press. */
  async function newResume(store, jobId, base, withBase) {
    const id = encodeURIComponent(jobId);
    if (!withBase) {
      let out;
      try {
        out = await store.api(`/api/jobs/${id}/quick-tailor`, { method: "POST", body: JSON.stringify({ base_resume: base }) });
      } catch (err) {
        throw err.status === 409 ? shown(TAILOR_BLOCKED) : err;
      }
      if (!out.nothing_to_tailor) return { applicationId: out.application_id, pdfReady: out.pdf_ready !== false };
      await store.api(`/api/tailoring-sessions/${encodeURIComponent(out.session_id)}/close`, { method: "POST" })
        .catch((err) => console.warn("[maestro-cs] could not close the empty tailoring session:", err));
    }
    const made = await store.api("/api/applications/from-base", {
      method: "POST", body: JSON.stringify({ job_id: jobId, base_resume: base, ops: [] }) });
    return { applicationId: made.id, pdfReady: Boolean(made.pdf_path) };
  }

  /** Remember the page a hand-picked job was applied on, so the next visit matches it
   * (`/api/jobs/match` reads the apply link). A convenience: a page that names no posting (`applyLink`
   * is null: a sign-in page, a job board) is not saved, a job that has a link keeps it, and a refused
   * write (a job another copy holds, an offline server) must not stop the run. */
  async function saveApplyLink(store, jobId, url) {
    const link = applyLink(url);
    if (!link) return;
    try {
      await store.api(`/api/jobs/${encodeURIComponent(jobId)}`, {
        method: "PATCH", body: JSON.stringify({ apply_url: link }) });
    } catch (err) {
      console.warn("[maestro-cs] could not save the page as the job's apply link:", err);
    }
  }

  const PICK_AGAIN = "That draft is no longer this job's open draft. Pick it again.";

  /** The draft the user picked, as the server holds it: the job's NEWEST application is not
   * necessarily the one they named. Returns `{id, hasPdf, baseResume}` or a `{stop}` sentence when the
   * draft is gone, is another job's, or is no longer a draft. */
  async function pickedDraft(store, applicationId, jobId) {
    let draft;
    try {
      draft = await store.api(`/api/applications/${encodeURIComponent(applicationId)}`);
    } catch (err) {
      if (err.status === 404) return { stop: PICK_AGAIN };
      throw err;
    }
    if (draft?.job_id !== jobId || (draft.status ?? "draft") !== "draft") return { stop: PICK_AGAIN };
    return { id: applicationId, hasPdf: Boolean(draft.pdf_path), baseResume: draft.base_resume ?? null };
  }

  // ---------- the Apply checklist ----------

  const PICK_NOTE = "Pick a resume to apply with.";
  const ANOTHER_TAB = "Another tab is already applying to this job. Finish or stop that run first.";
  /** A job another copy holds is a stop with a line of its own: nothing was running to cross. */
  const heldStop = (sentence) => ({ stop: sentence, line: "Using this copy of the job", why: "Held elsewhere" });
  const WAITING = "Waiting for your pick";
  const READY_NOTE = "Resume ready. Press Start filling to go on.";

  /** What each line says when a step goes wrong, and what the user's Stop came after. Fixed sentences:
   * the checklist never shows a server's words, the note below it carries whatever the panel may say. */
  const WHY = {
    save: "Couldn't save", score: "Couldn't score", queue: "Couldn't queue", tailor: "Couldn't tailor",
    pdf: "Couldn't make the PDF", link: "Couldn't link", open: "Couldn't open",
  };
  const AFTER = {
    save: "saving the job", score: "scoring your resumes", base: "choosing the resume",
    queue: "queueing the job", tailor: "tailoring the resume", pdf: "making the PDF",
    link: "linking the resume to the job",
  };

  /** The live checklist of one Apply press (`applySteps` in the store, drawn by stages/job.js), and the
   * Stop that ends it.
   *
   * A line is a step: `begin` shows it running (and says it through the footer note, which is the
   * panel's persistent live region: the rail is rebuilt on every paint, so a region inside it would be
   * a new node each time and a screen reader would hear nothing), `done` ticks it, `fail` crosses the
   * running one with a fixed reason, `put` adds one already true ("Using your tailored resume"). A step
   * that was not needed is never added. `halted` is the Stop, read at the boundaries between steps and
   * never inside a call: a request sent is not cancelled halfway, and what was done stays done.
   *
   * Every write is guarded by the press's generation (`store.current`), so a tab switched mid-press
   * leaves the new tab's panel alone. */
  function applyChecklist(store, token) {
    const lines = [];
    const state = { live: true, stopped: null };
    let over = false;
    const paint = () => {
      if (over || !store.current(token)) return;
      store.write({ applySteps: { ...state, lines: lines.map((one) => ({ ...one })) } });
      store.render();
    };
    const say = (text) => {
      if (!over && store.current(token)) store.write({ note: { text } });
    };
    const last = (wanted) => lines.findLast((one) => one.state === wanted);
    return {
      /** The panel's Apply starts a fresh list, and a Stop pressed for the last one is forgotten. */
      open() {
        store.write({ applySteps: { ...state, lines: [] }, applyStop: false });
        store.render();
      },
      begin(key, text, extra = {}) {
        lines.push({ key, text, state: "run", after: AFTER[key], ...extra });
        say(`${text}…`);
        paint();
      },
      done(key) {
        const line = lines.findLast((one) => one.key === key);
        if (line) line.state = "done";
        paint();
      },
      put(key, text, extra = {}) {
        lines.push({ key, text, state: "done", after: AFTER[key], ...extra });
        paint();
      },
      /** The step that was running did not finish. A stop that happened between steps names the line it
       * stopped on (`line`, a fixed phrase) so it is crossed too, with its own fixed reason. */
      fail(why, line = null) {
        const running = last("run");
        if (running) Object.assign(running, { state: "fail", why: why ?? WHY[running.key] });
        else if (line) lines.push({ key: "stop", text: line, state: "fail", why });
        paint();
      },
      /** Nothing is running; the next move is the user's. */
      wait() {
        lines.push({ key: "wait", text: WAITING, state: "wait" });
        paint();
      },
      // A press whose tab was left (the generation moved, which also reset the Stop flag with the page's
      // facts) counts as stopped: carrying on would write to a job nobody is looking at.
      halted: () => over || !store.current(token) || store.read().applyStop === true,
      /** Say where the Stop landed: after the last step that finished. */
      stopped() {
        state.stopped = last("done")?.after ?? "the last step";
        say(`Stopped after ${state.stopped}.`);
        paint();
      },
      end() {
        state.live = false;
        paint();
        // Nothing of this press paints again: a newer press owns the checklist from here.
        over = true;
      },
      /** The run takes over: the card drawn from here on is its own. */
      clear() {
        if (!over && store.current(token)) store.write({ applySteps: null, applyStop: false });
        over = true;
      },
    };
  }

  /** Is the job known: it has an id. A remembered pick (`restoreSession`) puts the job's id in the store on a
   * page the backend did not match, and saving that page again would make a second copy of the job. */
  const savedJob = (facts) => Boolean(facts.job?.id);

  /** The line that names the resume Apply is using, with its square (drawn by stages/job.js from `hue`)
   * and its match score for this job when there is one. */
  function showBase(store, steps, slug) {
    const facts = store.read();
    const entry = rankBaseResumes(facts.resumes, facts.scores).find((one) => one.slug === slug);
    const name = entry?.display_name || slug;
    const scored = entry && entry.score !== null ? ` (${Math.round(entry.score)})` : "";
    steps.put("base", `Using ${name}${scored}`, { hue: entry?.color_hue ?? null });
  }

  /** Everything between the press and the run, as one span of `busy`: the user's yes, the claim on
   * the job, a resume that is ready, and the proposal tied to its application. Returns `{stop}`
   * (a sentence: nothing more was done), `{halted}` (the user's Stop landed), `{ready}` (a press that
   * goes only as far as the resume: Tailor resume, Make PDF) or `{seed, application}` for `startRun`.
   * `through` says how far the press goes: `"resume"` or `"start"`.
   *
   * EVERY STAGE RE-READS WHAT THE SERVER HOLDS and does only what is missing, which is what lets "Stop
   * after each step" be three presses of one function. The user's yes (the queue) is the first move
   * of a press that goes on to the run, and the whole of Apply with the switch off, so a step press
   * that only readies the resume queues nothing.
   *
   * A CLAIMED binding (the user named the job's draft on a page the backend did not match) runs
   * `inPlace`: the pick says this page IS that job's application, so the run's link is this page and
   * the job's saved links (a board's, say) are never opened, and the application is the draft they
   * named, not the job's newest. */
  async function prepareApply(store, facts, { withBase, through, steps }) {
    const jobId = facts.job.id;
    const read = await readApplyFacts(store, jobId);
    if (read.applied) return { stop: ALREADY_APPLIED, line: "Opening the application", why: "Already applied" };
    if (!canRunHere(read.ownership)) return heldStop(heldSentence(read.ownership));
    // Another tab's run holds this job's proposal: a relink under it would move the application the run
    // is filling. The server cannot see the panel's runs, so the panel checks.
    if (read.proposalId && store.read().runs.some((one) => one.proposalId === read.proposalId
        && !ns.panelActionsRun.TERMINAL.has(one.status))) {
      return { stop: ANOTHER_TAB, line: "Opening the application", why: "Running in another tab" };
    }
    const inPlace = facts.claimed === true;
    // Before anything is written: a pick that no longer stands is the user's to make again.
    const picked = inPlace ? await pickedDraft(store, facts.application?.id, jobId) : null;
    if (picked?.stop) return picked;
    let applicationId = picked ? picked.id : read.applicationId;
    let pdfReady = picked ? picked.hasPdf : read.hasPdf;
    const base = (picked ? picked.baseResume : read.baseResume) ?? facts.baseSlug;
    // The user's own custom tailoring is never tailored over; the other way round it is theirs to choose.
    const finishFirst = applicationId === null && read.sessionId && !withBase;
    // Nothing picked and nothing to make a resume from: stop before anything is written. The list is
    // unlocked, and picking is what the user does next.
    if (applicationId === null && !finishFirst && !base) return { stop: PICK_NOTE, pick: true };
    if (base) showBase(store, steps, base);
    if (steps.halted()) return { halted: true };
    let proposalId = null;
    if (through === "start") {
      if (!read.queued) steps.begin("queue", "Queueing the job");
      const queued = await queueProposal(store, facts, read);
      if (queued.stop) return queued;
      if (!read.queued) steps.done("queue");
      proposalId = queued.id;
      if (read.ownership) {
        const held = await claimHere(store, jobId);
        if (held) return heldStop(held);
      }
      if (steps.halted()) return { halted: true };
    }
    if (applicationId === null) {
      if (finishFirst) {
        return { stop: FINISH_FIRST, line: "Tailoring the resume", why: "Finish it in Maestro CS" };
      }
      steps.begin("tailor", withBase ? "Using your base resume" : "Tailoring the resume");
      ({ applicationId, pdfReady } = await newResume(store, jobId, base, withBase));
      steps.done("tailor");
    } else {
      steps.put("tailor", "Using your resume for this job", { after: "choosing your resume" });
    }
    if (steps.halted()) return { halted: true };
    if (!pdfReady) {
      steps.begin("pdf", "Making the PDF");
      await store.api(`/api/applications/${encodeURIComponent(applicationId)}/render`, { method: "POST" });
      steps.done("pdf");
      if (steps.halted()) return { halted: true };
    }
    if (through === "resume") return { ready: true, application: { id: applicationId } };
    steps.begin("link", "Linking the resume to the job");
    try {
      await store.api("/api/proposals", {
        method: "POST", body: JSON.stringify({ job_id: jobId, application_id: applicationId }) });
    } catch (err) {
      throw err.status === 409 ? shown(`Couldn't link the resume to the job. ${err.message}`) : err;
    }
    steps.done("link");
    // Sync can deliver a link that never met the server's check, so it is vouched for here: http(s) only.
    const openUrl = inPlace ? httpUrl(facts.url)
      : httpUrl(read.applyUrl) ?? httpUrl(read.sourceUrl) ?? httpUrl(facts.url);
    if (!openUrl) {
      return { stop: "This job has no web link the Companion can open.", line: "Opening the application",
               why: WHY.open };
    }
    if (inPlace && !read.applyUrl) await saveApplyLink(store, jobId, openUrl);
    // The last point a Stop can land: after this the run is the card, with its own Stop.
    if (steps.halted()) return { halted: true };
    steps.begin("open", "Opening the application");
    return {
      application: { id: applicationId },
      seed: { proposalId, jobId, applicationId, company: facts.job.company ?? null,
              location: read.location ?? facts.job.location ?? null,
              title: facts.job.title ?? null, baseSlug: base, openUrl, sourceUrl: httpUrl(read.sourceUrl),
              ...(inPlace ? { inPlace } : {}) },
    };
  }

  /** After a press that saved the job (Save job, with "Stop after each step" on or "Choose the base
   * resume for me" off): say which resume is selected, or that the user is to pick. The scoring already
   * ran, and with it the pick (`preselect`); this only reports it. */
  function reportPick(store, steps) {
    const { baseSlug } = store.read();
    if (baseSlug) {
      showBase(store, steps, baseSlug);
      return;
    }
    steps.wait();
    store.write({ note: { text: PICK_NOTE } });
  }

  /** Apply: Queue, then run this one job in THIS tab. `start` is the run host's `startRun` and
   * `running` its `runningHere`, handed in by the roster (an action reaches no other action). Everything up to the run holds one `busy`
   * span; the run itself is not an action and holds none (it has its own card and Stop).
   *
   * ONE PRESS GOES AS FAR AS `ns.decisions.applyPress` SAYS: to the run (Apply, Start filling), to a
   * ready resume (Tailor resume, Make PDF), or only to a saved and scored job (Save job). Beside it the
   * checklist says what is happening, and its Stop ends the press at the next boundary.
   *
   * `withBase` is the open-custom-session state's "Apply with the base resume": the same road, but
   * the base resume stands in for the tailoring the user has not finished, and their session is
   * never touched. Submit is nowhere in this file: the run stops at the review. */
  async function applyJob(store, { start, running, withBase = false }) {
    if (store.read().busy !== null || store.read().fullAutomation !== true) return;
    // Between two of its round trips `busy` is released; the checklist is what says a press is still going.
    if (store.read().applySteps?.live === true) return;
    // A binding taken from a run record is not the user's pick for this page: not ours to apply in place.
    if (store.read().claimed === true && store.read().claimFrom !== "pick") return;
    // Before any write: queueing, tailoring and linking a job to a tab that cannot take its run is work
    // the user would then have to find and undo.
    if (running()) {
      store.write({ note: { text: RUN_GOING } });
      store.render();
      return;
    }
    const token = store.token();
    const { through } = applyPress(store.read());
    const steps = applyChecklist(store, token);
    steps.open();
    try {
      await runApply(store, token, steps, { start, withBase, through });
    } finally {
      steps.end();
    }
  }

  async function runApply(store, token, steps, { start, withBase, through }) {
    // The Save job press saves a page the backend has not matched even when a remembered pick named a job
    // for it (the button says Save job, and `applyPress` reads the match); every other press goes on
    // from a job that is known.
    const unsaved = (facts) => !savedJob(facts) || (through === "save" && facts.match !== "exact");
    if (unsaved(store.read())) {
      await addJob(store, { as: "apply", reload: false, steps });
      if (!store.current(token) || unsaved(store.read())) return;
      if (steps.halted()) {
        steps.stopped();
        return;
      }
      if (through === "save") {
        // Reported inside the press, then Stop goes before the re-read that shows what the save made true.
        reportPick(store, steps);
        steps.end();
        await store.loadContext(token);
        return;
      }
    } else if (through === "save") {
      return;
    }
    const facts = store.read();
    const done = await duringAction(store, "apply", () => prepareApply(store, facts, { withBase, through, steps }), {
      what: "Couldn't start the application.", answered: "Couldn't start the application. Try again." });
    if (!done) {
      steps.fail();
      return;
    }
    const out = done.out;
    if (out.halted) {
      steps.stopped();
    } else if (out.stop) {
      if (out.pick) steps.wait();
      else steps.fail(out.why, out.line);
      store.write({ note: { text: out.stop } });
    } else if (out.ready) {
      // The resume exists now and the user's next press is the run.
      store.write({ application: { id: out.application.id, status: "draft" }, pdfReady: true,
                    note: { text: READY_NOTE } });
      store.remember();
    } else {
      // The application exists now, whatever the run does next.
      store.write({ application: { id: out.application.id, status: "draft" }, pdfReady: true, note: null });
      steps.clear();
      store.render();
      store.remember();
      await start(out.seed);
      return;
    }
    // The press is over; Stop goes before the re-read that follows it.
    steps.end();
    store.render();
    await store.loadContext(done.token);
  }

  /** Apply with the base resume: the open-custom-session state's way on. */
  function applyWithBase(store, options) {
    return applyJob(store, { ...options, withBase: true });
  }

  ns.panelActionsJob = { addJob, scoreAllBases, queueJob, applyJob, applyWithBase };
})();
