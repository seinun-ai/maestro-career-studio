/* Maestro CS Companion — the Track stage's actions: the status PATCH, and
 * the from-base POST that answers `stageFor`'s track-this nudge.
 *
 * One of the concern files behind `ns.panelActions`; `panel/actions.js` is the
 * joiner and carries the whole contract. Read it before adding anything here.
 *
 * THE RULES, restated because a file that only POINTS at them is a file that
 * half-remembers them:
 *
 * - AN ACTION WRITES, holds `busy` for as long as that takes, obeys the
 *   generation rule in full, and never assigns a stage — `stageFor` recomputes
 *   the rail from the store on every render. That is load-bearing HERE more
 *   than anywhere: this action is the one that finishes the journey, and it
 *   finishes it by making `status` true rather than by ticking a row off.
 * - THE `busy` SPAN IS `duringAction`'s, read off the namespace and never
 *   re-implemented — see `panel/actions/during.js`.
 * - NOTHING HERE REACHES FOR ANYTHING: no `card`, no `chrome`, no `document`,
 *   no `fetch`, no timers.
 *
 * TWO CALLERS, TWO WRITERS, TWO FIELDS. `setStatus` stays the footer's — a
 * second Draft/Applied pair in the Track body would be two writers for one
 * field. `trackThis` is the body's, because Track has no footer primary and
 * the nudge lives where the user is reading. They share this file because
 * they are one stage's writes, and they never write the same key.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const duringAction = ns.panelDuringAction;

  /** Mark this application draft or applied.
   *
   * THE ONE PATCH IN THIS EXTENSION: one endpoint, a one-key body. Design §6's
   * rule is the reason the control is a control at all: NEVER AUTOMATIC, in
   * either direction. `applied_at` is
   * stamped by the backend on entry to applied and consumed by the analytics
   * series as a fact about the past, so a false positive silently corrupts a
   * record while a false negative costs one click. (The watcher that once
   * pre-answered this question is retired; the question, and the click, stay
   * the user's.)
   *
   * THREE THINGS WORTH KNOWING BEFORE EDITING IT:
   *
   * - "No application to update." is the note slot's rather than a throw,
   *   because this panel has no exception path a click goes through.
   *   Unreachable through the UI — the footer renders no
   *   segment without an application — and written for the reason every other
   *   guard in this directory is: a control's absence is a rendering decision,
   *   and this is the function that touches the backend.
   * - a press on the status the application ALREADY has returns without a round
   *   trip. The segment is a radiogroup, so the checked option stays pressable,
   *   and a PATCH that sets `applied` to `applied` is a write with nothing to
   *   write — harmless server-side (`applied_at` is stamped once, when it is
   *   unset) and still a spinner and a sentence about an event that did not
   *   happen.
   * - the EVIDENCE is re-read off the answer. `PATCH /api/applications/{id}`
   *   returns the whole `ApplicationRead`, `applied_at` included, and the day
   *   it went out is exactly what the Track body's evidence line is about — so
   *   the line is true the moment the button is pressed rather than after the
   *   next page load. One shape, one reader: `store.build.evidenceFrom` is the
   *   same function `loadContext` folds the GET through.
   *
   * `busy` IS KEYED ON `"track"`, the stage this control belongs to, which is
   * the file-wide rule (one stage, one primary, one busy key) and what makes
   * the footer's own primary grey out while a status write is open.
   */
  async function setStatus(store, status) {
    const facts = store.read();
    if (facts.busy !== null) return;
    if (!facts.application) {
      store.write({ note: { text: "No application to update." } });
      store.render();
      return;
    }
    if ((facts.application.status ?? "draft") === status) return;
    const done = await duringAction(store, "track", () =>
      store.api(`/api/applications/${facts.application.id}`, {
        method: "PATCH", body: JSON.stringify({ status }),
      }));
    if (!done) return;
    const { out } = done;
    // RE-READ past the guard, this directory's rule: the PATCH is a round trip
    // and the loaders have been writing to this store for the length of it.
    const after = store.read();
    // The only thing that clears the application is a page change, and a page
    // change moves the generation `duringAction` has just checked — so this is
    // a refusal for a state that should not arrive rather than a fallback that
    // invents one. Silent, because there is no page and nothing to say about
    // it.
    if (!after.application) return;
    store.write({
      // The backend's own answer for the status, not the argument: a route
      // that normalised or refused the value must not be reported back as the
      // value we sent. `?? status` only covers a response that omits the key.
      application: { ...after.application, status: out.status ?? status },
      evidence: store.build.evidenceFrom(out),
      // On success the applied SENTENCE is the Track body's (TRACK_NOTES in
      // stages/track.js carries the words) — the same string in
      // the body and the footer note at once read as a rendering bug on a
      // 400px rail, so the note stays silent for `applied` and speaks only
      // for the direction the body words differently. Failures still land in
      // the note via duringAction's catch, which is what the slot is for.
      note: status === "applied"
        ? null
        : { text: `Status updated to ${status}.` },
    });
    store.render();
    // The bridge entry carries `status`, so a pick remembered on the posting
    // and spent on the apply page must not still say "draft" after this.
    store.remember();
  }

  /** Turn this page's fill/attach into a tracked draft.
   *
   * The retired floating card had a `trackThis` on this same WIRE — the same
   * `POST /api/applications/from-base`, the same two-key body (`job_id` +
   * `base_resume`; `ops` default to [] server-side); this is that wire's one
   * surviving caller. The write-set after is
   * `pickApplication`'s: a track-this IS the user's claim
   * about this page, so `claimed` and `match: "exact"` land the same way a
   * pick does, and the Job row's un-pick door works on the binding.
   *
   * REMEMBERED AFTER THE RESPONSE, and that order is load-bearing for the
   * opposite reason `pickApplication`'s pre-await remember is. A pick already
   * has an application id from the list; this POST is what mints one. A
   * remember placed before the await would write an application-less entry,
   * and a failed POST would leave the next wizard page thinking nothing
   * happened — which is true — while a successful one that skipped the
   * post-await remember would lose the draft the user just claimed. The
   * generation check still sits on both of `duringAction`'s limbs: a tab
   * switch while the POST is open returns null and paints nothing.
   *
   * THE ROUTE NEEDS A JOB THAT ALREADY EXISTS. Track does not load a posting
   * (`loadPosting` is gated on stage === "job"), so there is no preview here
   * to `addJob` from. No `job.id` or no `baseSlug` is a refusal, not a nested
   * busy span — nesting `addJob` inside this one was the reason Task 15 left
   * the nudge unwired.
   */
  async function trackThis(store) {
    const facts = store.read();
    if (facts.busy !== null) return;
    if (facts.application) return;
    if (!facts.job?.id || !facts.baseSlug) {
      store.write({
        note: { text: "Nothing to track yet — this page's job is not in the library." },
      });
      store.render();
      return;
    }
    const done = await duringAction(store, "track", () =>
      store.api("/api/applications/from-base", {
        method: "POST",
        body: JSON.stringify({
          job_id: facts.job.id,
          base_resume: facts.baseSlug,
        }),
      }));
    if (!done) return;
    const { token, out } = done;
    const after = store.read();
    store.write({
      application: { id: out.id, status: out.status ?? "draft" },
      job: {
        id: after.job?.id ?? facts.job.id,
        company: after.job?.company ?? facts.job.company,
        title: after.job?.title ?? facts.job.title,
      },
      match: "exact",
      claimed: true,
      pdfReady: Boolean(out.pdf_path),
      evidence: store.build.evidenceFrom(out),
      note: { text: "Tracked. Mark it applied when you have submitted it." },
    });
    store.remember();
    store.render();
    await store.loadBaseScores(token);
  }

  ns.panelActionsTrack = { setStatus, trackThis };
})();
