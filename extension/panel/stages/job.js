/* Maestro CS Companion — the Job stage's body.
 *
 * One of five files behind `ns.panelStages`; `panel/stages.js` is the joiner
 * and carries the whole contract. Read it before adding anything here.
 *
 * THE RULE, restated because a file that only POINTS at it is a file that
 * half-remembers it: NOTHING HERE REACHES FOR ANYTHING. No `card`, no `chrome`,
 * no `document`, no network. A body builds nodes with the builders it is handed
 * and fires the callbacks it is handed, and everything it may read is on the
 * CONTEXT it is passed (`stageContext()` in panel.js is that contract's
 * definition). Enforced by scope rather than by agreement, which is the only
 * kind of enforcement a file like this can have.
 *
 * Everything dynamic goes through `textContent` (the handed-in `node` is the
 * only way anything here builds an element). A job title and a company name are
 * attacker-influenced text on an ATS that lets employers write their own
 * postings.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  /** Thousands separators without a locale. `toLocaleString` would read the
   * user's, and this is one number inside an English sentence. */
  const grouped = (n) => String(n).replace(/\B(?=(\d{3})+$)/g, ",");

  /** The one line under the preview: where the job description came from, and
   * how much of it there is. The count is the honest signal that the grab
   * WORKED — three filled boxes over an empty description would otherwise look
   * exactly like a successful read.
   *
   * THREE SENTENCES, because there are three states and two of them used to
   * share a line. "No job description found on this page" is a claim ABOUT THE
   * PAGE, and the panel is only entitled to it when the page answered; when the
   * ask came back with nothing at all, what it knows is about ITS OWN REACH —
   * an extension reload orphans the content scripts in every open tab, and the
   * page then says nothing however long it has been rendered. Telling that user
   * their JD does not exist is the confident lie this surface's whole design
   * refuses; telling them to reload the tab is both true and actionable.
   *
   * `"unreachable"` is written by `previewFrom` (panel.js) and by nothing else
   * — the literal is copied here because a stage body reaches for nothing, and
   * that function's docstring is the other half of this contract. `null` is the
   * empty preview's own value, which is "not asked yet": the pre-answer paint
   * keeps the ordinary sentence rather than flashing a reachability warning
   * about a question nobody has asked yet.
   */
  function previewNote(preview) {
    const text = String(preview.text ?? "").trim();
    if (text) return `JD grabbed from this page · ${grouped(text.split(/\s+/).length)} words`;
    return preview.source === "unreachable"
      ? "The companion cannot see this page — reload the tab."
      : "No job description found on this page.";
  }

  /** The Job stage: three fields the user can correct before anything is saved.
   *
   * Rendered FROM `facts.preview`, never from what the inputs happen to hold —
   * see `card.preview` in panel.js for why, and see the render-cost block above
   * `render()` for what replaces these elements without warning.
   */
  function jobBody(ctx) {
    const { facts, act, build } = ctx;
    const { node, attach } = build;
    if (facts.claimed === true && facts.application) {
      return claimedJobBody(ctx);
    }
    const kv = node("div", "kv");
    for (const [key, label] of facts.previewFields) {
      const input = node("input");
      input.id = `preview-${key}`;
      input.type = "text";
      input.value = facts.preview[key];
      // Writes the store — through the one callback that may — and does NOT
      // render, which is deliberate both ways: the store write is what makes
      // the character survive the next repaint, and rendering here would
      // destroy the element the user is typing into on every keystroke.
      // Nothing else on this surface reads the preview while it is being
      // edited, so there is nothing to repaint for.
      input.addEventListener("input", (event) => act.editPreview(key, event.target.value));
      const tag = node("label", null, label);
      tag.setAttribute("for", input.id);
      attach(kv, tag, input);
    }
    const body = attach(node("div", "stg-body"), kv,
                        node("div", "sub", previewNote(facts.preview)));
    const pick = picker(ctx);
    return pick ? attach(body, pick) : body;
  }

  /** A claimed binding, reopened. The preview inputs are the unmatched Job
   * body's; they are meaningless over a draft already saved elsewhere. What
   * this body is for: name what this page is bound to, switch to a different
   * draft, or stop using this one. Un-picking is not un-saving. */
  function claimedJobBody(ctx) {
    const { facts, act, build } = ctx;
    const { node, attach } = build;
    const company = String(facts.job?.company ?? "").trim() || "Unknown company";
    const title = String(facts.job?.title ?? "").trim() || "Untitled";
    const status = String(facts.application?.status ?? "draft");
    const bound = node("div", "sub", `${company} · ${title} · ${status}`);
    const stop = node("button", "unpick", "Stop using this draft");
    stop.type = "button";
    stop.disabled = facts.busy === true;
    stop.addEventListener("click", act.unpickApplication);
    const body = attach(node("div", "stg-body"), bound);
    const pick = picker(ctx);
    if (pick) attach(body, pick);
    return attach(body, stop);
  }

  /** Recent drafts, offered on any page nothing has matched — and, when the
   * binding is a claim, as the switcher in the reopened Job body. Honest
   * absence is the empty return: no candidates is nothing rendered, not a box
   * that says there is nothing.
   *
   * NO FORM GATE — this used to refuse unless `hasForm === true`, and Workday
   * falsified that (elevancehealth.wd1, console-verified 2026-08-18). Its
   * wizard urls are unique, so the backend matches none of them; the JD is in
   * the DOM of pages that carry no form yet; and the form verdict at bind-time
   * is false anyway — late SPA render, a login step in the middle, or the form
   * appearing with no url change to re-bind on. The refusal fired on exactly
   * the flow the picker was written for and never on the fast ATSes that did
   * not need it.
   *
   * OFFER, NEVER GUESS is why dropping it is safe. The pick is the USER'S
   * claim about this page — the panel is not asserting the page is fillable,
   * it is asking which application they are here about — so an offer is safe
   * anywhere a guess would not be. The two refusals that remain are the ones
   * where an offer would be an argument: `application` means something is
   * already armed or the backend already named this page, and an empty list
   * means there is nothing to name.
   *
   * `application` WITHOUT `claimed` is the backend's own match, and this body
   * is never handed one (Job is not reopenable for that case). The switcher
   * is offered when `claimed` is true: that is the user's binding, and they
   * can point at a different draft. The refusals that ARE observably
   * load-bearing here are `webPage` and the empty list.
   *
   * `webPage` is the third, and it is not about forms: the list outlives a tab
   * switch, and a `chrome://` tab is not a page this extension can fill or
   * scope a pick to. See panel.js's snapshot for that rule's other half.
   *
   * A NATIVE SELECT, not a stack of buttons. Four-plus drafts overflowed the
   * Job body as rows; a select scrolls and is keyboard-accessible for free.
   * Placeholder first ("Choose a draft
   * application…"), newest first as the list endpoint returns them, change
   * fires `pickApplication`. No cap: every draft the loader returned is an
   * option. The label is the offer in words, wired to the select. The same
   * control is the switcher in the reopened claimed Job body — one definition.
   */
  const DRAFT_PICK_ID = "draft-pick";

  function optionLabel(app) {
    const company = String(app.job_company ?? "").trim() || "Unknown company";
    const title = String(app.job_title ?? "").trim() || "Untitled";
    const status = String(app.status ?? "draft");
    return `${company} · ${title} · ${status}`;
  }

  function picker(ctx) {
    const apps = ctx.facts.applications;
    if (ctx.facts.webPage !== true || !apps?.length) return null;
    // A backend exact-match is not a claim and gets no switcher. A claimed
    // binding is the user's, so the same control is how they pick a different
    // draft. `application` without `claimed` is that backend case.
    if (ctx.facts.application && ctx.facts.claimed !== true) return null;
    const { node, attach } = ctx.build;
    const currentId = ctx.facts.application?.id ?? "";
    // IS THE BINDING ACTUALLY ON THE LIST? A `<select>` shows its first option
    // when no option is selected, and a DISABLED placeholder is not thereby a
    // selected one — so a bound id that is not among the rows made the browser
    // display SOME OTHER DRAFT'S NAME as if the user had chosen it (observed
    // live 2026-08-19, beside a deleted application the bridge had restored).
    // That is the worst kind of wrong this surface can be: a specific,
    // plausible, unchosen answer.
    //
    // Two states produce it and they are one question, which is why this is a
    // membership test rather than `!currentId`: nothing is bound at all, and
    // something is bound that the list does not contain — a draft older than
    // the list's window, a list read before the pick, or a referent that has
    // been deleted. The honest rendering of both is the placeholder, whose
    // words ("Choose a draft application…") are true in either.
    const bound = apps.some((app) => app.id === currentId);
    const select = node("select");
    select.id = DRAFT_PICK_ID;
    const placeholder = node("option", null, "Choose a draft application…");
    placeholder.value = "";
    placeholder.disabled = true;
    if (!bound) placeholder.selected = true;
    attach(select, placeholder);
    for (const app of apps) {
      const option = node("option", null, optionLabel(app));
      option.value = app.id;
      if (app.id === currentId) option.selected = true;
      attach(select, option);
    }
    select.addEventListener("change", (event) => {
      const id = event.target.value;
      if (id) ctx.act.pickApplication(id);
    });
    const label = node("label", "sub", "Recent drafts — pick one to work on here");
    label.setAttribute("for", DRAFT_PICK_ID);
    return attach(node("div", "appick"), label, select);
  }

  ns.panelStageJob = jobBody;
})();
