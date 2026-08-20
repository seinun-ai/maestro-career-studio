/* Maestro CS Companion — the Fill stage's action, and the run it is made of.
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
 *   re-implemented here — see `panel/actions/during.js`. This file is the one
 *   that most needs it said: the run below is several round trips long, and
 *   `onProgress` WRITES the store from inside it, so the generation rule is
 *   carried at each write rather than inherited from a check around the call.
 * - NOTHING HERE REACHES FOR ANYTHING: no `card`, no `chrome`, no `document`,
 *   no `fetch`, no timers.
 *
 * WHAT THIS FILE PUBLISHES BESIDES ITS ACTION: `ns.panelFillFinished`. The
 * "is this page's fill finished" predicate belongs to the Fill stage and is
 * READ by the pause row (`panel/actions/pause.js`), because the last pause row
 * closing has to mark the page done exactly as a clean run would. One function
 * with two callers, on the namespace, rather than the second copy that would
 * drift on whichever half is easier to forget.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const duringAction = ns.panelDuringAction;
  const { reconcileFill } = ns.decisions;
  // The guided-fill runner, read off the namespace for the shared modules'
  // reason: the Fill stage below calls it with this panel's bound tab's
  // transport, and the runner itself knows nothing about which world it is in.
  // `shared/choose.js` — which the runner reads at call time — is loaded by
  // panel.html beside it, which is what Task 12's split bought.
  const { runGuidedFill } = ns.guidedRun;

  /** Which resume the fill's employment blocks and skills come from.
   *
   * Three rungs in this order: the application when we have one, else the
   * chosen base, else neither — which the endpoint accepts and answers with a
   * profile-only payload. The order is the endpoint's own preference, not a
   * choice made here.
   */
  function resumeQuery(facts) {
    if (facts.application) {
      return `?application_id=${encodeURIComponent(facts.application.id)}`;
    }
    return facts.baseSlug ? `?base=${encodeURIComponent(facts.baseSlug)}` : "";
  }

  /** The deterministic pass: one context payload, one fan-out, one
   * reconciliation.
   *
   * THE RULE PASS LIVES HERE and not in a shared module, which is now a
   * decision rather than a deferral: it writes this store's fields and says
   * this surface's sentences, and there is one caller. What is shared is what
   * does the DECIDING — `reconcileFill` is `shared/decisions.js`'s, so any
   * caller buckets one fill's outcomes the same way.
   *
   * FOUR THINGS BELOW ARE LOAD-BEARING, and each is a rule rather than a
   * detail:
   *
   * - `/api/autofill/context` replaces three always-co-issued round trips and
   *   degrades per section: a skills outage returns `skills: null` rather than
   *   failing the request, which is why a null section becomes `[]` here and
   *   never an error.
   * - the two EEO flags come from the BACKEND's standing consent and from
   *   nothing else. Disclosing protected characteristics and ticking the
   *   application's own agreement boxes are different permissions, so they are
   *   two flags off one record; the legacy `chrome.storage.sync`
   *   `eeoAutofillEnabled` is ignored, and this panel offers no toggle that
   *   could turn either on.
   * - `consentForms` goes LAST in the message, matching the engine's parameter
   *   order, because a positional call converted from a keyed message is where
   *   a silent argument swap would live.
   * - telemetry is sent BEFORE the reached check: a page full of `no_rule` is
   *   exactly the coverage-gap evidence the channel exists to collect, and it
   *   is the page we learn least from that we most need it for.
   *
   * It runs INSIDE the runner's swallow (`rulePass` is injected and its throw
   * is caught there), which is what makes "no profile yet" a thinner run rather
   * than the end of one. The unreached-page sentence is not swallowed in any
   * meaningful sense: the collect that follows immediately hits the same
   * silence and throws the same one sentence, which is the point of there being
   * only one.
   */
  async function rulePass(store, facts, token) {
    const context = await store.api(`/api/autofill/context${resumeQuery(facts)}`);
    if (!context.profile || Object.keys(context.profile).length === 0) {
      throw new Error("No autofill profile yet. Fill it in under Profile in "
        + "Maestro CS.");
    }
    const frames = await store.broadcast({
      type: "profile_fill",
      profile: context.profile,
      employment: context.employment ?? [],
      eeoEnabled: context.eeo_consent?.enabled === true,
      skills: context.skills ?? [],
      consentForms: context.eeo_consent?.consent_forms === true,
    });
    const result = reconcileFill(frames);
    store.telemetry("profile_fill", result.observations);
    if (!result.reached) throw new Error(ns.guidedRun.NO_FRAME_REACHED);
    // PAST THE GUARD, like every other write in this directory: a context read
    // and a fan-out are two round trips, and the user is free to leave across
    // either.
    if (!store.current(token)) return;
    store.write({
      fill: result,
      // Read, never decided. `null` when the endpoint said nothing about
      // consent, which the Voluntary-disclosures row renders as "not asked" —
      // and that is a different sentence from "off".
      eeoConsent: context.eeo_consent && typeof context.eeo_consent === "object"
        ? {
          enabled: context.eeo_consent.enabled === true,
          consent_forms: context.eeo_consent.consent_forms === true,
        }
        : null,
    });
    store.render();
  }

  /** What the run actually wrote: the qids the engine answered for, minus the
   * ones the runner residued.
   *
   * NOT a second reading of the outcome vocabulary, deliberately. The runner
   * has already decided which qids are residue — `not_stuck`, a pair the writer
   * never reported back, an abstain, a /choose failure — so "written" is that
   * decision subtracted rather than a fresh table of outcome strings that would
   * be the second answer to a question `shared/guided-run.js` has answered.
   */
  function writtenQids(writeResults, residue) {
    const open = new Set((residue ?? []).map((row) => row.qid));
    return (writeResults ?? []).filter((row) => !open.has(row.qid));
  }

  /** Is this page's fill FINISHED — the claim `touched` makes and `stageFor`
   * renders as a tick with Track active beneath it?
   *
   * ONE function, read by both the paths that can make that claim true:
   * `startFill` when its run lands, and `submitAnswer` (`actions/pause.js`)
   * when the last pause row closes. It is written out here rather than inlined
   * twice because the two halves are the interesting part and a second copy
   * would drift on exactly the half that is easy to forget:
   *
   * - wrote something, because a run that answered nothing has no claim to
   *   make about this page at all;
   * - left nothing open, because a tick beside a step with two unanswered
   *   fields still under it takes the list of what is open OFF THE SCREEN and
   *   offers to mark the application applied instead.
   *
   * AN ATTACH COUNTS AS WRITING, and it is `decisions.js` that says so rather
   * than this file: `done.fill` is documented there as "this extension's own
   * claim that it filled OR ATTACHED here", and until this round there was no
   * attach on this surface for that clause to describe. Putting the résumé into
   * the page's upload box is the most substantial thing this extension does to
   * a page, so a rule that counted twenty text fields and not that would be
   * measuring effort rather than result.
   *
   * WHAT THE SECOND HALF THEN BUYS, and why the attach does not simply set
   * `touched` on its own: an attach performed after a fill that left three
   * fields open still leaves three fields open. Running it through the same
   * predicate is what keeps that true — the tick waits for the form, and the
   * attach on a page with nothing else outstanding finishes the step.
   *
   * READS THE STORE'S OWN FIELDS, which is what makes the two callers converge
   * rather than agree: `submitAnswer` removes a row and asks again, and it gets
   * the same answer `startFill` would have got had the run ended there. A
   * second predicate that counted "the run's residue" would have said no
   * forever, because the run's residue never changes after the run.
   *
   * ON THE NAMESPACE for that reason and only that one: the pause row is a
   * different file since Task 15's split, and a predicate two files agree about
   * is a predicate that eventually does not.
   */
  function fillFinished({ fill, writeResults, residue, essays, attached }) {
    const written = writtenQids(writeResults, residue);
    const wrote = (fill?.counts?.filled ?? 0) + (fill?.counts?.corrected ?? 0)
      + written.length + (attached?.count ?? 0);
    const open = (residue?.length ?? 0) + (essays?.length ?? 0);
    return wrote > 0 && open === 0;
  }

  /** Start fill: the deterministic pass, then — unless the user said rules only
   * — the model on what is left.
   *
   * THE ONE PLACE THIS PANEL INJECTS. A click is a user gesture, and
   * `panel_prepare` is what makes a tab that was already open when the
   * extension last reloaded fillable at all: content scripts enter a page when
   * the PAGE loads, so such a tab has none and every message to it answers
   * nothing. `loadHasForm` deliberately does NOT prepare — a read on every tab
   * switch is the always-on cost the detection gate exists to avoid — and this
   * is the other half of that decision: injection is reserved for the moment
   * the user asks for something that needs the page.
   *
   * NO "does this page have a form" GUARD, and that is not an oversight.
   * `card.hasForm` is false both for a page with no form AND for a tab our
   * scripts never reached — which is precisely the tab `panel_prepare` exists
   * to rescue — so gating on it would refuse to fill the one case this button
   * is for. A page that genuinely has nothing reports nothing, and an empty
   * report is an honest answer.
   *
   * `touched` IS THE CLAIM, AND IT IS THE FINISHED ONE. `stageFor` reads it as
   * `done.fill` and the rail renders that as a tick with Track active beneath
   * it — so it is written only when this run BOTH wrote something and left
   * nothing open. Two halves, and each is load-bearing:
   *
   * - wrote something, because a run that answered nothing has no claim to
   *   make about this page at all;
   * - left nothing open, because a tick beside a step with two unanswered
   *   fields still under it is the "we did it" / "we did some of it"
   *   conflation `decisions.js` keeps skipped separate from done to avoid —
   *   and it is worse than an abstract honesty point here, because a done row
   *   has no body: ticking Fill off takes the list of what is still open OFF
   *   THE SCREEN, on the page it is about, and offers to mark the application
   *   applied instead.
   *
   * THE COST, stated rather than discovered: a fill that answers nineteen
   * fields and leaves one does not mark this page as touched, so the
   * track-this nudge does not appear until the last field is answered and the
   * fill re-run. That is the right way round — the nudge follows the work
   * being finished — and it is also where Task 13's pause rows land, which
   * answer the remainder without leaving the panel.
   *
   * `touched` MEANS "this step is complete", which is stricter than "a field
   * was written", and the rail is why. A tick takes the open-fields list off
   * screen, so setting it on a partial fill hides the very rows the user still
   * has to answer. (A surface with no rail can afford the looser reading —
   * there `touched` only raises a "mark as applied" suggestion, which costs
   * nothing when it is early.)
   */
  async function startFill(store) {
    const facts = store.read();
    if (facts.busy !== null) return;
    // TAKEN BEFORE `duringAction`, which takes the same value a line later
    // (nothing awaits in between). It is read out here because `onProgress`
    // needs it: that callback WRITES the store from inside the run, so it
    // carries the generation rule itself rather than inheriting a check made
    // around the call.
    const token = store.token();
    // EVERY FIELD THIS RUN WILL REPORT, cleared before it starts — and this is
    // what makes the two readings below mean what they say rather than what
    // the LAST run left behind. `resetPageFacts` clears these on a tab change
    // and nothing else did, so a second press on the same page inherited the
    // first press's report:
    //
    // - `collected` (stages/fill.js) would read run 1's residue as "run 2
    //   collected the questions", painting the fields the user has since
    //   answered by hand underneath run 2's counts;
    // - the discriminator in the catch below would read run 1's `fill` as "the
    //   rules ran on THIS run" and suppress the unreachable sentence for a run
    //   whose rule pass never reached the page at all — the invariant that
    //   catch is written around, falsified by its own predecessor.
    //
    // One write, before the first await, on the render the user clicked: a
    // press starts from nothing known, which is also what the body should show
    // while the run is open.
    store.write({ fill: null, eeoConsent: null, residue: null, essays: null,
                  writeResults: null });
    const aiAssist = facts.fillMode === "assist";
    const done = await duringAction(store, "fill", async () => {
      await store.prepare();
      try {
        return await runGuidedFill({
          broadcast: store.broadcast,
          api: store.api,
          telemetry: store.telemetry,
          // `facts` and not a fresh read, which is the same "read once" the
          // mode control gets and for the same reason: `resumeQuery` picks the
          // application or the base slug, and WHICH resume this fill is from
          // has to be the one the user was looking at when they pressed. A
          // re-read inside the rule pass would let a load landing mid-run
          // change the answer — a fill sourced from an application the panel
          // adopted a moment ago, on a form the user started for their base.
          // Anything that must be current is re-read past the guard instead.
          rulePass: () => rulePass(store, facts, token),
          // THE ASYNC STORE-WRITING FUNCTION the generation rule was written
          // for, and the one that would be easiest to leave out: the run is
          // several round trips long, so a user who switches tabs mid-fill is
          // the ORDINARY case here rather than the unlucky one. Without this
          // check tab A's essay queue and residue paint over tab B a beat after
          // tab B finished loading — and they do not look wrong, they look like
          // tab B's form having questions nobody can find.
          onProgress: (update) => {
            if (!store.current(token)) return;
            if (update.phase === "essays") store.write({ essays: update.essays });
            if (update.phase === "residue") store.write({ residue: update.residue });
            store.render();
          },
        }, { aiAssist, applicationId: facts.application?.id ?? null });
      } catch (err) {
        // A THROW HERE IS NOT ALWAYS A PAGE NOBODY REACHED, and the difference
        // is two fields sitting in the form. The run is a sequence, so a
        // failure at the collect or the write leaves the rule pass's work
        // standing — and the runner's one sentence for an unreached page
        // ("Reload the tab, then try again") is a flat lie about a page this
        // panel has just written into. It is also the sentence the user would
        // act on by reloading, which throws that work away.
        //
        // `fill` is the discriminator and the only honest one available: it is
        // written past the generation guard by `rulePass` itself, so non-null
        // means the rules reached THIS page on THIS run. After a tab switch it
        // reads null (`resetPageFacts`), which sends the original sentence up
        // to `duringAction`'s stale check to be discarded — the right outcome
        // either way.
        if (store.read().fill === null) throw err;
        throw new Error("The rules ran; the page stopped answering before the "
          + "questions could be collected. What they filled is below — reload "
          + "the tab to finish the rest.");
      }
    });
    if (!done) return;
    const { out } = done;
    // RE-READ for the rule pass's own result: it landed in the store from
    // inside the run, which is where the progress rows want it.
    const after = store.read();
    const open = out.residue.length + out.essays.length;
    // The SAME predicate a pause-row submit will ask, over this run's numbers.
    // Written as one function so the two paths converge rather than agree — see
    // `fillFinished`.
    // `after.attached` and not null: an attach made BEFORE this run is still on
    // this page, and a fill that answered nothing over a page already carrying
    // the résumé has not un-attached it.
    const finished = fillFinished({ fill: after.fill, writeResults: out.writeResults,
                                    residue: out.residue, essays: out.essays,
                                    attached: after.attached });
    store.write({
      residue: out.residue,
      essays: out.essays,
      writeResults: out.writeResults,
      // The counts are the rows'; this slot gets the one sentence. "Needs you"
      // counts the essays with the residue because the user's question is what
      // is still open, and an unanswered essay is exactly that — they are kept
      // apart in the store because they are ANSWERED differently, not because
      // they are different news.
      note: { text: open
        ? `${store.build.plural(open, "field")} still ${open === 1 ? "needs" : "need"} you.`
        : "Fill finished. Review before you submit." },
    });
    if (finished) store.write({ touched: true });
    store.render();
    // `touched` is the bit that outlives this page: an ATS wizard is six page
    // loads and `resetPageFacts` clears the store on every one of them, so
    // without the write the rail would ask for this fill again on the next step
    // of a form the extension has already finished.
    if (finished) store.remember();
  }

  /** Put the tailored PDF into this page's upload box.
   *
   * USER-PRESSED, ALWAYS. This is not a step of `startFill` and must not become
   * one: a fill writes text into fields the user can read back at a glance,
   * and an upload is a whole document leaving for an employer. The body offers
   * the control and the user decides; nothing here runs on a load, a detect or
   * the end of a run.
   *
   * IT ASKS THE PAGE FOR NOTHING AND CHOOSES NOTHING. Which boxes exist was
   * settled by the detect pass (`card.fileInputs`), and the BODY refuses to
   * offer the press when there is more than one — see `attachRow`
   * (stages/fill.js). This action deliberately does not re-check that: two
   * places deciding "is this page's upload box unambiguous" is two places that
   * can disagree, and the one that renders the control is the one the user is
   * looking at. What it does check is `busy`, like every other action here.
   *
   * THE PDF IS RE-READ, not assumed: `pdfReady` was true when the panel last
   * loaded the application, and a re-render or a delete in the web app since
   * then would make this attach a 404 with a worse message than the one
   * below. The read also yields the REAL filename — the same
   * `pdf_path` split `evidenceFrom` performs — so the file that lands on the
   * page is named what the user's own library calls it.
   *
   * THE BYTES NEVER TOUCH THIS DOCUMENT. `store.attachPdf` is a message; the
   * service worker fetches, base64s and fans out, so the PDF crosses one
   * boundary rather than two and this panel holds none of it. Every receiving
   * frame still passes `frameMayReceiveUserData` — a résumé is PII and is gated
   * exactly as a fill is.
   *
   * THE COUNT IS THE ENGINE'S READBACK. `attachResumePdf` re-reads
   * `input.files` after the assignment, so a page that refused the write
   * contributes nothing and this reports zero rather than a success. The two
   * zero cases are told apart the way the fill path tells them apart: a frame
   * that ANSWERED and found nothing is a fact about the page, and no frame
   * answering at all is a fact about our reach.
   *
   * `touched` GOES THROUGH `fillFinished` rather than being set here — see that
   * function. An attach is writing; it is not a licence to tick a step that
   * still has open fields under it.
   */
  async function attachResume(store) {
    const facts = store.read();
    if (facts.busy !== null) return;
    // No application, no tailored PDF, nothing to attach. The body does not
    // render the control in that state; this is the guard that makes pressing
    // it impossible rather than merely unlikely.
    if (!facts.application) return;
    const applicationId = facts.application.id;
    // TAKEN BEFORE `duringAction`, `startFill`'s rule and for `startFill`'s
    // reason: there is a store write INSIDE the run, so it carries the
    // generation check itself rather than inheriting the one `duringAction`
    // makes around the call.
    const token = store.token();
    const done = await duringAction(store, "fill", async () => {
      await store.prepare();
      const detail = await store.api(`/api/applications/${applicationId}`);
      if (!detail.pdf_path) {
        // The store is corrected on the way past: `pdfReady` is what put this
        // control on screen, and leaving it true would keep offering an attach
        // for a document that is gone. The render in `duringAction`'s catch is
        // what takes the control away.
        //
        // PAST THE GUARD, and this is the write the rule exists for. Two awaits
        // stand above it, so a user who switches tabs across either of them
        // gets this answer about the application they LEFT stamped onto the one
        // they are now looking at: the new page's `pdfReady` goes false, its
        // Resume stage re-offers a tailor for an application whose PDF is
        // perfectly good, and its attach offer disappears. `duringAction`'s own
        // check discards the ERROR on a stale generation and cannot help here,
        // because by then this write has already landed.
        if (store.current(token)) store.write({ pdfReady: false });
        throw new Error("The tailored PDF is not rendered anymore. Open it in "
          + "Maestro CS and generate it again.");
      }
      const filename = detail.pdf_path.split(/[\\/]/).pop() || "tailored-resume.pdf";
      // THE OFFER'S OWN BELIEF, sent with the write. `facts.fileInputs` is what
      // put this control on screen in the state it is in — one box means the
      // button was live, several means it was dead — and the engine refuses the
      // whole write in any frame whose list no longer says the same thing.
      //
      // WITHOUT IT THE REFUSAL WAS DECORATION. The count is frame 0's and is
      // taken at DETECT time; the write runs at PRESS time across every gated
      // frame. A Workday step that reveals a cover-letter uploader when the
      // résumé section expands moved from one box to two in between, and the
      // résumé went into both — the report said so honestly afterwards, which
      // is not the same as the refusal having held.
      const expect = facts.fileInputs;
      const frames = await store.attachPdf(
        `/api/applications/${applicationId}/pdf`, filename, expect);
      const count = frames.reduce((total, frame) => total + (frame.result ?? 0), 0);
      if (!count) {
        if (!frames.some((frame) => frame.result !== undefined)) {
          throw new Error(ns.guidedRun.NO_FRAME_REACHED);
        }
        // ZERO HAS TWO CAUSES and they are different news, so the panel asks
        // rather than guessing: the boxes refused the file, or the page grew
        // one and the refusal above fired. The fresh count answers it, and
        // WRITING IT BACK is what makes the row itself say why — it flips to
        // the several-boxes refusal, in the same words the offer would have
        // used had the page looked like this when we first asked.
        const now = await store.detectFileInputs();
        if (store.current(token)) store.write({ fileInputs: now });
        throw new Error(now === expect
          ? "No upload box on this page took the file. Attach it by hand."
          : "This page's upload boxes changed while you were pressing, so "
            + "nothing was attached.");
      }
      return { filename, count };
    });
    if (!done) return;
    const attached = done.out;
    const after = store.read();
    // A RUN HAS TO HAVE HAPPENED, and this clause belongs here rather than in
    // `fillFinished` because it is about the ATTACH and not about the
    // predicate. An attach is evidence about the upload box; it is not evidence
    // about the form. On a Workday page with twenty empty fields, an attach
    // alone would otherwise satisfy "wrote something, left nothing open" — the
    // second half only because nothing has ever LOOKED — and tick the Fill step
    // over a form nobody filled, which is exactly the "we did it" / "we did
    // some of it" conflation the tick exists to avoid. Worse than abstract: a
    // done row has no body, so the tick would take this very report off screen.
    //
    // It costs the upload-only page nothing, which is the case worth checking:
    // a fill there reports zero filled and zero open, `fill` is non-null
    // because the rules reached the page, and the attach then finishes the step
    // exactly as it should.
    const ranHere = after.fill !== null || after.residue !== null
      || after.essays !== null;
    const finished = ranHere && fillFinished({
      fill: after.fill, writeResults: after.writeResults,
      residue: after.residue, essays: after.essays, attached,
    });
    store.write({
      attached,
      // NAMED, and hedged on purpose. The extension set `input.files` and the
      // page took it; whether the employer's own uploader has processed it is
      // not a thing this can see, and "Attached" full stop would be a stronger
      // claim than the evidence.
      note: { text: `Attached ${attached.filename}. Check the upload before you submit.` },
    });
    if (finished) store.write({ touched: true });
    store.render();
    // The session entry, for `startFill`'s reason: an ATS wizard is six page
    // loads and `resetPageFacts` clears the store on every one of them.
    if (finished) store.remember();
  }

  ns.panelActionsFill = { startFill, attachResume };
  ns.panelFillFinished = fillFinished;
})();
