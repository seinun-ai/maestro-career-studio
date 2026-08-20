/* Maestro CS Companion — picking a draft application by hand.
 *
 * One of the concern files behind `ns.panelActions`; `panel/actions.js` is the
 * joiner and carries the whole contract. Read it before adding anything here.
 *
 * THE RULES, restated because a file that only POINTS at them is a file that
 * half-remembers them:
 *
 * - AN ACTION WRITES, holds `busy` for as long as that takes, obeys the
 *   generation rule in full, and never assigns a stage — `stageFor` recomputes
 *   the rail from the store on every render. The pick's whole job is to make
 *   the facts a backend match would have made; the rail moving is a
 *   consequence, not an instruction.
 * - THE `busy` SPAN IS `duringAction`'s, read off the namespace and never
 *   re-implemented — see `panel/actions/during.js`.
 * - NOTHING HERE REACHES FOR ANYTHING: no `card`, no `chrome`, no `document`,
 *   no `fetch`, no timers.
 *
 * WHY THIS IS ITS OWN FILE rather than another function in `actions/job.js`.
 * Add job SAVES a posting. This ARMS an application the user already has. They
 * share a stage body and a busy key (`"job"`) because both run while Job is
 * active, and they are still two concerns — a second writer stuffed into
 * `addJob`'s file is how the next round trip lands outside `duringAction`.
 *
 * FUTURE WORK, recorded and not built: a requisition id (`JR…`) visible on
 * both Workday pages could close this gap without a pick. That is backend
 * matcher work; the pick stays the user's claim until it exists.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const duringAction = ns.panelDuringAction;

  /** Everything a claim is made of, cleared — `pickApplication`'s inverse for
   * the facts it sets about the application, and NOT for page facts or the
   * base choice.
   *
   * ONE DEFINITION because there are now two ways to stop being bound, and
   * they must clear the same fields: the user withdrawing the claim
   * (`unpickApplication`) and the referent turning out to be gone
   * (`dropDeletedApplication`). Written twice, the two would drift by exactly
   * one field, and the field left behind is a fact about an application that
   * is no longer on the surface — the Track stage's evidence line, a stale
   * `pdfReady` arming Fill — which is the shape of the bug this whole round is
   * about.
   *
   * `note` IS NOT HERE, and that is the difference between the two callers:
   * a withdrawal has nothing to say (the user just did it and can see the
   * result), while a deletion has exactly one sentence to say. Spreading this
   * and then naming `note` is what keeps that choice at the call site.
   */
  const UNBOUND = {
    application: null,
    job: null,
    match: "none",
    claimed: false,
    pdfReady: false,
    evidence: null,
    scores: null,
    revisit: null,
  };

  /** The panel's whole vocabulary for a referent that died. ONE string, said
   * by ONE writer, because two sentences about one fact is how a surface ends
   * up contradicting itself in the same note slot. It names the web app rather
   * than the request, because "no longer exists" is a claim about the DRAFT
   * and the user's next move is in Maestro CS, not in this panel. */
  const DELETED_NOTE = "That draft no longer exists in Maestro CS.";

  /** Arm the panel with a draft the user pointed at.
   *
   * THE WIRE is one detail GET plus `match = "exact"`, and that assignment is
   * the same claim `restoreSession` documents at its site: the user chose this
   * target by hand, so `stageFor` must not read anything but `"exact"` as "we
   * do not know" and put Add job over the top of it.
   *
   * REMEMBERED BEFORE THE FIRST AWAIT, and that order is load-bearing — but
   * the hazard is a LOST bridge, not a mis-addressed one. A remember placed
   * after the detail GET could never write the wrong tab: `duringAction`
   * returns null once the generation moves and this action returns with it.
   * What a post-await remember WOULD do is not run at all — on a tab switch,
   * or on a detail GET that merely fails — and a pick whose bridge never
   * landed is the user teaching the session nothing and pausing again on the
   * next wizard page. Pre-await, the bridge exists whatever happens to the
   * GET (pinned by the failed-GET test).
   *
   * WITH ONE EXCEPTION, added by the ghost-binding round and narrowed to the
   * one failure that is an ANSWER rather than a silence: a 404 on the detail
   * GET says the row the picker offered is not there — the list was read
   * before somebody deleted it — and a bridge naming a deleted application is
   * the ghost the next page would arm from. That case takes the entry back out
   * (`dropDeletedApplication`). Every other failure keeps today's behaviour
   * exactly, because every other failure says nothing about whether the
   * application exists.
   *
   * The detail GET then fills in
   * `pdfReady` so Fill arms by data. Scores are loaded after, not a second
   * `loadContext`: the backend still does not know this apply URL, so a reload
   * would apply `match: "none"` and only come back through the session — a
   * flicker of Add job over a pick the user just made.
   *
   * Job facts come off the LIST ROW (`ApplicationSummary` joins them), not
   * off a second job GET: company and title are what the picker already
   * showed, and inventing a round trip to learn them again is a fetch the
   * user did not ask for.
   */
  async function pickApplication(store, applicationId) {
    const facts = store.read();
    if (facts.busy !== null) return;
    const chosen = (facts.applications ?? []).find((app) => app.id === applicationId);
    if (!chosen) return;
    // Read BEFORE the write, which costs nothing (there is no await above it)
    // and is what the 404 limb below needs: `duringAction` hands back `null`
    // for a failure and for a tab switch alike, so the one thing that says
    // which happened is this token still being current.
    const token = store.token();
    store.write({
      application: { id: chosen.id, status: chosen.status ?? "draft" },
      job: {
        id: chosen.job_id,
        company: chosen.job_company,
        title: chosen.job_title,
      },
      match: "exact",
      claimed: true,
      // The application's own base is the user's earlier choice, so Score
      // completes by data rather than asking them to pick again. Without
      // this, Fill stays locked behind a ranking they already made.
      baseSlug: chosen.base_resume || facts.baseSlug,
      baseSelected: Boolean(chosen.base_resume) || facts.baseSelected === true,
      // The attach belonged to the application being replaced. Without this the
      // Fill row goes on reporting the OLD application's filename as attached
      // to this page, and — because the offer is gone once something is
      // attached — the newly picked application's PDF cannot be attached at all
      // without reloading. NOT `fileInputs`: how many upload boxes this page
      // has is a fact about the PAGE, and the page has not changed.
      attached: null,
    });
    store.remember();
    store.render();
    // THE 404 IS CAUGHT HERE rather than read off `duringAction`, and the
    // narrowing is deliberate. That helper's contract is "either an answer or
    // nothing you may paint" — it has already put the failure in the note slot
    // and cleared `busy`, and widening its return so every caller could inspect
    // a status would put the discrimination in nine actions that have no use
    // for it. A `catch` that re-throws changes nothing about what the helper
    // does; it only lets this one action remember WHY.
    let deleted = false;
    const done = await duringAction(store, "job", () =>
      store.api(`/api/applications/${applicationId}`).catch((err) => {
        deleted = err?.status === 404;
        throw err;
      }));
    if (!done) {
      // THE LIST WAS STALE. The pre-await remember is still right for every
      // other failure — see above; the hazard it exists for is a LOST bridge —
      // but a bridge pointing at a draft the backend says is gone is not a
      // bridge, it is the ghost the next wizard page would arm from. So this
      // is the one failure that takes the entry back out, and it is safe to
      // narrow to precisely because the user cannot lose anything they still
      // have: the row they clicked is not there any more.
      //
      // `current(token)` for the generation rule's usual reason and one more:
      // `done` being null ALSO means "the user switched tabs", and a `deleted`
      // flag set on the way past is about the page they left.
      if (deleted && store.current(token)) dropDeletedApplication(store);
      return;
    }
    const detail = done.out;
    store.write({
      pdfReady: Boolean(detail.pdf_path),
      evidence: store.build.evidenceFrom(detail),
      application: {
        id: chosen.id,
        status: detail.status ?? chosen.status ?? "draft",
      },
      note: { text: `Using ${chosen.job_company} · ${chosen.job_title}.` },
    });
    store.remember();
    store.render();
    await store.loadBaseScores(token);
  }

  /** Withdraw a claim. Not un-saving: the draft stays in the backend; only
   * this panel's binding to this page changes.
   *
   * SYNCHRONOUS — no round trip, no `duringAction` span. The write set is
   * `UNBOUND` above — `pickApplication`'s inverse for the facts it set about
   * the application, and not for page facts or the base choice — plus a note
   * cleared, because a withdrawal the user just performed needs no sentence.
   * Then `remember()` so the bridge entry rewrites application-less;
   * `sessionEntryFrom` already treats those as legal and they already carry
   * the base.
   *
   * A backend exact-match is not a claim and cannot be withdrawn here.
   */
  function unpickApplication(store) {
    const facts = store.read();
    if (facts.busy !== null) return;
    if (facts.claimed !== true) return;
    store.write({ ...UNBOUND, note: null });
    store.remember();
    store.render();
  }

  /** The same unbinding, made by the BACKEND rather than by the user: this
   * page is bound to an application that no longer exists.
   *
   * WHAT ENTITLES IT. Only a 404 on the application's OWN resource reaches
   * here — the callers do that discrimination (`pickApplication` above,
   * `loadContext` in panel.js) and neither may hand a network failure, a
   * timeout or a 5xx to this function. The bridge's tolerance of an
   * unreachable backend is a deliberate design, not an oversight: a user on a
   * flaky connection, or with the backend not yet started, keeps their binding
   * across the whole wizard. Forgetting a pick because one GET did not come
   * back would break exactly that, and it would do it silently.
   *
   * `remember()` IS THE POINT, not a tidy-up. Clearing the store alone leaves
   * the bridge entry naming the dead application on disk, and the very next
   * wizard page restores it — the ghost re-arms, the chip comes back, and the
   * Open-application link goes on landing in the web app's "this application
   * no longer exists". The store write is what the user sees now; the rewrite
   * is what makes it stay true.
   *
   * `claimed !== true` REFUSES A BACKEND MATCH, deliberately. This clears
   * `match` and `job` as well, which is honest about a memory the panel
   * restored — every one of those facts came out of the same dead entry — and
   * would NOT be honest about a page `/api/jobs/match` just named: there the
   * job is the backend's own answer about this url and it outlives whatever
   * happened to one application row.
   *
   * THE DEAD ROW LEAVES THE PICKER with it. The list is a cache of drafts read
   * a moment ago, and we now know one of its rows is gone; leaving it there
   * would offer the user the very draft that just failed, and the pick would
   * fail the same way. `null` (never loaded) stays `null` — an absent list is
   * not an empty one, and inventing one here would tell the Job body there are
   * no drafts.
   *
   * NO `busy` GUARD, unlike both siblings, and the omission is the decision:
   * a backend-initiated drop must not be refused because something else is in
   * flight. The consequence nobody should rediscover the hard way: an action
   * already running when the drop lands finishes into the same note slot, so
   * its own sentence can replace DELETED_NOTE before the user reads it — they
   * are unbound either way; only the sentence can be lost.
   */
  function dropDeletedApplication(store) {
    const facts = store.read();
    if (facts.claimed !== true) return;
    const dead = facts.application?.id ?? null;
    store.write({
      ...UNBOUND,
      // A statement, not a failure: nothing went wrong with the request and
      // the user did nothing wrong, so it is not painted as an error.
      note: { text: DELETED_NOTE },
      applications: facts.applications === null || dead === null
        ? facts.applications
        : facts.applications.filter((app) => app.id !== dead),
    });
    store.remember();
    store.render();
  }

  ns.panelActionsPick = { pickApplication, unpickApplication,
                          dropDeletedApplication };
})();
