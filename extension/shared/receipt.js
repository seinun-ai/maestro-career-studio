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
 * THE PAGE'S OWN INVENTORY IS THE SOURCE OF A ROW. A rule-pass write names the
 * field it went to (`fid`, from `content/inventory.js`), and the row's
 * question, section, value and options are read from that field after the run:
 * the label a rule matched on is the option's text for a radio or a checkbox.
 * A write with no field behind it is not recorded.
 *
 * EVERY OCCURRENCE IS KEPT. Two fields with one label (a second "Company" in
 * a work-history block) are two entries, in page order: the server keeps the
 * latest answer per (step, section, question, occurrence), so folding them
 * here would make the second field's answer overwrite the first's.
 *
 * WHAT THIS FILE PUBLISHES: ns.receipt = { fromLoop, fromRulePass,
 * fromEdits, seenOf, typedAnswer, pageOf, sourceOfSlot, sourceOfRule }.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const PROFILE_SECTIONS = new Set(["personal", "work_auth", "eligibility", "eeo", "preferences",
                                    "education", "languages"]);
  // The loop statuses that left a value the Companion chose on the page; the
  // first three carry that value as their `answer`, the others a note.
  const WROTE = new Set(["verified", "closest", "assumed", "partial", "unconfirmed"]);
  const ANSWERED = new Set(["verified", "closest", "assumed"]);
  // The EEO rules' ids (`content/eeo.js`) and the profile slot each answers.
  const EEO_SLOTS = { gender: "eeo.gender", "race-ethnicity": "eeo.race_ethnicity",
                      "hispanic-latino": "eeo.hispanic_latino", veteran: "eeo.veteran_status",
                      disability: "eeo.disability_status" };
  // The backend's limits (app/schemas/filled_answers.py): a field is cut to
  // them here, so one oversize field cannot make the server refuse the run.
  const MAX_FIELDS = 300;
  const MAX_QUESTION = 500;
  const MAX_SECTION = 200;
  const MAX_SLOT = 120;
  const MAX_ANSWER_CHARS = 20000;
  const MAX_ITEMS = 100;
  const MAX_ITEM_CHARS = 500;
  const MAX_OPTIONS = 1000;
  const clip = (text, n) => String(text ?? "").slice(0, n);
  const fold = (text) => String(text ?? "").toLowerCase().replace(/\s+/g, " ").trim();

  const neverFilled = (question) => {
    if (typeof ns.isNeverFilled !== "function") throw new Error("receipt: shared/policy.js is not loaded");
    return ns.isNeverFilled(question);
  };

  function sourceOfSlot(slot) {
    const section = String(slot ?? "").split(".")[0];
    if (PROFILE_SECTIONS.has(section)) return "profile";
    if (section === "experience" || section === "skills") return "resume";
    // `derived.full_name` is the profile's own first and last name joined: a
    // saved fact, so it reads as the profile's like the rule `full-name` does.
    if (slot === "derived.full_name") return "profile";
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
      const items = value.map((item) => clip(item, MAX_ITEM_CHARS).trim()).filter(Boolean).slice(0, MAX_ITEMS);
      return items.length ? items : null;
    }
    const text = String(value ?? "").trim();
    return text ? clip(text, MAX_ANSWER_CHARS) : null;
  }

  /** fid → the field as the page holds it now, from the frames that answered. */
  function inventoryOf(frames) {
    const out = new Map();
    for (const frame of frames ?? []) {
      for (const field of frame?.result?.fields ?? []) out.set(field.fid, field);
    }
    return out;
  }

  /** One field as the server takes it, cut to its bounds; null when it has no
   * question (the server refuses a blank one, and one such field must never
   * cost the whole run its record). */
  function entry(base, extra) {
    const question = clip(base.question, MAX_QUESTION).trim();
    // The never-fill labels (signatures, passwords, government IDs) are judged
    // by the policy's consent-INDEPENDENT list: standing consent lifts the
    // fill's rules, not this one. A missing policy script fails loud and closed
    // (the builder throws, the post is skipped).
    if (!question || neverFilled(question)) return null;
    return { question, section: base.section ? clip(base.section, MAX_SECTION) : null,
             required: Boolean(base.required), options_count: null, slot: null,
             eeo: false, edited_by_you: false, ...extra };
  }

  /** How many options a multi-select page field offered, or null. */
  const optionsOf = (live) => {
    const count = live?.multi ? (live.options ?? []).length : 0;
    return count ? Math.min(count, MAX_OPTIONS) : null;
  };

  function loopEntry(row, live) {
    const yours = row.status === "yours";
    if (live?.policyBlocked || (!yours && !WROTE.has(row.status))) return null;
    const answer = answerOf(live ? live.committed : (ANSWERED.has(row.status) ? row.answer : null));
    if (answer === null) return null;
    return entry(row, {
      answer,
      source: yours ? "you" : sourceOfRow(row),
      slot: row.route === "slot" ? clip(row.slot, MAX_SLOT) || null : null,
      eeo: String(row.slot ?? "").startsWith("eeo."),
      edited_by_you: !yours && live?.touched === true,
      options_count: optionsOf(live),
    });
  }

  /** One field you typed or changed, as an entry, or null when it is not
   * recordable: untouched, never-fill, unreadable or blank. */
  function youEntry(live) {
    if (!live.touched || live.policyBlocked || live.shape === "unknown") return null;
    const answer = answerOf(live.committed);
    const field = answer === null ? null
      : entry(live, { answer, source: "you", options_count: optionsOf(live) });
    return field && { fid: live.fid, field };
  }

  /** The fields you typed or changed that no report names. */
  function youEntries(inventory, taken) {
    return [...inventory.values()].filter((live) => !taken.has(live.fid))
      .map(youEntry).filter(Boolean);
  }

  function uploadEntry(upload) {
    if (upload?.outcome !== "attached" || !upload.filename) return [];
    return [{ fid: null, field: entry({ question: "Resume" },
                                      { answer: clip(upload.filename, MAX_ITEM_CHARS), source: "upload", slot: "resume" }) }];
  }

  /** The entries in the page's own order (the server counts a repeated label
   * by its place in the row), those the page does not list (the upload) last;
   * capped at the server's field limit. */
  function finish(entries, inventory) {
    const place = new Map([...(inventory?.keys() ?? [])].map((fid, at) => [fid, at]));
    const rank = (one) => place.get(one.fid) ?? Infinity;
    const kept = entries.filter((one) => one.field).sort((a, b) => rank(a) - rank(b)).slice(0, MAX_FIELDS);
    return { fields: kept.map((one) => one.field), fids: kept.map((one) => one.fid ?? null) };
  }

  /** Every field an earlier post named (`seen`, by field id) that is still on
   * the page, restated as it stands and under the source it was posted with,
   * unless this run already has it. The server keeps the newest answer per
   * (step, section, question, OCCURRENCE in the row), so a run that posts only
   * the third "Company" would land on the first one's place: a run restates
   * what is already there. */
  function restated(inventory, seen, taken) {
    return [...inventory.values()].filter((live) => seen?.[live.fid] && !taken.has(live.fid))
      .map((live) => editOf(live, seen[live.fid])?.one).filter(Boolean);
  }

  /** A loop run (`ns.fillLoop.runFill`'s report), the page after it,
   * Autofill's own attach (`autoAttachResume`'s report, or null) and what an
   * earlier post said (`seen`, or undefined). */
  function fromLoop(report, frames, upload, seen) {
    const inventory = inventoryOf(frames);
    const rows = report?.fields ?? [];
    const written = rows.map((row) => ({ fid: row.fid, field: loopEntry(row, inventory.get(row.fid)) }));
    const yours = youEntries(inventory, new Set(rows.map((row) => row.fid)));
    const mine = [...written.filter((one) => one.field), ...yours];
    const again = restated(inventory, seen, new Set(mine.map((one) => one.fid)));
    return finish([...mine, ...again, ...uploadEntry(upload)], inventory);
  }

  /** The field a rule write went to, as the page holds it now. The question,
   * section, options and value are the INVENTORY's, found by the fid the rule
   * pass named: the label a rule matched on is the option's text for a radio
   * or a checkbox, a name for a bare input. A write with no field behind it
   * (no fid, a frame that did not answer), one the page does not hold, and one
   * the policy never fills are not recorded. */
  function ruleEntry(item, live) {
    if (!live || live.policyBlocked) return null;
    const answer = answerOf(live.committed);
    if (answer === null) return null;
    const eeoSlot = EEO_SLOTS[item.rule] ?? null;
    const field = entry(live, { answer, source: sourceOfRule(item.rule), eeo: eeoSlot !== null,
                                slot: eeoSlot, edited_by_you: live.touched === true,
                                options_count: optionsOf(live) });
    return field && { fid: live.fid, field };
  }

  /** A rule-pass run (`reconcileFill`'s `fill`), the page after it, and the
   * attach and `seen` (see `fromLoop`). One entry per FIELD (a checkbox group
   * written box by box is one), a field you changed after a rule wrote it keeps
   * the rule's source. `before` is the set of fids you had already changed when
   * the run began: a rule that wrote over one of them wrote AFTER your touch, so
   * the value is the rule's and is not marked as yours. */
  function fromRulePass(fill, frames, upload, { seen, before } = {}) {
    const inventory = inventoryOf(frames);
    const taken = new Map();
    for (const item of [...(fill?.filled ?? []), ...(fill?.corrected ?? [])]) {
      const one = taken.has(item.fid) ? null : ruleEntry(item, inventory.get(item.fid));
      if (one) taken.set(one.fid, one);
    }
    for (const one of taken.values()) {
      if (before?.has(one.fid)) one.field.edited_by_you = false;
    }
    const mine = [...taken.values(), ...youEntries(inventory, taken)];
    const again = restated(inventory, seen, new Set(mine.map((one) => one.fid)));
    return finish([...mine, ...again, ...uploadEntry(upload)], inventory);
  }

  /** What the receipt remembers of a row it posted, by field id: enough to
   * post a later edit of that field under the same source. */
  function seenOf(built) {
    const out = {};
    built.fids.forEach((fid, at) => {
      if (!fid) return;
      const { source, slot, eeo, edited_by_you: edited, answer } = built.fields[at];
      out[fid] = { source, slot, eeo, edited, answer: JSON.stringify(answer) };
    });
    return out;
  }

  /** One field of the page against what an earlier post said of it: its entry
   * (your edit keeps a run's source and marks it edited), and whether it is a
   * change worth posting. Null when the page's field is not recordable. */
  function editOf(live, before) {
    if (live.policyBlocked || live.shape === "unknown") return null;
    if (!before && !live.touched) return null;
    const answer = answerOf(live.committed);
    if (answer === null && !(before && live.touched)) return null;
    const changed = live.touched && (!before || JSON.stringify(answer) !== before.answer);
    const field = entry(live, {
      answer, source: before?.source ?? "you", slot: before?.slot ?? null, eeo: before?.eeo ?? false,
      edited_by_you: before ? Boolean(before.edited) || (live.touched && before.source !== "you") : false,
      options_count: optionsOf(live) });
    return field && { changed, one: { fid: live.fid, field } };
  }

  /** The page now against what was posted (`seen`, by field id): the fields
   * you typed or changed since, in a row that also restates every field
   * already posted, so the server's per-occurrence order holds. Empty when
   * nothing changed. */
  function fromEdits(frames, seen) {
    const inventory = inventoryOf(frames);
    const edits = [...inventory.values()].map((live) => editOf(live, seen?.[live.fid])).filter(Boolean);
    if (!edits.some((edit) => edit.changed)) return { fields: [], fids: [] };
    return finish(edits.map((edit) => edit.one), inventory);
  }

  /** One pause-row answer: typed into the panel, written on the page. */
  function typedAnswer(label, answer) {
    const value = answerOf(answer);
    return finish(value === null ? [] : [{ fid: null,
      field: entry({ question: label }, { answer: value, source: "you" }) }], null);
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

  ns.receipt = { fromLoop, fromRulePass, fromEdits, seenOf, typedAnswer, pageOf, sourceOfSlot, sourceOfRule };
})();
