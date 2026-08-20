/* Maestro CS Companion — shared decisions.
 *
 * Pure functions read by BOTH worlds: the content scripts (loaded first in
 * the manifest's content_scripts order) and the side panel document (loaded
 * by a <script> tag in panel.html). Nothing in this file may touch `document`,
 * `location`, `chrome.*`, or the network — that is what makes it loadable in
 * both and testable in node.
 *
 * AUTHORITATIVE, which it became at R-C rather than having been designed that
 * way. Several of these rules were once written twice — here and in the
 * floating card — with comments in both saying the two had to move together.
 * The card is gone; there is one copy of each judgement now, and the reasoning
 * that used to be split across two files is written out below in full.
 *
 * WHAT THIS FILE PUBLISHES: ns.decisions = { stageFor, rankBaseResumes,
 * sessionTenant, restorableSession, reconcileFill, sanitizeAnswer }.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  /** Which stage of the journey this card is at, computed from data — never
   * from what the user last clicked.
   *
   * THIS FUNCTION IS THE HONESTY RULES, full stop. They used to be written
   * twice — here, and in the floating card's `resolvePrimary`, which is where
   * they were learned — and every one of them below is a defect somebody hit.
   * R-C deleted that second copy, so this is the only place they live and the
   * only place to change them. The RUNG ORDER is part of the rule: the base
   * shortcut first, then the library ladder.
   * - Filling a form is a question about the PAGE and the session; the library
   *   must not gate it. Conflating the two is what left a user who had
   *   deliberately armed a base resume with no way to fill the form in front
   *   of them: the primary reached `autofill` only through a tracked job with a
   *   tailored PDF, so Base mode was offered Add job or Fast tailor and nothing
   *   else — while the attach could already put that very resume in the page.
   * - `match !== "exact"` means "we do not know", not "none". An unreachable
   *   backend must not claim the job exists, so the journey opens at Job,
   *   which re-asks. The shortcut sitting above that check does not bend the
   *   rule: its copy claims a fill from base is possible — a page-and-session
   *   fact — never that the job exists. `done.job` stays false and the rail's
   *   Job row still offers Add job.
   * - The shortcut skips Score/Resume VISIBLY: `skipped` NAMES them, and it
   *   means "not required on the current path", never "done". `choiceSkipped`
   *   then names the one of them the user actually chose, because a skip they
   *   chose is a door back and a skip the path computed is not.
   * - `mark-applied` requires only a draft application (the 2026-08-16
   *   lesson: the confirmation page is where it is most wanted);
   *   `track-this` keeps the `touched` requirement, because before a
   *   deliberate no-write attach there is nothing to track.
   * - `hasForm` IS NOT A STAGE INPUT, and its removal from this function is
   *   the 2026-08-19 lesson (Yum, live). "Is there a form on this page" is a
   *   fact about the PAGE; "which question is still open" is what a stage
   *   is. Gating the shortcut on the form conflated them: a user who pressed
   *   "use base as-is" on a posting page had answered the Resume stage's own
   *   question, and the rail kept them on Resume — a step whose question was
   *   closed, with the Fill row locked and nothing anywhere saying why. The
   *   gate's real purpose (never offer Start fill into nothing) is a claim
   *   about a BUTTON, so it moved to the button: panel.js refuses the Fill
   *   primary without a form, and `stages/fill.js` says where filling
   *   actually happens. It is still read HERE for one thing only — the
   *   shortcut's COPY, below — because "Ready to autofill" is a promise about
   *   the page rather than about the stage.
   */
  function stageFor({
    match, hasApplication, pdfReady, status, touched, hasForm,
    baseArmed, hasScores, baseSelected,
  }) {
    const jobDone = match === "exact";
    const fillFromBase = baseArmed === true && !hasApplication;
    const scoreDone = jobDone && hasScores === true && baseSelected === true;
    const resumeDone = jobDone && hasApplication === true && pdfReady === true;
    const isDraft = (status ?? "draft") === "draft";
    const trackDone = hasApplication === true && !isDraft;
    // `touched` and nothing else: `done.fill` is this extension's own claim
    // that it filled or attached HERE, and an application marked applied
    // inside the web app must not put a checkmark on a page it never wrote to.
    const fillDone = touched === true;

    // The shortcut rung is FIRST, above the library ladder, because the page
    // is not the library's to gate. Everything below it is the library's own
    // order, where refusing to go BACKWARDS is the ladder's job and not
    // `done`'s: without the `trackDone` rung an application attached via
    // track-this and then marked applied — so `pdfReady` is false, it was
    // never tailored — fell through to "resume" and asked the user to tailor a
    // resume for a job they had already applied to.
    const stage =
      fillFromBase ? (fillDone ? "track" : "fill")
        : !jobDone ? "job"
          : trackDone ? "track"
            : !scoreDone ? "score"
              : !resumeDone ? "resume"
                : !fillDone ? "fill"
                  : "track";

    return {
      stage,
      done: { job: jobDone, score: scoreDone, resume: resumeDone,
              fill: fillDone, track: trackDone },
      // What the current path does not REQUIRE — never what is done. An
      // unmatched shortcut names Job here while `done.job` stays false, so the
      // rail greys the row and still offers Add job.
      skipped: fillFromBase
        ? (jobDone ? ["score", "resume"] : ["job", "score", "resume"])
        : [],
      // WHOSE skip it is — the same rows as `skipped`, filtered down to the
      // ones a user can take back. A skip has two provenances and they are not
      // interchangeable: `baseArmed` is a CLAIM the user made ("use base
      // as-is"), and a claim is theirs to withdraw; everything else on the
      // short rail is the path's own arithmetic, and there is nothing there to
      // withdraw. The rail reads this to decide which skipped row is a door
      // (panel.js `isReopenable`), and it is a list rather than a boolean so
      // the answer stays per-row.
      //
      // ONLY `resume`, and that is the honest reading rather than a narrowing.
      // The claim was made in answer to the RESUME stage's own question — the
      // fork asks "tailor, or not?" and "use base as-is" is the no — so Resume
      // is the row that holds it. Score is skipped because nothing needs a
      // ranking when nothing is being tailored, and Job because the shortcut
      // is a page-and-session fact that never asked the library: neither is a
      // decision anybody made, and putting a withdraw door on either would be
      // a second entrance to one claim.
      //
      // The empty list when `fillFromBase` is false is not "no claim exists" —
      // `baseArmed` may still be true beside an application that has overtaken
      // it — it is "no row is being skipped by one", which is the only question
      // this key answers. (It used to say "on a page with no form" as well,
      // and that half went with the form gate: a form-less page skips the same
      // rows now, because the user's answer is the same answer either way.)
      choiceSkipped: fillFromBase ? ["resume"] : [],
      fillFromBase,
      // "ready" covers two different facts and this sentence is what keeps
      // them apart: a tracked APPLICATION with a rendered PDF, or Base mode
      // with a resume armed over a form. The second said "Application ready"
      // about an application that does not exist — reported live as "where is
      // the open-application button" on a job that was never tracked.
      //
      // AND `hasForm` IS THE THIRD CONDITION, which is the whole of what the
      // form gate still decides here. The shortcut now reaches Fill on a
      // posting page too (see the rule above), and "Ready to autofill from
      // your base resume" over a page with no form is the same kind of false
      // promise this line was written to stop — one page later. There is no
      // no-form variant of the sentence because the Fill body says it, once,
      // where the user is already reading (`stages/fill.js`); a second copy
      // under the identity would be two sentences for one fact in a 400px
      // rail.
      shortcutNote: fillFromBase && stage === "fill" && hasForm === true
        ? "Ready to autofill from your base resume."
        : null,
      nudge: hasApplication
        ? (isDraft ? "mark-applied" : null)
        : (touched && isDraft ? "track-this" : null),
    };
  }

  /** Base resumes in the order this JOB ranks them, each carrying its score.
   *
   * The app already scores every base resume against a job — one endpoint,
   * `score_all_bases`, and the Score & Tailor tab is built on it — but the
   * extension never asked, so its dropdown listed resumes in library order and
   * the user picked blind. Fast tailor then built on whatever that pick was,
   * and the one number shown afterwards was the score of a resume nobody had
   * reason to believe was the right one.
   *
   * Ranked here rather than server-side because the ORDER is a presentation
   * choice and the scores are not: every number below is the backend's, and
   * this function never computes one (design §4.2, "render them; compute
   * nothing new").
   *
   * Unscored resumes keep their library order and sort last — "not scored yet"
   * is not a bad score, and showing it as one would be this function inventing
   * a judgement.
   */
  function rankBaseResumes(resumes, scores) {
    const bySlug = new Map();
    for (const row of scores ?? []) {
      if (row?.target_type !== "base_resume" || row?.phase !== "base") continue;
      const composite = Number(row.composite);
      if (!Number.isFinite(composite)) continue;
      // Latest wins: `latest_scores` already returns one row per target, but a
      // caller that concatenated two reads must not produce two entries.
      if (!bySlug.has(row.target_id)) bySlug.set(row.target_id, composite);
    }
    return (resumes ?? [])
      .map((resume, index) => ({
        ...resume,
        score: bySlug.has(resume.slug) ? bySlug.get(resume.slug) : null,
        index,
      }))
      .sort((a, b) => {
        if (a.score === b.score) return a.index - b.index;
        if (a.score === null) return 1;
        if (b.score === null) return -1;
        return b.score - a.score;
      });
  }

  /** Origin + first path segment: multi-tenant boards (job-boards.greenhouse.io)
   * share one origin across companies, so origin alone bleeds sessions
   * across tenants. Takes the URL as a string because the panel evaluates it
   * for a TAB, not for its own document.
   *
   * The first segment is the tenant slug on the shared boards and is stable
   * across a wizard's steps everywhere we fill (Workday keeps its tenant in
   * the subdomain, so the extra segment is harmless there).
   *
   * TOTAL, because the panel asks this about whatever a TAB currently holds
   * rather than about a page it is running inside: `new URL("")` THROWS, and
   * an empty or relative url is what a tab reports before it has committed
   * one. `null` is the answer there — "this page has no tenant identity".
   * (A `chrome://` page does not throw; it parses to an opaque origin and
   * scopes to itself, which is harmless because no pick is ever made on one.)
   * Nothing restores onto a null tenant by
   * tenant: a pick made on a real board carries a real tenant string, which
   * can never equal `null`, so `restorableSession` refuses it. The one thing
   * that still gets through is the backend naming the entry's own job, which
   * already outranks the tenant by design (see THE BACKEND WINS below) — a
   * missing tenant must not be able to overrule the stronger signal. */
  function sessionTenant(url) {
    try {
      const u = new URL(url);
      return `${u.origin}/${u.pathname.split("/")[1] ?? ""}`;
    } catch {
      return null;
    }
  }

  /** May a remembered pick be restored onto THIS page load?
   *
   * Pure, and its own function for the same reason `stageFor` is: it is a
   * whole judgement rather than a step of one, and it is the piece that
   * decides whether the panel shows an application the user is not looking at.
   * Three guards, each answering a different way of being wrong:
   *
   * ORIGIN. A pick belongs to the site it was made on. Stored per origin
   * rather than per URL because the URL changes on every wizard step, which is
   * exactly the case this exists for.
   *
   * FRESHNESS. An entry past its TTL is not a pick, it is a memory of one.
   * A clock that jumped backwards makes `age` negative, which is not fresh
   * either — hence the range test rather than `age < TTL`.
   *
   * THE BACKEND WINS. If `/api/jobs/match` recognised this page as a job, and
   * it is not the job the pick was made for, the pick is about a different
   * posting and is discarded. A Workday tenant serves every one of its jobs
   * from one origin, so without this the application picked for one posting
   * would be offered on the next — which is the most confident wrong thing
   * this surface could say. A match of `null`/`none` is not a contradiction:
   * it is the backend not knowing, which is the ordinary case on an apply URL,
   * and it is precisely when the remembered pick is worth having.
   */
  function restorableSession(entry, { now, origin, matchedJobId, ttlMs, tenant }) {
    if (!entry || entry.origin !== origin) return null;
    // Origin alone cannot scope the memory: multi-tenant boards
    // (job-boards.greenhouse.io, jobs.lever.co) put thousands of companies on
    // ONE origin, and a Cohere pick restored onto a Lightning posting — same
    // origin, different company — told the user "Application ready" about an
    // application that does not belong to the page (observed live
    // 2026-08-16). A cross-tenant entry, or a pre-tenant legacy entry, is
    // trusted only when the BACKEND matched this page to the very job the
    // entry names — the one signal stronger than the memory.
    const backendConfirms = Boolean(
      matchedJobId && entry.jobId && matchedJobId === entry.jobId);
    if (entry.tenant !== tenant && !backendConfirms) return null;
    const age = now - (entry.at ?? 0);
    if (!(age >= 0 && age < ttlMs)) return null;
    if (matchedJobId && entry.jobId && matchedJobId !== entry.jobId) return null;
    return entry;
  }

  /** The reconciliation strip's numbers, from the fill engine's own output.
   *
   * Design §4.2: "Render them; compute nothing new." Every value below already
   * exists — `filled[]`, `eeoFilled[]`, `corrected[]`, and one observation per
   * field carrying the commit ladder's outcome. This function buckets and
   * concatenates; it does not judge whether a field was filled.
   *
   * It takes the whole per-frame array rather than pre-flattened lists because
   * `reached` has to be decided from the same data. A frame contributes
   * `result: undefined` when it could not be reached or threw, and every
   * sentence the caller prints about the page — "no matching fields" — is a
   * lie when NO frame answered. Deciding that here means a caller cannot forget it.
   *
   * Buckets are the frozen outcome vocabulary of
   * `backend/app/schemas/autofill_telemetry.py`. `no_rule` is counted
   * separately and kept OUT of "skipped": an ATS form carries dozens of
   * controls no rule claims, and folding them in would print "38 skipped"
   * beside "14 filled" — a number about the size of the form, not about what
   * we did. The `ai_*` outcomes are absent because a profile fill cannot emit
   * them; an outcome this table does not know is left out of every count
   * rather than guessed into one.
   *
   * `already` is the one count NOT built from observations, because the engine
   * deliberately emits none for a field that already held the answer (the
   * frozen vocabulary has no outcome for a write that never happened). It is
   * the length of the engine's own `already` list — still rendered, never
   * judged here.
   */
  function reconcileFill(frames) {
    const BUCKET = {
      filled: "filled",
      filled_normalized: "filled",
      corrected: "corrected",
      not_stuck: "notStuck",
      combobox_snap_failed: "notStuck",
      policy_blocked: "skipped",
      skipped_checkbox: "skipped",
      missing_source: "skipped",
      eeo_disabled: "skipped",
      skip_rule: "skipped",
      hidden: "skipped",
      no_rule: "noRule",
    };
    const answered = frames.filter((frame) => frame.result !== undefined);
    const observations = answered.flatMap((frame) => frame.result.observations ?? []);
    const counts = { filled: 0, corrected: 0, notStuck: 0, skipped: 0, noRule: 0 };
    for (const observation of observations) {
      const bucket = BUCKET[observation.outcome];
      if (bucket) counts[bucket] += 1;
    }
    // Concatenated in frame order, which is the order the fan-out asked in.
    const already = answered.flatMap((frame) => frame.result.already ?? []);
    counts.already = already.length;
    return {
      reached: answered.length > 0,
      counts,
      observations,
      already,
      filled: answered.flatMap((frame) => frame.result.filled ?? []),
      eeoFilled: answered.flatMap((frame) => frame.result.eeoFilled ?? []),
      corrected: answered.flatMap((frame) => frame.result.corrected ?? []),
    };
  }

  /** The markdown a model reaches for, stripped out of text that is going into
   * a plain form field.
   *
   * THE RULES ARE WRITTEN DOWN rather than left to be read off the regexes,
   * and that is a habit worth keeping now that there is one caller again: this
   * function was moved here at Task 14 precisely so two surfaces could paste
   * through one sanitizer, and the surviving one is the panel's QnA drawer,
   * which renders the answer and hands it to the clipboard for the user to
   * paste. The destination is a plain form field, so what a model formats FOR
   * a chat window — a heading, a bolded phrase, a bullet, a fence, a rule —
   * arrives in an application as literal `##` and `**` characters.
   *
   * A SECOND COPY STILL EXISTS and is pinned identical: `fillAnswersByQid` is
   * INJECTED into the page, where `window.careerStudioCompanion` does not
   * exist, so it carries the same six-`.replace` chain inline. See
   * `extension/.slopconfig.json` and
   * `test_the_injected_copy_of_the_sanitizer_stays_identical_to_the_shared_one`.
   *
   * Each line strips a marker and KEEPS its content, which is the whole
   * posture: nothing here decides an answer is wrong, only that a form field
   * cannot render it. The blank-line collapse is the one that is about reading
   * rather than syntax — a model's paragraph spacing survives, its
   * triple-spacing does not — and the trim is what keeps a leading newline out
   * of a box the user is about to submit.
   *
   * WHAT IT DELIBERATELY DOES NOT TOUCH, written down so the next reader knows
   * the list is short by choice and not by accident: pipe tables, `[link](url)`,
   * `> blockquotes`, `_underscore emphasis_`, and setext headings (a line
   * underlined with `===`). Each is either rare in an answer to an application
   * question or ambiguous with ordinary prose — an underscore is a filename, a
   * `>` is a quotation, a bare url in parentheses is a citation — and stripping
   * an ambiguous marker edits the user's text rather than unformatting it,
   * which is the one thing this function may not do.
   *
   * ONE KNOWN RESIDUE, for the same reason: `***both***` leaves a single
   * asterisk on each side, because the bold pattern takes the inner pair and
   * `[^*]+` cannot match across the third. It is pinned by a case in the table
   * rather than fixed — a greedier pattern would start eating the lone
   * asterisks that appear in honest prose, and one stray character is the
   * cheaper of the two errors in a box the user reads before submitting.
   *
   * TOTAL, because a `null` answer is what a backend that returned nothing
   * looks like by the time it reaches here, and `String(null)` printing "null"
   * into a cover-letter box is the failure this guard is for. */
  function sanitizeAnswer(text) {
    return String(text ?? "")
      .replace(/^#{1,6}\s+/gm, "")
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/`{1,3}([^`]*)`{1,3}/g, "$1")
      .replace(/^\s*(?:[-*•]|\d+[.)])\s+/gm, "")
      .replace(/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/gm, "")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  ns.decisions = {
    stageFor, rankBaseResumes, sessionTenant, restorableSession, reconcileFill,
    sanitizeAnswer,
  };
})();
