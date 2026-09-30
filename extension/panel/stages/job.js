/* Maestro CS Companion — the Job stage's body.
 *
 * One of four files behind `ns.panelStages`; `panel/stages.js` is the joiner
 * and carries the whole contract. Read it before adding anything here.
 *
 * THE STEP ASKS TWO QUESTIONS: is the job saved, and which base resume goes
 * with it. So it has three bodies — the editable preview before a save, the
 * ranked base list after one (what was the Score step until 2026-09-27), and
 * the claimed binding's switcher when the user picked a draft by hand.
 *
 * ONE EXCEPTION to the rule below, the same one every file in this directory
 * may make: `shared/decisions.js` is read off the namespace, because the
 * ranking is a DECISION both surfaces read one copy of rather than a fact
 * about this render.
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
  const { rankBaseResumes, describesJob } = ns.decisions;

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
    // Only text found by a job signal is called a job description
    // (`describesJob`): Task 25's first read found "Job description found (13
    // words)" over a recipe page, because the count was over any page text.
    const text = String(preview.text ?? "").trim();
    if (describesJob(preview)) {
      return `Job description found (${grouped(text.split(/\s+/).length)} words)`;
    }
    return preview.source === "unreachable"
      ? "The Companion can't read this page. Reload the tab."
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
    if (facts.jobSaved === true) return baseBody(ctx);
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
    const title = String(facts.job?.title ?? "").trim() || "Untitled job";
    const status = build.statusLabel(facts.application?.status ?? "draft");
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
   * Placeholder first ("Choose one…"), newest first as the list endpoint returns them, change
   * fires `pickApplication`. No cap: every draft the loader returned is an
   * option. The label is the offer in words, wired to the select. The same
   * control is the switcher in the reopened claimed Job body — one definition.
   */
  const DRAFT_PICK_ID = "draft-pick";

  // No status in the option: the list is drafts only (`?status=draft`, see
  // `loadApplications` in panel.js), so "· draft" on every row said nothing.
  function optionLabel(app) {
    const company = String(app.job_company ?? "").trim() || "Unknown company";
    const title = String(app.job_title ?? "").trim() || "Untitled job";
    return `${company} · ${title}`;
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
    // words ("Choose one…") are true in either.
    const bound = apps.some((app) => app.id === currentId);
    const select = node("select");
    select.id = DRAFT_PICK_ID;
    const placeholder = node("option", null, "Choose one…");
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
    // The question the pick answers, rather than the list's name: "Recent
    // drafts" left the reader to work out what choosing one would do.
    const label = node("label", "sub", "Applying for one of these?");
    label.setAttribute("for", DRAFT_PICK_ID);
    return attach(node("div", "appick"), label, select);
  }

  /** What an ATS score IS, said once in the panel where the numbers first
   * appear, as the app's own estimate (docs/frontend-conventions.md, the
   * glossary's ATS score). The web app's Score and tailor tab says the same
   * sentence (`ATS_SCORE_LEAD`, frontend/lib/ats-words.ts). */
  const ATS_SCORE_LEAD = "An ATS score (0 to 100) is our estimate of how an "
    + "applicant tracking system would rate each resume for this job.";

  /** The one line under the ranked list: how much of it is real. */
  function rankingNote({ facts, build }, ranked) {
    if (!ranked.length) return "No base resumes yet. Add one in Maestro CS.";
    const scored = ranked.filter((row) => row.score !== null).length;
    // While the scorer runs (on the save, or when this step opens on a job
    // nobody has scored), and otherwise the retry, named in words because its
    // button sits in the footer rather than in this body.
    if (!scored) {
      return facts.busy === true
        ? "Scoring your base resumes for this job."
        : "Not scored for this job yet. Select Update scores below.";
    }
    // No engine id beside the count: a scorer's version string is its own
    // name for itself, not a word a job seeker can act on. The count is over
    // `ranked`, so it describes the rows on screen and nothing wider.
    return `${build.plural(scored, "base resume")} scored for this job`;
  }

  /** One selectable base resume: the radio dot, the name, the composite.
   *
   * `role="radio"` on a real button rather than an `<input type=radio>`: the
   * row IS the control (the dot is drawn by CSS from the selected class), and
   * a hidden input with a label wrapped round the same box would be two
   * elements where one does. No roving tabindex, so every row is tabbable —
   * worse than the ARIA pattern on a long list, and it never traps anyone,
   * which is the trade a first version should make.
   *
   * `aria-checked` and not colour alone: the selected row differs from the
   * rest by a border and a tint, and neither reaches a screen reader.
   */
  function baseRow({ facts, act, build }, entry, best) {
    const { node, attach } = build;
    const selected = entry.slug === facts.baseSlug;
    const row = node("button", selected ? "baserow sel" : "baserow");
    row.type = "button";
    // Stable across a rebuild (panel.js `withPlaceKept`), which hands focus to
    // the Job row's door when a pick closes the list.
    row.id = `base-${entry.slug}`;
    row.setAttribute("role", "radio");
    row.setAttribute("aria-checked", selected ? "true" : "false");
    const dot = node("span", "r");
    dot.setAttribute("aria-hidden", "true");
    attach(row, dot, ...rowText(build, entry, best));
    row.addEventListener("click", () => act.pickBase(entry.slug));
    return row;
  }

  /** A row's name and its composite. "not scored" is a WORD, never a zero: a
   * base resume nobody has scored against this job has no number, and
   * printing one would be the panel inventing the judgement it exists to
   * render. Rounded, never computed — the composite is the backend's. */
  function rowText({ node }, entry, best) {
    const score = entry.score === null
      ? node("span", "score", "not scored")
      : node("span", best ? "score good" : "score", String(Math.round(entry.score)));
    return [node("b", null, entry.display_name || entry.slug), score];
  }

  /** The same row as information only: a bound application already answered
   * the base question, so there is nothing to pick and nothing to press. */
  function infoRow({ build }, entry, best, usedSlug) {
    const row = build.node("div", entry.slug === usedSlug ? "baserow ro sel" : "baserow ro");
    return build.attach(row, ...rowText(build, entry, best));
  }

  /** Which base a bound application's resume came from, in one line: its own
   * `base_resume` (the pick's and the restore's `baseSlug` otherwise), by the
   * name the web app shows, and its score for this job when one is stored.
   * "Resume from", never "Tailored from": the panel cannot tell a tailored
   * resume from the base unchanged (a track-this application). */
  function tailoredFrom({ facts }, ranked, usedSlug) {
    const used = ranked.find((entry) => entry.slug === usedSlug);
    const name = used?.display_name || facts.application?.base_resume_name
      || "your base resume";
    return used && used.score !== null
      ? `Resume from ${name} · ${Math.round(used.score)}`
      : `Resume from ${name}`;
  }

  /** The saved job's base question: every base resume this job has an
   * opinion about, best first, and one of them selected — the ranking's best
   * until the user picks another.
   *
   * ORDERED BY `rankBaseResumes` and by nothing else. The library's own order
   * is the order they were created in, which is a listing that makes users
   * pick blind (decisions.js records what that cost). The ORDER is this
   * surface's choice; the numbers in it are the backend's, and nothing here
   * computes one.
   *
   * `best` is the top of the RANKING rather than the top of the list: an
   * all-unscored library has no best, and the green chip must not land on
   * whichever row happens to be first.
   *
   * READ-ONLY BESIDE AN APPLICATION (owner decision, 2026-09-27): its own base
   * answered the question, so the body names that base and shows the ranking
   * as information. A pick there would move the Before ring off the resume
   * the application was actually tailored from.
   */
  function baseBody(ctx) {
    const { node, attach } = ctx.build;
    const ranked = rankBaseResumes(ctx.facts.resumes, ctx.facts.scores);
    const best = ranked.findIndex((entry) => entry.score !== null);
    const body = node("div", "stg-body");
    if (ctx.facts.application) {
      const usedSlug = ctx.facts.application.base_resume || ctx.facts.baseSlug;
      const list = node("div");
      ranked.forEach((entry, index) =>
        attach(list, infoRow(ctx, entry, index === best, usedSlug)));
      return attach(body, node("div", "sub", tailoredFrom(ctx, ranked, usedSlug)), list,
                    node("div", "sub", ATS_SCORE_LEAD));
    }
    const list = node("div");
    list.setAttribute("role", "radiogroup");
    list.setAttribute("aria-label", "Base resume, best match first");
    ranked.forEach((entry, index) => attach(list, baseRow(ctx, entry, index === best)));
    return attach(body, list,
                  node("div", "sub", rankingNote(ctx, ranked)),
                  node("div", "sub", ATS_SCORE_LEAD));
  }

  ns.panelStageJob = jobBody;
})();
