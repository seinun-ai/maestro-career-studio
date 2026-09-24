/* Maestro CS Companion — the Score stage's body.
 *
 * One of five files behind `ns.panelStages`; `panel/stages.js` is the joiner
 * and carries the whole contract. Read it before adding anything here.
 *
 * THE RULE, restated because a file that only POINTS at it is a file that
 * half-remembers it: NOTHING HERE REACHES FOR ANYTHING. No `card`, no `chrome`,
 * no `document`, no network — everything a body may read is on the CONTEXT it
 * is passed (`stageContext()` in panel.js is that contract's definition), and
 * firing one of its callbacks is the only way it changes anything.
 *
 * ONE EXCEPTION, and it is the same one every file in this directory may make:
 * `shared/decisions.js` is read off the namespace rather than handed in,
 * because the ranking is a DECISION both surfaces read one copy of rather than
 * a fact about this render.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const { rankBaseResumes } = ns.decisions;

  /** The one line under the ranked list: how much of it is real. */
  function rankingNote({ build }, ranked) {
    if (!ranked.length) return "No base resumes yet. Add one in Maestro CS.";
    const scored = ranked.filter((row) => row.score !== null).length;
    // The affordance named in words, because the button that runs it sits in
    // the footer rather than in this body — "Score base resumes" is a compute
    // call, so it happens when the user asks and never on open.
    if (!scored) return "Not scored for this job yet. Select Score base resumes below.";
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
    row.setAttribute("role", "radio");
    row.setAttribute("aria-checked", selected ? "true" : "false");
    const dot = node("span", "r");
    dot.setAttribute("aria-hidden", "true");
    // "not scored" is a WORD, never a zero: a base resume nobody has scored
    // against this job has no number, and printing one would be the panel
    // inventing the judgement it exists to render. Rounded, never computed —
    // the composite is the backend's (design §4.2).
    const score = entry.score === null
      ? node("span", "score", "not scored")
      : node("span", best ? "score good" : "score", String(Math.round(entry.score)));
    attach(row, dot, node("b", null, entry.display_name || entry.slug), score);
    row.addEventListener("click", () => act.pickBase(entry.slug));
    return row;
  }

  /** The Score stage: every base resume this job has an opinion about, best
   * first, and one of them selected.
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
   */
  function scoreBody(ctx) {
    const { node, attach } = ctx.build;
    const ranked = rankBaseResumes(ctx.facts.resumes, ctx.facts.scores);
    const best = ranked.findIndex((entry) => entry.score !== null);
    const list = node("div");
    list.setAttribute("role", "radiogroup");
    list.setAttribute("aria-label", "Base resume, best match first");
    ranked.forEach((entry, index) => attach(list, baseRow(ctx, entry, index === best)));
    return attach(node("div", "stg-body"), list,
                  node("div", "sub", rankingNote(ctx, ranked)));
  }

  ns.panelStageScore = scoreBody;
})();
