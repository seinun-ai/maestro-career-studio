/* Maestro CS Companion — the QnA drawer: one question, one grounded answer.
 *
 * One of the concern files behind `ns.panelActions`; `panel/actions.js` is the
 * joiner and carries the whole contract. Read it before adding anything here.
 *
 * THE RULES, restated because a file that only POINTS at them is a file that
 * half-remembers them:
 *
 * - AN ACTION WRITES, holds `busy` for as long as that takes, obeys the
 *   generation rule in full, and never assigns a stage.
 * - THE `busy` SPAN IS `duringAction`'s, read off the namespace and never
 *   re-implemented — see `panel/actions/during.js`. The `busy` this action
 *   takes is the FILL stage's, because the drawer lives in the Fill body: the
 *   footer's primary, the mode segments, the pause rows and the essay rows'
 *   own Ask are all out of reach while a question is open, exactly as they are
 *   during a fill.
 * - NOTHING HERE REACHES FOR ANYTHING: no `card`, no `chrome`, no `document`,
 *   no `fetch`, no timers.
 *
 * ONE NAMESPACE READ: `sanitizeAnswer` from `shared/decisions.js` — a
 * DECISION, not a fact about this panel, which is what makes it belong there
 * rather than here.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const duringAction = ns.panelDuringAction;
  const { sanitizeAnswer } = ns.decisions;

  /** WHAT GROUNDS THIS ANSWER, and the refusal when nothing does.
   *
   * `POST /api/qa` takes `application_id` OR `job_id` and refuses a body with
   * neither (`run_qa`, backend/app/routers/qa.py). The two are different
   * groundings rather than two spellings of one: an application answers from
   * the tailored resume and this job's own Q&A history, a job answers from the
   * base resume and the posting.
   *
   * REFUSING WITHOUT AN APPLICATION would be a dead control here, and that is
   * the trap this avoids: the panel reaches the Fill stage on a path that has
   * no application at all — "use base as-is" arms a fill with a job and
   * nothing else — and the essays that land in this drawer come out of exactly
   * those runs. So the SHAPE is `resumeQuery`'s (`panel/actions/fill.js`): the
   * most specific grounding we hold, in the same order.
   *
   * THE SECOND RUNG IS NOT `resumeQuery`'s SECOND, and the difference is worth
   * the paragraph. There the base slug is a query parameter on an autofill
   * read; here it is `base` on the QA body, and sending it is what makes the
   * sentence this action prints ("Answered from your base resume and this
   * posting") a true one. Without it the route grounds on a generic default
   * resume the user never picked — the document the whole Score stage exists to
   * have them choose against — so the panel would be filling an essay box from
   * one resume while the fill beside it wrote from another.
   *
   * `null` is the third rung and it now has TWO ways of being reached: nothing
   * to ground on at all, or a job with no base picked. Neither can be answered
   * honestly, so the caller says so rather than sending a body the route would
   * refuse and calling that an outage.
   */
  function qaGrounding(facts) {
    if (facts.application) return { application_id: facts.application.id };
    if (!facts.job || !facts.baseSlug) return null;
    return { job_id: facts.job.id, base: facts.baseSlug };
  }

  /** Ask one question and get a paragraph back, grounded in this application.
   *
   * THE COMPOSER, AND ONLY THE COMPOSER: the per-application Q&A TRANSCRIPT is
   * list-shaped, versioned and re-readable, and the web app does it better
   * (design §4.2). A 400px rail is the wrong place for a chat log.
   *
   * ONE POST to `/api/qa` with the grounding key and a one-element `questions`
   * array. NOT a batch: "fill the remaining questions" is a job
   * `shared/guided-run.js` already owns end to end, and a batch path here
   * would be a second pipeline for it.
   *
   * THE ANSWER IS SANITIZED even though this drawer only RENDERS it, because
   * rendering is not what the text is for: the drawer exists to be copied out
   * of, into a plain textarea on an ATS. `**bold**` is markdown in a chat
   * window and two literal asterisks in an application.
   *
   * ONE ROUND TRIP AND NO TAIL, so `duringAction`'s span covers every await
   * this action makes — see its contract for why the store writes that follow
   * the return are safe outside it, and for what changes the day one of them
   * needs an await.
   */
  async function askQuestion(store) {
    const facts = store.read();
    if (facts.busy !== null) return;
    const question = String(facts.qna.question ?? "").trim();
    if (!question) {
      store.write({ note: { text: "Paste a question first." } });
      store.render();
      return;
    }
    const grounding = qaGrounding(facts);
    if (!grounding) {
      // Nothing to answer FROM, and the two ways of getting here want different
      // sentences. Each names what the rail would ask for next, and the second
      // is `useBaseAsIs`'s own words for the same state — an empty library —
      // because two sentences for one condition is how a user comes to believe
      // there are two conditions.
      store.write({ note: { text: facts.job
        ? "No base resume yet — build one in Maestro CS."
        : "Add the job first — an answer is grounded in your resume and this "
          + "posting." } });
      store.render();
      return;
    }
    const done = await duringAction(store, "fill", () =>
      store.api("/api/qa", {
        method: "POST",
        body: JSON.stringify({ ...grounding, questions: [question] }),
      }));
    if (!done) return;
    // JOINED, not indexed: `_split_numbered_answers` may hand back one element
    // for a reply it could not split, and for a ONE-question ask that element
    // is the whole answer. The card joins for the same reason.
    const answer = sanitizeAnswer((done.out.answers ?? []).join("\n\n"));
    // RE-READ past the guard: the POST is a round trip and the loaders have
    // been writing to this store for the length of it. The draft question is
    // read back rather than reused, so a user who kept typing while the answer
    // was on the wire keeps their characters.
    const after = store.read();
    store.write({
      // `answered` is the question this paragraph belongs to and `question` is
      // left alone — the box keeps what the user has since typed, and the
      // answer says out loud which question it is for.
      qna: { ...after.qna, answered: question, answer, copied: false },
      note: { text: grounding.application_id
        ? "Saved to this application’s Q&A history."
        : "Answered from your base resume and this posting." },
    });
    store.render();
  }

  ns.panelActionsQna = { askQuestion };
})();
