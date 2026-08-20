/* Maestro CS Companion — the Resume stage's two actions.
 *
 * One of the concern files behind `ns.panelActions`; `panel/actions.js` is the
 * joiner and carries the whole contract. Read it before adding anything here.
 *
 * THE RULES, restated because a file that only POINTS at them is a file that
 * half-remembers them:
 *
 * - AN ACTION WRITES, holds `busy` for as long as that takes, obeys the
 *   generation rule in full, and never assigns a stage — `stageFor` recomputes
 *   the rail from the store on every render.
 * - THE `busy` SPAN IS `duringAction`'s, read off the namespace and never
 *   re-implemented here — see `panel/actions/during.js`.
 * - NOTHING HERE REACHES FOR ANYTHING: an action reads through the handle,
 *   writes through the handle, and asks the handle to paint.
 *
 * THREE ACTIONS, AND TWO OF THEM ASK THE BACKEND FOR NOTHING. `useBaseAsIs`
 * and its withdrawal `stopUsingBaseAsIs` have no round trip and therefore no
 * `duringAction` and no token — they are still actions rather than body
 * callbacks because of what they COMMIT to, which their own docstrings explain.
 * All three are in one file because they are one fork: the two limbs the user
 * chooses between, and the way back out of the limb that finishes the stage.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const duringAction = ns.panelDuringAction;

  /** Quick tailor: one POST, and the panel has an application with a rendered
   * PDF behind it.
   *
   * EVERY FAILURE READS THE SAME WAY, deliberately: a health gate and an
   * in-progress session share one status and one string field, so a heading
   * per status code would be a claim about which of them happened.
   *
   * FOUR THINGS THIS DELIBERATELY DOES NOT DO, each written down because the
   * obvious alternative is wrong here:
   *
   * - `out.compare` is dropped rather than stored. The panel's Before → After
   *   rings read `latest_scores` rows (design §4.2: render them, compute
   *   nothing), and `ats_score.compare` PERSISTS the pair it computes — so the
   *   honest way to make the After ring true is to re-read the rows, which is
   *   what the tail of this function does. A second home for the same numbers
   *   is how two parts of one surface end up disagreeing.
   * - `health_warning` is FOLDED INTO the sentence rather than said first.
   *   Said first, it is overwritten by the next note on every path and becomes
   *   a line nobody ever reads; one note slot means one sentence, and the
   *   warning is part of what just happened.
   * - the application is stored as `{id, status}` where `fastTailor` writes
   *   four fields, adding `job_company` and `job_title` from the job it just
   *   tailored for. Nothing on this surface reads them: the identity card
   *   renders `card.job`, which is the same two strings from the source the
   *   backend confirmed. They exist in the store only where `restoreSession`
   *   copies them off a session entry, so writing them here would be a second,
   *   quietly divergent home for a company name this panel already has.
   * - the session is REMEMBERED on the render-failure path too, not only on
   *   full success. The application exists the moment
   *   the POST returns — the render is a separate server-side step that failed
   *   after the tailor committed — so forgetting it would mean the next page
   *   of the wizard offering to tailor a job that already has one. Written at
   *   the bottom of this function for both paths, which is why the call is not
   *   inside either branch.
   */
  async function quickTailor(store) {
    const facts = store.read();
    if (facts.busy !== null) return;
    // The note slot's rather than a throw: this panel has no exception path a
    // click goes through, so a throw here would be a silent no-op.
    if (!facts.job) {
      store.write({ note: { text: "Add the job first." } });
      store.render();
      return;
    }
    if (!facts.baseSlug) {
      store.write({ note: { text: "Pick a base resume first." } });
      store.render();
      return;
    }
    // A tailor is the longest round trip this surface makes, so it is the limb
    // the user is most likely to have walked away from — `duringAction`'s guard
    // on BOTH limbs is load-bearing here rather than merely correct.
    const done = await duringAction(store, "resume", () =>
      store.api(`/api/jobs/${facts.job.id}/quick-tailor`, {
        method: "POST", body: JSON.stringify({ base_resume: facts.baseSlug }),
      }));
    if (!done) return;
    const { token, out } = done;
    // The warning rides whichever sentence follows it.
    const warning = out.health_warning ? `⚠ ${out.health_warning} ` : "";
    if (out.nothing_to_tailor) {
      // A 200 with nothing done: no gap this profile is allowed to resolve.
      // The session is left open server-side for a custom pass, which is what
      // "open it in Maestro CS" means here — and no application was created,
      // so nothing about the store moves.
      store.write({ note: { text: `${warning}Nothing to tailor. No gap this profile is `
        + "allowed to resolve. Attach the base resume instead, or open it in "
        + "Maestro CS." } });
      store.render();
      return;
    }
    // Rendering is server-side and can fail after the tailor has COMMITTED, so
    // this is not an error path: the application exists either way, and the
    // web app shows `render_error` and can re-render. `!== false` because a
    // response that omits the key has told us nothing, and the honest reading
    // of nothing is the one that keeps offering to tailor.
    const pdfReady = out.pdf_ready !== false;
    const applied = (out.applied ?? []).length;
    store.write({
      application: { id: out.application_id, status: "draft" },
      pdfReady,
      note: pdfReady
        ? { text: applied
          ? `${warning}Tailored. ${store.build.plural(applied, "change")} applied.`
          : `${warning}Tailored.` }
        : { text: `${warning}Tailored, but the PDF render failed. Open `
          + "it in Maestro CS to see why and re-render.", error: true },
    });
    store.render();
    // WRITTEN DOWN NOW, on the failure path as much as the success one:
    // the application exists as soon as the POST returned, and it is the most
    // valuable thing this panel has ever had to remember — losing it to a
    // failed render would mean the next page of the wizard offering to tailor
    // a job that already has an application.
    store.remember();
    // The After ring, and the one read that makes it true. Not awaited by
    // anything and allowed to fail silently, exactly like `loadBaseScores`
    // everywhere else: a slow or broken score read costs the ring and nothing
    // else — the tailor itself has already happened and the note already says
    // so.
    store.loadBaseScores(token);
  }

  /** Send this application with the base resume as it stands.
   *
   * The Resume stage's first fork limb, and the only action here that asks the
   * backend for nothing: `baseArmed` is what `stageFor` reads to skip Score and
   * Resume and put the user on Fill, and the rail then RENDERS those rows as
   * skipped — "not required on the path you took", dashed and never a tick
   * (decisions.js's rule, and the reason `SKIPPED_SUMMARY` says "using base
   * as-is" in the user's own words).
   *
   * IT IS STILL AN ACTION rather than a body callback like `pickBase`, and the
   * line between them is what it COMMITS to: this one arms a fill, writes the
   * memory the next page load spends, and is the limb the footer's twin rule
   * greys out while anything else runs. No round trip means no `duringAction`
   * and no token — there is no await to be raced across.
   *
   * Written down for `pickBase`'s reason and more so: the arming has to reach
   * the page that holds the form, which is a later page load of the same
   * wizard. Without the write the user would arm on the posting and arrive at
   * the apply page with nothing armed — which is the shortcut not existing.
   */
  function useBaseAsIs(store) {
    const facts = store.read();
    if (!facts.baseSlug) {
      // Nothing to be as-is. `loadBaseResumes` names the library's first row
      // as the default, so this is an EMPTY library rather than an unmade
      // choice — and arming a fill from no resume would be a shortcut to a
      // fill with nothing in it.
      store.write({ note: { text: "No base resume yet — build one in Maestro CS." } });
      store.render();
      return;
    }
    store.write({
      baseArmed: true,
      // NO SENTENCE, ON EITHER KIND OF PAGE, and the deleted half is the
      // 2026-08-19 change. There used to be one for the form-less page: the
      // shortcut needed a FORM to reach Fill, so arming on a posting moved
      // nothing and a click that changed nothing on screen reads as a click
      // that was ignored. The stage no longer asks about the form, so the rail
      // moves here too — Resume goes to "Skipped — using base as-is" and Fill
      // becomes the step — and the Fill body itself says the part the note
      // used to carry, where the user is now looking. Two copies of one
      // sentence, one of them in a slot the next note overwrites, is worse
      // than the one that stays put.
      //
      // `null` rather than nothing, because the slot may hold the LAST page's
      // answer ("Saved with 3 skills extracted") and the rail moving is this
      // press's own answer.
      note: null,
    });
    store.render();
    store.remember();
  }

  /** Withdraw the base-as-is claim. `unpickApplication`'s twin, one stage down,
   * and deliberately the same grammar: what the user claimed, the user can take
   * back.
   *
   * SYNCHRONOUS — no round trip, no `duringAction` span, for `useBaseAsIs`'s
   * reason: there was never a wire call to undo. The write set is exactly
   * `useBaseAsIs`'s inverse — `baseArmed`, and the sentence it may have written
   * beside it — and `revisit`, which is not the claim but is the VIEW of it:
   * the door the user pressed this button in was opened over the skipped Resume
   * row, and that row is about to stop being skipped.
   *
   * WHAT IT DELIBERATELY DOES NOT CLEAR, the un-pick's list re-read for this
   * claim: `baseSlug` and `baseSelected` (which base they picked is a different
   * answer, and forgetting it would make them choose again to ask for the same
   * thing), `touched` and every other page fact, and anything about an
   * application. Arming a base never wrote any of them.
   *
   * `remember()` IS THE HALF THAT LASTS, and it is the trap this action exists
   * for. The arming was made to cross a page load — that is the whole of
   * `useBaseAsIs`'s closing line — so a withdrawal that only cleared the store
   * would be undone by the next wizard page, which restores `baseArmed` from
   * the bridge and re-arms the claim the user just withdrew. The rewrite is not
   * bookkeeping; it is the withdrawal.
   */
  function stopUsingBaseAsIs(store) {
    const facts = store.read();
    if (facts.busy !== null) return;
    if (facts.baseArmed !== true) return;
    store.write({ baseArmed: false, note: null, revisit: null });
    store.remember();
    store.render();
  }

  ns.panelActionsResume = { quickTailor, useBaseAsIs, stopUsingBaseAsIs };
})();
