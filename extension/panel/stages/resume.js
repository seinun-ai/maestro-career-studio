/* Maestro CS Companion — the Resume stage's body.
 *
 * One of four files behind `ns.panelStages`; `panel/stages.js` is the joiner
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

  /** The step's words, in one place (owner-approved, 2026-09-27). One short
   * muted line per level: the choices first, and what the two tailoring paths
   * do once Tailor is open. */
  const WORDS = {
    base: "Use my base resume",
    tailor: "Tailor to this job",
    fork: "Base: your resume unchanged. Tailor: fit it to this job first.",
    // The second sentence is about the link, so it goes with it.
    quick: "Quick tailor makes the PDF here.",
    // The panel reads the backend on load and on Refresh, never on a timer.
    custom: "A PDF you make in Maestro CS shows up here when you select Refresh.",
    noPdf: "Your tailored resume has no PDF yet.",
    again: "Tailor again in Maestro CS ↗",
  };

  /** Why the base is off beside an application: one sentence, by who bound
   * it. `stageFor`'s `fillFromBase` needs `!hasApplication`, so armed beside
   * one the claim changed nothing on screen (Task 25's dead button). */
  const BASE_OFF = {
    matched: "This job already has a draft application, so it uses that resume.",
    claimed: "You picked a draft for this page, so it uses that resume.",
  };

  /** The id the disabled base limb's `aria-describedby` names. */
  const BASE_OFF_ID = "base-off-note";

  /** One fork limb. A button, `sel` when it is the branch the user is standing
   * in — which on this fork means "the choice you have opened", never "the
   * choice we made for you": nothing here is pre-selected. `id` is stable
   * across the rebuild a press causes (panel.js `withPlaceKept`). */
  function forkButton({ build }, id, label, onClick, selected = false) {
    const button = build.node("button", selected ? "sel" : null, label);
    button.type = "button";
    button.id = id;
    button.addEventListener("click", onClick);
    return button;
  }

  /** A limb that DOES something, locked while any action runs — with
   * `aria-disabled`, not `disabled`: the limb the user just pressed is rebuilt
   * by the render its own busy causes, and a `disabled` button cannot take
   * focus back, so focus would fall to the document (the conventions'
   * GapLocked rule). Every action refuses to start while `busy`, so the click
   * a locked limb still receives does nothing. The disclosure and the link are
   * never locked: neither claims anything. */
  function actingLimb(ctx, id, label, onClick) {
    const button = forkButton(ctx, id, label, onClick);
    if (ctx.facts.busy === true) button.setAttribute("aria-disabled", "true");
    return button;
  }

  /** The job's Fit tab in the web app, or nothing: no `appUrl` means the SW
   * never said where the web app is, and a link to a guess is the failure
   * this project keeps naming (`deepLink` refuses on the same terms). NOT the
   * gap-analysis route, which needs a session the panel would have to create. */
  function fitLink({ facts, build }, label) {
    if (!facts.appUrl || !facts.job?.id) return null;
    const anchor = build.node("a", null, label);
    anchor.href = `${facts.appUrl}/jobs/${facts.job.id}?tab=fit`;
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    return anchor;
  }

  /** The chosen base resume's name, as the web app shows it, or null: the
   * slug is an API key, never a word for the user. */
  function baseName({ facts }) {
    return facts.resumes?.find((resume) => resume.slug === facts.baseSlug)
      ?.display_name || null;
  }

  /** The way out of the base-as-is claim, the twin of the claimed Job body's
   * "Stop using this draft": a claim the user made is theirs to withdraw.
   * `baseSlug` survives it, so the rail comes back with the base still chosen. */
  function withdrawLimb(ctx) {
    const { facts, act, build } = ctx;
    const stop = build.node("button", "unpick", "Stop using the base resume");
    stop.type = "button";
    stop.disabled = facts.busy === true;
    stop.addEventListener("click", act.stopUsingBaseAsIs);
    return stop;
  }

  /** Quick tailor and the link to Maestro CS, with their one line — shown once
   * Tailor is open. ONE region, so `aria-controls` has one thing to point at. */
  function tailorOptions(ctx) {
    const { node, attach } = ctx.build;
    const custom = fitLink(ctx, "Tailor in Maestro CS ↗");
    const options = node("div");
    options.id = TAILOR_OPTIONS_ID;
    return attach(options,
                  attach(node("div", "fork"),
                         actingLimb(ctx, "resume-quick", "Quick tailor", ctx.act.quickTailor),
                         custom),
                  node("div", "sub",
                       custom ? `${WORDS.quick} ${WORDS.custom}` : WORDS.quick));
  }

  /** "Tailor to this job": a disclosure. It asks the backend for nothing,
   * which is why it can be pressed by someone still making up their mind, and
   * it names the region it opens only while that region exists. */
  function tailorLimb(ctx) {
    const { facts, act } = ctx;
    const tailor = forkButton(ctx, "resume-tailor", WORDS.tailor, act.openTailor,
                              facts.tailorOpen);
    tailor.setAttribute("aria-expanded", facts.tailorOpen ? "true" : "false");
    if (facts.tailorOpen) tailor.setAttribute("aria-controls", TAILOR_OPTIONS_ID);
    return tailor;
  }

  /** The Resume step, in four shapes, each keyed on what is TRUE:
   *
   * - An application WITH its PDF: the step is done ("Tailored resume ready"
   *   on the row). Reopened, one small link to tailor again in Maestro CS,
   *   where replacing a tailored draft asks first. No fork: Quick tailor here
   *   would replace it unasked.
   * - An application WITHOUT a PDF: its tailored resume exists and only the
   *   PDF is missing, so the step's primary (the footer) is Create PDF, never
   *   Quick tailor — that runs a fresh tailor. The base is shown off, with
   *   its one-sentence reason.
   * - The base-as-is claim, reopened from its skipped row: the claim in the
   *   user's own words, the tailoring choice, and the withdraw. The base limb
   *   is dropped: pressing it would re-assert a claim already in force.
   * - Otherwise, two choices — Use my base resume (acts, and finishes the
   *   step by skipping it visibly) and Tailor to this job (discloses Quick
   *   tailor and the link) — with one line saying what each does.
   *
   * An application overrides the claim by DATA (`fillFromBase` needs
   * `!hasApplication`), so `armed` is the flag AND no application: reading the
   * flag alone put "Using ⟨base⟩ as is" over a reopened row the user had just
   * tailored from.
   */
  function resumeBody(ctx) {
    const { facts, act, build } = ctx;
    const { node, attach } = build;
    const body = node("div", "stg-body");
    if (facts.application && facts.pdfReady) {
      const again = fitLink(ctx, WORDS.again);
      if (again) {
        again.id = "resume-again";
        again.className = "linkish";
      }
      return attach(body, again);
    }
    if (facts.application) {
      const base = forkButton(ctx, "resume-base", WORDS.base, act.useBaseAsIs);
      base.disabled = true;
      base.setAttribute("aria-describedby", BASE_OFF_ID);
      const why = node("div", "sub", facts.claimed ? BASE_OFF.claimed : BASE_OFF.matched);
      why.id = BASE_OFF_ID;
      return attach(body, node("div", "sub", WORDS.noPdf),
                    attach(node("div", "fork"), base), why);
    }
    const armed = facts.baseArmed === true;
    if (armed) {
      // `useBaseAsIs` refuses without a base, so the fallback is for a bridge
      // entry that lost it rather than for a choice nobody made.
      attach(body, node("div", "sub", `Using ${baseName(ctx) || "your base resume"} as is`),
             attach(node("div", "fork"), tailorLimb(ctx)));
    } else {
      attach(body,
             attach(node("div", "fork"),
                    actingLimb(ctx, "resume-base", WORDS.base, act.useBaseAsIs),
                    tailorLimb(ctx)),
             node("div", "sub", WORDS.fork));
    }
    if (facts.tailorOpen) attach(body, tailorOptions(ctx));
    // The withdraw goes LAST: it is the way out of the step, not a way through.
    return armed ? attach(body, withdrawLimb(ctx)) : body;
  }

  ns.panelStageResume = resumeBody;
})();
