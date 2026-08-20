/* Maestro CS Companion — what the remainder pass ASKS, and what it reports.
 *
 * The pure half of the open-questions path: split the collected controls into
 * essays and ChooseFields, batch the ChooseFields at 40, and shape the
 * value-free telemetry the run produces. No `document`, no `location`, no
 * `chrome`, no network — `requestChoose` takes the POST as an injected
 * `postChoose`, exactly as `shared/guided-run.js` takes its transport.
 *
 * WHY IT IS A FILE AT ALL, and it is worth being exact because "shared" is
 * where things drift to. `shared/guided-run.js` reads these three functions off
 * the namespace at call time, and until now all three lived in
 * `content/open-questions.js` — a CONTENT SCRIPT. In a panel document they are
 * undefined whatever the load order, so the Fill stage's first click bought a
 * TypeError and nothing else. The rest of that file must NOT follow them here:
 * `collectOpenQuestions`, `applyGuidedChoices` and `fillAnswersByQid` are
 * page-DOM writers and a panel has no page. So this is a split of one file
 * rather than a move of it, and the line is exactly "does it touch the page".
 *
 * THREE THINGS TRAVELLED WITH THEM, and one deliberately did not:
 *
 * - `chunkChooseFields` and `CHOOSE_BATCH_SIZE` are `requestChoose`'s, not the
 *   collector's. Leaving either behind would silently remove the cap, which is
 *   the one number the whole /choose contract is written around.
 * - `QUESTIONY` is HERE and published as `ns.QUESTIONY`, which is the decision
 *   the split forced. Two readers need it — `routeOpenQuestions` (textareas,
 *   below) and `collectOpenQuestions` (plain text inputs, still content-side) —
 *   and the alternative was a copy on each side under a byte-equality pin. The
 *   copy would have been the wrong shape here: this repo's byte-identical pins
 *   (the commit ladder) exist because those functions are INJECTED and must be
 *   self-contained, and `collectOpenQuestions` is not — it already reads
 *   `ns.isPolicyBlocked` and `ns.lastRuleAttempts` off the namespace at call
 *   time, so one more `ns.` read costs it nothing and buys ONE definition of a
 *   regex whose own comment forbids loosening it. A pin can only tell you two
 *   copies still agree; it cannot stop the second one existing.
 * - `createArmedDebouncer` stayed content-side, on the grounds that it
 *   belonged to the floating card's stage observer. R-C deleted the card and
 *   the function with it: nothing arms a run but a click now.
 *
 * WHAT THIS FILE PUBLISHES: ns.QUESTIONY, ns.routeOpenQuestions,
 * ns.chunkChooseFields, ns.requestChoose, ns.buildRestFillObservations.
 *
 * Loaded by the manifest's content_scripts (before open-questions.js, which
 * reads the regex) and by panel.html's script tags (before guided-run.js, which
 * calls all three).
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  // Shared with collection (plain text inputs, `collectOpenQuestions`) and
  // routing (essay vs /choose, `routeOpenQuestions` below).
  // Do not loosen: `middle name` passes EXCLUDE and is stopped only here.
  const QUESTIONY =
    /\?|why\b|describe|tell (us|me)|what\b|how\b|experience|interest|motivat|excite|salary|compensation|notice|referr|hear about/i;

  /** Split the remainder: QUESTIONY textareas stay on /api/qa; everything else
   * becomes a ChooseField for one batched /choose call. qids are the ones
   * collection stamped — unique, stable, the write path's only address.
   *
   * `knownValues` is retained for explicit callers, but MUST NOT be fed from
   * `lastRuleAttempts`: released and retryable controls can share a label, and
   * doing so would re-attach the retry's profile value to the released field. */
  function routeOpenQuestions(questions, knownValues = {}) {
    const essays = [];
    const chooseFields = [];
    const seen = new Set();
    for (const q of questions ?? []) {
      if (!q?.qid || seen.has(q.qid)) continue;
      seen.add(q.qid);
      if (q.kind === "textarea" && QUESTIONY.test(q.label ?? "")) {
        essays.push(q);
        continue;
      }
      const field = {
        qid: q.qid,
        label: q.label,
        kind: q.kind,
        options: Array.isArray(q.options) ? q.options.slice(0, 30) : [],
      };
      const known = knownValues[q.qid] ?? knownValues[q.label] ?? q.known_value;
      if (known) field.known_value = known;
      chooseFields.push(field);
    }
    return { essays, chooseFields };
  }
  // ---- end routeOpenQuestions ----


  const CHOOSE_BATCH_SIZE = 40;

  function chunkChooseFields(fields, size = CHOOSE_BATCH_SIZE) {
    const out = [];
    for (let i = 0; i < (fields?.length ?? 0); i += size) {
      out.push(fields.slice(i, i + size));
    }
    return out;
  }
  // ---- end chunkChooseFields ----


  /** One batched /choose call per stage, chunked at 40. A network/5xx on a
   * chunk residues those fields and keeps going — never throws, never asks the
   * caller to roll back the rule pass. Abstains are residue, not retries. */
  async function requestChoose(fields, { postChoose, applicationId } = {}) {
    const choices = {};
    const residue = [];
    if (!fields?.length) return { choices, residue };
    if (typeof postChoose !== "function") {
      return { choices, residue: [...fields] };
    }
    for (const chunk of chunkChooseFields(fields)) {
      try {
        const body = { fields: chunk };
        if (applicationId) body.application_id = applicationId;
        const res = await postChoose(body);
        Object.assign(choices, res?.choices ?? {});
      } catch (_) {
        residue.push(...chunk);
      }
    }
    const residued = new Set(residue.map((field) => field.qid));
    for (const field of fields) {
      if (residued.has(field.qid)) continue;
      const choice = choices[field.qid];
      if (!choice || choice.reason === "abstained" || choice.answer == null) {
        residue.push(field);
      }
    }
    return { choices, residue };
  }
  // ---- end requestChoose ----


  const REST_FILL_OUTCOMES = new Set([
    "filled", "retry_filled", "match_recovered", "filled_unverified",
    "not_stuck", "ai_abstained",
  ]);

  /** The `rest_fill` batch: one observation per field the run has something
   * true to say about, and never a value.
   *
   * THE HOST IS THE ROW'S, and only the row's. This function used to fall back
   * to `location.hostname` when a row carried none, which was already
   * unnecessary — `collectFromPage` stamps every question and every retryable
   * with the host of the FRAME that answered, which is the truthful host for an
   * iframe-embedded form — and the move made it a lie as well: in a panel
   * document `location.hostname` is the extension's own id, so the fallback
   * would have attributed a Workday fill to `chrome-extension://…`. Removed
   * rather than made conditional. A row with no host reports none, which is
   * what "we do not know" looks like on the wire.
   *
   * Both lists resolve through `byQid` first, which is why nothing is lost by
   * that: a write result carries `{qid, outcome}` and an abstained ChooseField
   * carries no host either, but both name a qid that `questions` holds with its
   * host attached. `fallback` is what a qid outside that map degrades to, and
   * such a row cannot be produced by the shipped collector. */
  function buildRestFillObservations({ questions, writeResults, abstained }) {
    const byQid = new Map((questions ?? []).map((q) => [q.qid, q]));
    const out = [];
    const push = (qid, outcome, fallback) => {
      if (!REST_FILL_OUTCOMES.has(outcome)) return;
      const q = byQid.get(qid) ?? fallback ?? {};
      const obs = {
        label: String(q.label ?? "").slice(0, 160),
        kind: q.kind ?? "text",
        host: q.host ?? "",
        outcome,
        rule_id: null,
      };
      if (Array.isArray(q.options) && q.options.length
          && (q.kind === "select" || q.kind === "radio" || q.kind === "combobox")) {
        obs.options = q.options.slice(0, 30);
      }
      out.push(obs);
    };
    for (const row of abstained ?? []) push(row.qid, "ai_abstained", row);
    for (const row of writeResults ?? []) push(row.qid, row.outcome, row);
    return out;
  }
  // ---- end buildRestFillObservations ----


  ns.QUESTIONY = QUESTIONY;
  ns.routeOpenQuestions = routeOpenQuestions;
  ns.chunkChooseFields = chunkChooseFields;
  ns.requestChoose = requestChoose;
  ns.buildRestFillObservations = buildRestFillObservations;
})();
