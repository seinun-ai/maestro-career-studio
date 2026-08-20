/* Maestro CS Companion — the Resume stage's body.
 *
 * One of five files behind `ns.panelStages`; `panel/stages.js` is the joiner
 * and carries the whole contract. Read it before adding anything here.
 *
 * THE RULE, restated because a file that only POINTS at it is a file that
 * half-remembers it: NOTHING HERE REACHES FOR ANYTHING. No `card`, no `chrome`,
 * no `document`, no network — everything a body may read is on the CONTEXT it
 * is passed (`stageContext()` in panel.js is that contract's definition), and
 * firing one of its callbacks is the only way it changes anything. That is what
 * makes the link below a real `<a href>` built from a fact handed IN
 * (`facts.appUrl`) rather than from the panel's settings object.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  /** The id the Tailor limb's `aria-controls` names, and the id a focus
   * restore will reach for. A constant because two places have to agree on it
   * and they are 40 lines apart; the panel's other stable id (`preview-<key>`)
   * is built the same way for the same reason. */
  const TAILOR_OPTIONS_ID = "tailor-options";

  /** One fork limb. A button, `sel` when it is the branch the user is standing
   * in — which on this fork means "the choice you have opened", never "the
   * choice we made for you": nothing here is pre-selected, because picking a
   * tailoring path on the user's behalf is the Base/Tailored toggle this fork
   * replaced (the mockup's caption records why it had to go). */
  function forkButton({ build }, label, onClick, selected = false) {
    const button = build.node("button", selected ? "sel" : null, label);
    button.type = "button";
    button.addEventListener("click", onClick);
    return button;
  }

  /** A limb that DOES something, out of reach while anything else is running.
   *
   * The footer's primary greys and spins for the length of an action, and this
   * fork stands directly above it with one of the same labels on it: a twin
   * that stayed pressable would swallow the click — guarded, so nothing bad
   * happens, and silent, which is the Jobscan failure this surface keeps
   * naming (a user cannot tell a broken control from a busy one). The
   * disclosure and the link are NOT disabled: neither claims anything, and
   * reading the options while a tailor runs is free.
   */
  function actingLimb(ctx, label, onClick, selected = false) {
    const button = forkButton(ctx, label, onClick, selected);
    button.disabled = ctx.facts.busy === true;
    return button;
  }

  /** Where a custom pass happens, or nothing at all.
   *
   * The job's own page in the web app, on the tab that starts a custom
   * tailoring session ("Score & Tailor"). NOT the session route: that one
   * needs a session id, and the only way to have one is to create it — which
   * is the API call this limb exists not to make.
   *
   * `null` rather than a dead anchor when we cannot build a real address: no
   * `appUrl` means the SW never told us where the web app is, and a link to a
   * guess is the failure this project keeps naming. The header's `deepLink`
   * refuses on exactly the same terms.
   */
  function customLink({ facts, build }) {
    if (!facts.appUrl || !facts.job?.id) return null;
    const anchor = build.node("a", null, "Custom in Studio ↗");
    anchor.href = `${facts.appUrl}/jobs/${facts.job.id}?tab=fit`;
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    return anchor;
  }

  /** The way out of the base-as-is claim, and the twin of the claimed Job
   * body's "Stop using this draft" — same control, same class, same grammar: a
   * claim the user made is theirs to withdraw.
   *
   * Withdrawing is not un-picking a resume. `baseSlug` survives (the withdraw's
   * own docstring lists what it leaves alone), so the rail comes back to the
   * library ladder with the user's base still chosen — the sentence above this
   * button becomes the fork again, not a blank slate.
   */
  function withdrawLimb(ctx) {
    const { facts, act, build } = ctx;
    const stop = build.node("button", "unpick", "Stop using base as-is");
    stop.type = "button";
    stop.disabled = facts.busy === true;
    stop.addEventListener("click", act.stopUsingBaseAsIs);
    return stop;
  }

  /** The Resume stage: three ways forward, on two levels.
   *
   *   [ Use base as-is ]  [ Tailor ]
   *   [ Quick tailor   ]  [ Custom in Studio ↗ ]     ← only once Tailor is open
   *
   * AND ONE MORE SHAPE, once the base is ARMED — which is this body reopened
   * from a rail row that reads "Skipped — using base as-is", on a page with a
   * form and on a posting page alike:
   *
   *   Using ai_ml_engineer as-is
   *   [ Tailor ]
   *   [ Quick tailor ] [ Custom in Studio ↗ ]        ← only once Tailor is open
   *   [ Stop using base as-is ]
   *
   * TWO EDITS AND NOT A SECOND BODY. The claim is NAMED (the user's own words
   * back to them, with the resume they armed), the withdraw is offered at the
   * bottom, and the "Use base as-is" limb is dropped — pressing it would
   * re-assert a claim that is already in force, which is a control that cannot
   * do anything and therefore cannot be honest. Everything else composes
   * unchanged, which is the point: the tailoring fork is exactly what the user
   * came back here for, and a reopened row offering a lesser version of the
   * stage would be a second Resume stage to keep in step with this one.
   *
   * KEYED ON THE CLAIM, NOT ON "the row is skipped", and that stays right for
   * a duller reason than it once had. The two used to come apart on the
   * posting page — `stageFor` skipped nothing there, because the shortcut was
   * gated on a form — and they no longer do: the claim skips the same rows
   * wherever it is made. What is still true is the rule, which is what this
   * body is keyed on: a body renders what is TRUE, and which rail row it is
   * under is the rail's question. `armed` below is what "the claim" means
   * precisely, and the second half of it is the part that is easy to miss.
   *
   * TWO LEVELS rather than three buttons in a row, which is the mockup's shape
   * and its reasoning: the first question is whether to tailor at all, and
   * "quick or custom" is only a question for the user who said yes. Flattening
   * it would put three equal-weight choices in front of someone who has not
   * been asked the one that matters.
   *
   * WHAT EACH LIMB IS, because they are three different KINDS of control and
   * the difference is the honest part:
   *
   * - "Use base as-is" ACTS, and finishes the stage: the shortcut arms, the
   *   rail skips Score and Resume visibly, and the user lands on Fill.
   * - "Tailor" DISCLOSES. It asks nothing of the backend, which is why it can
   *   be pressed by someone still making up their mind.
   * - "Quick tailor" ACTS, and it is the same function the footer's primary
   *   runs (see `STAGE_RUN` for why one behaviour is offered twice).
   * - "Custom in Studio ↗" LEAVES: a real `<a target="_blank">` to the web app
   *   and never an API call. The custom pass is a gap-filling conversation
   *   that belongs in a full page, and the panel has no business creating a
   *   tailoring session behind the user's back to open one — it picks the
   *   result up on the next load instead, which is what the sub line promises.
   */
  function resumeBody(ctx) {
    const { facts, act, build } = ctx;
    const { node, attach } = build;
    const tailor = forkButton(ctx, "Tailor", act.openTailor, facts.tailorOpen);
    // The only limb that discloses anything, so the only one that says so —
    // and it names WHAT it discloses as well as whether it is open. Expanded
    // without `aria-controls` announces a state and leaves the region
    // unidentified: the two controls that appeared are somewhere after this
    // button, and "somewhere after" is what a rebuilt rail makes expensive to
    // find (see the render-cost block in panel.js — the same activation drops
    // keyboard focus to the document, which Round B owns).
    //
    // `id` on the region rather than a wrapper class, because it is an address
    // and not a style. It is also the handle the eventual focus restore will
    // use, which is the other reason it is stable.
    //
    // ONLY WHILE IT EXISTS. This loop renders what is true and nothing else, so
    // the closed fork has no region in the document — and `aria-controls`
    // naming an id nothing carries is worse than saying nothing: it offers a
    // jump that goes nowhere, which is the same broken promise as a link to a
    // guessed address. `aria-expanded: false` is the whole of the closed
    // state's story, and it is enough of one.
    tailor.setAttribute("aria-expanded", facts.tailorOpen ? "true" : "false");
    if (facts.tailorOpen) tailor.setAttribute("aria-controls", TAILOR_OPTIONS_ID);
    // THE CLAIM, AND WHETHER IT IS STILL IN FORCE — two conditions, because
    // `baseArmed` alone is only the first. An application overrides it by
    // DATA: `stageFor`'s `fillFromBase` requires `!hasApplication`, so the
    // moment a tailor commits one the shortcut stops firing, the flag goes
    // inert, and Fill attaches the tailored PDF rather than the base. Reading
    // the flag alone put "Using ⟨base⟩ as-is" over the reopened row for a user
    // who had just pressed Quick tailor from it — a false sentence about which
    // document is going into the form — beside a withdraw that flips a flag
    // nothing reads. That is the same sin this body names when it drops the
    // "Use base as-is" limb: a control that cannot do anything cannot be
    // honest. Data wins over a claim here exactly as it wins over a reopened
    // view in `openRow`.
    const armed = facts.baseArmed === true && !facts.application;
    const body = attach(node("div", "stg-body"),
                        // The claim in the user's own words, and the resume it
                        // names — `useBaseAsIs` refuses without one, so the
                        // fallback is for a bridge entry that lost it rather
                        // than for a choice nobody made.
                        armed ? node("div", "sub",
                                     `Using ${facts.baseSlug || "your base resume"} as-is`)
                          : null,
                        attach(node("div", "fork"),
                               armed ? null
                                 : actingLimb(ctx, "Use base as-is", act.useBaseAsIs),
                               tailor));
    // The withdraw goes LAST on every path, under the second level when it is
    // open: it is the way out of the stage, not one of the ways through it.
    if (!facts.tailorOpen) return armed ? attach(body, withdrawLimb(ctx)) : body;
    const custom = customLink(ctx);
    // ONE region, so `aria-controls` has one thing to point at: the second
    // level is the two limbs AND the sentence that explains one of them, and a
    // reader sent to the limbs alone would be sent past the explanation.
    const options = node("div");
    options.id = TAILOR_OPTIONS_ID;
    attach(options,
           attach(node("div", "fork"),
                  actingLimb(ctx, "Quick tailor", act.quickTailor),
                  custom),
           // The sentence belongs to the link: it promises what happens after
           // the user leaves, so with no link to leave through there is
           // nothing to promise.
           custom ? node("div", "sub", "Custom opens the gap-filling "
             + "tailor page; this panel picks the result up when it’s "
             + "rendered.") : null);
    attach(body, options);
    return armed ? attach(body, withdrawLimb(ctx)) : body;
  }

  ns.panelStageResume = resumeBody;
})();
