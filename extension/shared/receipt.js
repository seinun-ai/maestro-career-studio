/* Maestro CS Companion — the answer receipt: what one fill run left on the
 * page, and where each answer came from.
 *
 * PANEL-SIDE AND PURE, like `shared/fill-loop.js`: no `document`, no `chrome`,
 * no network. `panel/actions/fill.js` hands it a run's report and the page's
 * post-run inventory (`fill_inventory`, which only a frame that EARNS the
 * user's data answers: SYSTEM.md {#inv-frame-earns-data}) and posts what it
 * returns to `POST /api/jobs/{id}/filled-answers` through the generic `api`
 * door.
 *
 * THE RECEIPT IS NOT TELEMETRY. It carries values, so it never goes through
 * the value-free channels, never reads the telemetry setting, and nothing
 * here feeds those builders (SYSTEM.md {#inv-filled-answers-local}).
 *
 * SOURCES are the job page's pills. A slot's section says where a value came
 * from: the profile's sections are `profile`, a work-history entry or the
 * skills `resume`, a saved answer `custom`, a derived fact `inferred`. The
 * AI's prose is `written` and its other choices `inferred`. A field you typed
 * or changed is `you`; one you changed AFTER the Companion wrote it keeps the
 * Companion's source, is marked `edited_by_you`, and records your value. A
 * field the policy never fills (signatures, ID numbers) is never recorded,
 * even when you typed it. A field the run left open, left alone or found
 * already filled is not recorded: it is not the Companion's answer.
 *
 * EVERY OCCURRENCE IS KEPT. Two fields with one label (a second "Company" in
 * a work-history block) are two entries, in page order: the server keeps the
 * latest answer per (step, section, question, occurrence), so folding them
 * here would make the second field's answer overwrite the first's.
 *
 * WHAT THIS FILE PUBLISHES: ns.receipt = { fromLoop, fromRulePass,
 * typedAnswer, pageOf, sourceOfSlot, sourceOfRule }.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const PROFILE_SECTIONS = new Set(["personal", "work_auth", "eligibility", "eeo", "preferences",
                                    "education", "languages"]);
  // The loop statuses that left a value the Companion chose on the page; the
  // first three carry that value as their `answer`, the others a note.
  const WROTE = new Set(["verified", "closest", "assumed", "partial", "unconfirmed"]);
  const ANSWERED = new Set(["verified", "closest", "assumed"]);
  // A rule-pass write the engine could not confirm (`content/autofill.js` notes).
  const UNLANDED = /^(may not have registered|no matching option)/;
  // The EEO rules' ids (`content/eeo.js`) and the profile slot each answers.
  const EEO_SLOTS = { gender: "eeo.gender", "race-ethnicity": "eeo.race_ethnicity",
                      "hispanic-latino": "eeo.hispanic_latino", veteran: "eeo.veteran_status",
                      disability: "eeo.disability_status" };
  // The backend's limits (app/schemas/filled_answers.py).
  const MAX_FIELDS = 300;
  const clip = (text, n) => String(text ?? "").slice(0, n);
  const fold = (text) => String(text ?? "").toLowerCase().replace(/\s+/g, " ").trim();

  function sourceOfSlot(slot) {
    const section = String(slot ?? "").split(".")[0];
    if (PROFILE_SECTIONS.has(section)) return "profile";
    if (section === "experience" || section === "skills") return "resume";
    return section === "custom" ? "custom" : "inferred";
  }

  function sourceOfRow(row) {
    if (row.route === "free_text") return "written";
    return row.route === "slot" && row.slot ? sourceOfSlot(row.slot) : "inferred";
  }

  /** The rule pass's rule ids (`content/autofill.js` RULES): work history and
   * skills come off the resume, a saved answer is custom, the agreement tick
   * is derived, everything else is the profile's. */
  function sourceOfRule(rule) {
    if (rule === "custom") return "custom";
    if (rule === "consent-forms") return "inferred";
    return rule === "skills" || /^emp-/.test(rule ?? "") ? "resume" : "profile";
  }

  /** A value as the receipt stores it: a list stays a list, blank is null. */
  function answerOf(value) {
    if (Array.isArray(value)) {
      const items = value.map((item) => clip(item, 500).trim()).filter(Boolean).slice(0, 100);
      return items.length ? items : null;
    }
    const text = String(value ?? "").trim();
    return text ? clip(text, 20000) : null;
  }

  /** fid → the field as the page holds it now, from the frames that answered. */
  function inventoryOf(frames) {
    const out = new Map();
    for (const frame of frames ?? []) {
      for (const field of frame?.result?.fields ?? []) out.set(field.fid, field);
    }
    return out;
  }

  function entry(base, extra) {
    return { question: clip(base.question || "A field with no label", 500),
             section: base.section ? clip(base.section, 200) : null,
             required: Boolean(base.required), options_count: null, slot: null,
             eeo: false, edited_by_you: false, ...extra };
  }

  function loopEntry(row, live) {
    const yours = row.status === "yours";
    if (live?.policyBlocked || (!yours && !WROTE.has(row.status))) return null;
    const answer = answerOf(live ? live.committed : (ANSWERED.has(row.status) ? row.answer : null));
    if (answer === null) return null;
    return entry(row, {
      answer,
      source: yours ? "you" : sourceOfRow(row),
      slot: row.route === "slot" ? row.slot ?? null : null,
      eeo: String(row.slot ?? "").startsWith("eeo."),
      edited_by_you: !yours && live?.touched === true,
      options_count: live?.multi ? (live.options ?? []).length || null : null,
    });
  }

  /** One field you typed or changed, as an entry, or null when it is not
   * recordable: untouched, never-fill, unreadable or blank. */
  function youEntry(live) {
    if (!live.touched || live.policyBlocked || live.shape === "unknown") return null;
    const answer = answerOf(live.committed);
    return answer === null ? null : { fid: live.fid, field: entry(live, { answer, source: "you" }) };
  }

  /** The fields you typed or changed that no report names. */
  function youEntries(inventory, taken) {
    return [...inventory.values()].filter((live) => !taken.has(live.fid))
      .map(youEntry).filter(Boolean);
  }

  function uploadEntry(upload) {
    if (upload?.outcome !== "attached" || !upload.filename) return [];
    return [{ fid: null, field: entry({ question: "Resume" },
                                      { answer: clip(upload.filename, 500), source: "upload", slot: "resume" }) }];
  }

  function finish(entries) {
    const kept = entries.slice(0, MAX_FIELDS);
    return { fields: kept.map((one) => one.field), fids: kept.map((one) => one.fid ?? null) };
  }

  /** A loop run (`ns.fillLoop.runFill`'s report), the page after it, and
   * Autofill's own attach (`autoAttachResume`'s report, or null). */
  function fromLoop(report, frames, upload) {
    const inventory = inventoryOf(frames);
    const rows = report?.fields ?? [];
    const written = rows.map((row) => ({ fid: row.fid, field: loopEntry(row, inventory.get(row.fid)) }))
      .filter((one) => one.field);
    const taken = new Set(rows.map((row) => row.fid));
    return finish([...written, ...youEntries(inventory, taken), ...uploadEntry(upload)]);
  }

  // A rule label is the field's joined label text (`labelFor`): its first part
  // is the <label>'s own words.
  const questionOfLabel = (label) => String(label ?? "").split(" | ")[0].trim();

  /** What the rule pass wrote, one entry per write, in the order it wrote. */
  function ruleEntries(fill) {
    const eeo = new Map((fill?.eeoFilled ?? []).map((item) => [item.label, EEO_SLOTS[item.field] ?? null]));
    const out = [];
    for (const item of [...(fill?.filled ?? []), ...(fill?.corrected ?? [])]) {
      const answer = answerOf(item.value);
      if (UNLANDED.test(item.note ?? "") || answer === null) continue;
      out.push({ fid: null, field: entry({ question: questionOfLabel(item.label) }, {
        answer, source: sourceOfRule(item.rule), eeo: eeo.has(item.label),
        slot: eeo.get(item.label) ?? null }) });
    }
    return out;
  }

  /** A field you changed after a rule wrote it: the rule's source, your value,
   * in the rule's place. */
  function changedRule(mine, ruled) {
    const { source, slot, eeo } = ruled.field;
    return { ...mine, field: { ...mine.field, source, slot, eeo, edited_by_you: true } };
  }

  /** The page's fields by their folded question, in page order. */
  function byQuestion(inventory) {
    const out = new Map();
    for (const live of inventory.values()) {
      const key = fold(live.question);
      out.set(key, [...(out.get(key) ?? []), live]);
    }
    return out;
  }

  /** Your changes over the rule pass's writes. The k-th field of a label
   * answers the k-th write of that label, so same-labelled fields never fold
   * into one. When the page and the pass disagree on how many of a label
   * there are, the k-th cannot be told, so a changed field is a plain `you`
   * entry beside the pass's own. */
  function mergeYours(ruled, inventory) {
    const out = [...ruled];
    const extra = [];
    const writes = new Map();
    ruled.forEach((one, at) => {
      const key = fold(one.field.question);
      writes.set(key, [...(writes.get(key) ?? []), at]);
    });
    for (const [key, fields] of byQuestion(inventory)) {
      const at = writes.get(key) ?? [];
      fields.forEach((live, k) => {
        const mine = youEntry(live);
        if (!mine) return;
        if (at.length === fields.length) out[at[k]] = changedRule(mine, out[at[k]]);
        else extra.push(mine);
      });
    }
    return [...out, ...extra];
  }

  /** A rule-pass run (`reconcileFill`'s `fill`), the page after it, and the
   * attach. A field you changed after a rule wrote it keeps the rule's source. */
  function fromRulePass(fill, frames, upload) {
    const merged = mergeYours(ruleEntries(fill), inventoryOf(frames));
    return finish([...merged, ...uploadEntry(upload)]);
  }

  /** One pause-row answer: typed into the panel, written on the page. */
  function typedAnswer(label, answer) {
    const value = answerOf(answer);
    return finish(value === null ? [] : [{ fid: null,
      field: entry({ question: questionOfLabel(label) }, { answer: value, source: "you" }) }]);
  }

  /** Where the run happened: the tab's host, and its path as the wizard step. */
  function pageOf(url) {
    try {
      const { hostname, pathname } = new URL(url);
      return { host: clip(hostname, 255) || null, step: clip(pathname, 300) || null };
    } catch {
      return { host: null, step: null };
    }
  }

  ns.receipt = { fromLoop, fromRulePass, typedAnswer, pageOf, sourceOfSlot, sourceOfRule };
})();
