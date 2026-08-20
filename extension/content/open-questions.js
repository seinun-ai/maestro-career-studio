/* Maestro CS Companion — open-question collection and answer injection.
 *
 * Shared content-script module, and since Task 12 it is the PAGE half of that
 * path and nothing else: everything here reads or writes the document, which is
 * exactly why it may not be loaded into a panel. The pure half — routing,
 * batching, and the telemetry shaping — is `shared/choose.js`, which both
 * surfaces load. The commit ladder inside fillAnswersByQid stays self-contained
 * because it is deliberately identity-pinned against the profile fill copy.
 *
 * `QUESTIONY` comes off the namespace for the same split: `collectOpenQuestions`
 * screens plain text inputs with it and `routeOpenQuestions` screens textareas
 * with it, and they now live in different files. ONE definition, in
 * `shared/choose.js`, whose comment carries the "do not loosen" rule.
 */

// ============================================================
// WHAT THIS FILE PUBLISHES
// ============================================================
(() => {
  const ns = (window.careerStudioCompanion ??= {});


// ============================================================
// AI SMART FILL — collect, then write back
// ============================================================

/** Runs IN THE PAGE (all frames). Finds visible, unanswered fields the
 * profile fill didn't cover — free text, textareas, dropdowns, and radio
 * groups — tags them with data-rt-qid, and returns
 * {qid, label, kind, options?}. Identity, work-authorization, and EEO fields
 * are excluded: those are the profile's job, never the AI's guess. Signatures,
 * attestations, consent and credentials are excluded too, under the same HR-3
 * deny-list the profile fill uses — this is the gate that keeps the model away
 * from them, because a field it does not collect is never tagged and so can
 * never be written. */
function collectOpenQuestions() {
  const norm = (s) => (s ?? "").toLowerCase().replace(/\s+/g, " ").trim();
  const token = Math.random().toString(36).slice(2, 8); // per-frame namespace

  // HR-3 is shared with the profile writer. This is the riskier path, so the
  // policy still runs at COLLECTION: an uncollected control receives no qid
  // and fillAnswersByQid cannot address it later.
  const EXCLUDE =
    /first\s*name|last\s*name|full\s*name|e-?mail|phone|mobile|address|\bcity\b|\bstate\b|zip|postal|country|linked\s*in|git\s*hub|website|portfolio|school|university|college|\bdegree\b|discipline|major|field of study|\bgpa\b|graduat|sponsor|authoriz|right to work|legally|veteran|disab|gender|race|ethnic|hispanic|resume|cover\s*letter|\bcv\b|location|password|search|date|employer|company\s*name|job\s*title|work\s*(history|experience)|employment|duties|responsibilit|\bdescription\b/i;
  // Free-text inputs need a question-ish label to avoid junk fields;
  // textareas, selects, and radios are almost always real questions.
  // QUESTIONY lives on the NAMESPACE (shared/choose.js) so routing can split
  // essays without drifting — see this file's header for why one definition
  // beat a pinned copy per side.

  const isVisible = (el) =>
    !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);

  // Same discriminator the profile writer uses (autofill.js isListboxButton).
  // Duplicated rather than imported: Lane S owns autofill.js this round.
  // Form dropdowns are <button aria-haspopup="listbox" type="button"> with no
  // data-automation-id; header chrome (Settings, account) is type=submit and
  // always carries an automation id.
  const isListboxButton = (el) =>
    el instanceof HTMLButtonElement
    && el.getAttribute("aria-haspopup") === "listbox"
    && el.type !== "submit"
    && !el.getAttribute("data-automation-id");
  const LISTBOX_PLACEHOLDER = /^(select( one)?|choose( one)?|—|-)?$/;
  const listboxButtonText = (button) =>
    String(button.innerText ?? button.textContent ?? "").trim();
  const listboxButtonEmpty = (button) =>
    LISTBOX_PLACEHOLDER.test(norm(listboxButtonText(button)));

  // A textarea inside a detected employment block belongs to the
  // structured employment fill, never the AI (design Part 2d): oddly
  // labeled Description fields were falling through and receiving
  // multi-employer markdown blobs. The walk stops at <form>/<body> —
  // scanning a whole single-form page would flag every textarea.
  const EMP_BLOCK = /employer|company\s*name|job\s*title|work\s*(history|experience)|employment/i;
  const inEmploymentBlock = (input) => {
    let node = input.parentElement;
    for (let depth = 0;
      node && node !== document.body && node.tagName !== "FORM" && depth < 6;
      depth += 1, node = node.parentElement) {
      const head = node.querySelector(
        ':scope > legend, :scope > h2, :scope > h3, :scope > h4, :scope > [class*="label" i], :scope > [class*="title" i]');
      if (head && EMP_BLOCK.test(head.innerText ?? "")) return true;
      if (depth < 3) {
        // Sibling scan only for BLOCK-sized containers: a flat form whose
        // one wrapper div holds every field would otherwise flag ALL
        // textareas as employment because a lone current_employer input
        // exists somewhere on the page.
        const controls = node.querySelectorAll("input, select, textarea");
        if (controls.length <= 12) {
          for (const sib of node.querySelectorAll("input[name], input[id], select[name], select[id]")) {
            if (sib !== input && EMP_BLOCK.test(`${sib.name ?? ""} ${sib.id ?? ""}`)) return true;
          }
        }
      }
    }
    return false;
  };

  const questionTextFor = (input) => {
    if (input.id) {
      const lab = document.querySelector(`label[for="${CSS.escape(input.id)}"]`);
      if (lab?.innerText?.trim()) return lab.innerText;
    }
    const wrap = input.closest("label");
    if (wrap?.innerText?.trim()) return wrap.innerText;
    const container = input.closest("div, li, tr, fieldset");
    const q = container?.querySelector('[class*="label" i], [class*="question" i], legend');
    if (q?.innerText?.trim()) return q.innerText;
    return input.getAttribute("aria-label") ?? input.getAttribute("placeholder") ?? "";
  };

  const out = [];
  const excluded = [];
  // Telemetry: which fields the gates rejected (label+kind+reason — no values).
  const reject = (label, kind, reason) =>
    excluded.push({ label: label.slice(0, 160), kind, reason });
  let n = 0;
  const retryables = [];
  const seenRadioGroups = new Set();
  const renderedKind = (el) => (el instanceof HTMLSelectElement ? "select"
    : el instanceof HTMLTextAreaElement ? "textarea"
    : isListboxButton(el) ? "combobox"
    : el.type === "radio" ? "radio" : "text");

  for (const el of document.querySelectorAll("textarea, input, select, button")) {
    if (el.disabled || el.readOnly || !isVisible(el)) continue;
    // Buttons enter the walk for ONE shape. Every other button — submit, the
    // header's utility menus, a page's own controls — is junk, not a field.
    if (el instanceof HTMLButtonElement && !isListboxButton(el)) continue;
    const label = norm(questionTextFor(el));
    if (!label) continue;
    const k = renderedKind(el);
    // Ahead of EXCLUDE, and ahead of the per-type ladder below: declining to
    // show a consent field to the model is a policy decision, not a side
    // effect of an identity pattern that happens to overlap it, and narrowing
    // EXCLUDE later must not be able to reopen the hole. The type ladder
    // matters just as much — QUESTIONY screens plain text inputs alone, so a
    // consent question rendered as a select or a radio pair, which is how ATS
    // forms usually render one, passed every gate there was.
    if (ns.isPolicyBlocked(label)) {
      reject(label, k, "policy_blocked");
      continue;
    }
    // This is the ONLY release seam in this collector. `lastRuleReleases` is a
    // WeakSet of controls a rule REFUSED because its value did not belong on
    // that control, or because an explicitly opted-in work-auth rule had no
    // stored answer. It carries no value, so the field continues below as an
    // ordinary question. `lastRuleAttempts` is deliberately separate: those
    // controls had the RIGHT value and missed delivery, so they remain
    // retryables sent straight to guided_write with that known value. Policy
    // stays above both facts, and therefore can never be released.
    const released = ns.lastRuleReleases?.has(el) === true;
    if (!released && EXCLUDE.test(label)) {
      // EXCLUDE means "rule territory — never the model's to answer". But a
      // rule that TRIED this control and could not land it left a known value
      // behind (ns.lastRuleAttempts, per-run, in-memory). That is a RETRYABLE:
      // the write reached without the ask — it goes straight to guidedWrite
      // with the known value and is never offered to /choose. Only an
      // unanswered control qualifies; an answer already standing is the
      // user's or a prior run's.
      const attempted = ns.lastRuleAttempts?.get(label);
      const unanswered = el instanceof HTMLSelectElement ? !el.value
        : isListboxButton(el) ? listboxButtonEmpty(el)
        : el.type === "radio" ? false
        : !el.value;
      if (attempted && unanswered) {
        const qid = `${token}-${n++}`;
        el.setAttribute("data-rt-qid", qid);
        retryables.push({
          qid,
          label: label.slice(0, 300),
          kind: k === "select" ? "select" : k === "combobox" ? "combobox" : "text",
          known_value: attempted,
        });
        continue;
      }
      reject(label, k, "excluded");
      continue;
    }

    let kind = null;
    let options = null;

    if (el instanceof HTMLSelectElement) {
      if (el.value) continue; // already answered
      options = [...el.options]
        .map((o) => (o.value === "" ? null : (o.textContent ?? "").trim()))
        .filter(Boolean)
        .slice(0, 30);
      if (options.length < 2) continue;
      kind = "select";
    } else if (isListboxButton(el)) {
      // Already committed: the user's answer or a prior fill. Same as a
      // select with a value — not remainder.
      if (!listboxButtonEmpty(el)) continue;
      // Closed popovers stay closed. Options that are not already in the DOM
      // belong to the writer at write time; poking the control open would
      // drive the page during a scan.
      kind = "combobox";
    } else if (el instanceof HTMLTextAreaElement) {
      if (el.value) continue;
      if (inEmploymentBlock(el)) continue;
      kind = "textarea";
    } else if (el.type === "radio") {
      if (!el.name || seenRadioGroups.has(el.name)) continue;
      seenRadioGroups.add(el.name);
      const group = [...document.querySelectorAll(
        `input[type="radio"][name="${CSS.escape(el.name)}"]`)];
      if (group.some((r) => r.checked)) continue; // already answered
      options = group.map((r) => norm(questionTextFor(r)).slice(0, 80)).filter(Boolean);
      if (options.length < 2) continue;
      kind = "radio";
      // The group's question lives in the legend/container, not the option
      // label wrapping this radio — re-derive and re-screen it.
      const legend = el.closest("fieldset")?.querySelector("legend");
      const container = el.closest("fieldset, div, li, tr");
      const q = container?.querySelector('[class*="label" i], [class*="question" i]');
      const groupLabel = norm(legend?.innerText ?? q?.innerText ?? "") || label;
      // Re-screened on the same ladder, policy first. A button's own label is
      // "Yes" — it has nothing in it to block — so on a grouped consent
      // question the legend is the ONLY string carrying the thing we refuse to
      // answer, and it is also the string that would be sent to the model.
      if (ns.isPolicyBlocked(groupLabel)) {
        reject(groupLabel, "radio", "policy_blocked");
        continue;
      }
      const groupReleased = released || group.some(
        (radio) => ns.lastRuleReleases?.has(radio) === true);
      if (!groupReleased && EXCLUDE.test(groupLabel)) {
        reject(groupLabel, "radio", "excluded");
        continue;
      }
      const qid = `${token}-${n++}`;
      el.setAttribute("data-rt-qid", qid);
      out.push({ qid, label: groupLabel.slice(0, 300), kind, options });
      continue;
    } else if (released && ns.isCombobox(el)) {
      // A released input-combobox has already been opened by the rule pass.
      // It is value-free here, like a closed listbox button; guidedWrite will
      // reopen its real options if /choose finds an answer.
      if (el.value) continue;
      kind = "combobox";
    } else if (el.type === "text" || !el.getAttribute("type")) {
      if (el.value) continue;
      if (ns.isCombobox(el)) continue;
      if (!ns.QUESTIONY.test(label)) { reject(label, "text", "not_questiony"); continue; }
      kind = "text";
    } else {
      continue;
    }

    const qid = `${token}-${n++}`;
    el.setAttribute("data-rt-qid", qid);
    out.push({ qid, label: label.slice(0, 300), kind, options });
  }
  // host: this frame's own hostname, so iframe-hosted ATS forms (Greenhouse
  // embeds) attribute AI observations truthfully, matching the profile path.
  return { questions: out, excluded, retryables, host: location.hostname };
}
// Historical sentinel retained for source-level diagnostics; the harness now
// executes this module's published function directly.
// ---- end collectOpenQuestions ----


/* MOVED at Task 12 to `shared/choose.js`: routeOpenQuestions,
 * chunkChooseFields + CHOOSE_BATCH_SIZE, requestChoose, and
 * buildRestFillObservations. All four are pure, all four are read by
 * `shared/guided-run.js`, and a panel document cannot load this file — see the
 * header.
 *
 * `createArmedDebouncer` was the one that STAYED, on the grounds that it
 * belonged to the floating card's stage observer and no panel had one. R-C
 * deleted the card, which left the function with no caller at all, so it went
 * with it rather than sitting here as a published export nothing reads. The
 * panel's Fill stage is user-driven — there is no mutation burst to coalesce,
 * because nothing starts a run except a click. */


/** Resolve tagged controls in THIS frame and hand them to Lane S's writer.
 * A missing qid is skipped; a missing writer degrades to no results. */
async function applyGuidedChoices(pairs) {
  if (typeof ns.guidedWrite !== "function") return [];
  const items = [];
  for (const pair of pairs ?? []) {
    const el = document.querySelector(`[data-rt-qid="${CSS.escape(pair.qid)}"]`);
    if (!el) continue;
    items.push({
      qid: pair.qid,
      el,
      kind: pair.kind,
      answer: pair.answer,
      knownValue: pair.knownValue,
    });
  }
  if (!items.length) return [];
  return ns.guidedWrite(items);
}
// ---- end applyGuidedChoices ----


/** Runs IN THE PAGE. Writes AI answers back into their tagged fields —
 * matching the answer to an option for selects and radio groups. */
async function fillAnswersByQid(pairs) {
  const norm = (s) => (s ?? "").toLowerCase().replace(/\s+/g, " ").trim();
  // Inline copy of `ns.decisions.sanitizeAnswer` (shared/decisions.js since
  // Task 14). It STAYS a copy for the commit ladder's reason, not by oversight:
  // this
  // function is INJECTED into the page, where the namespace does not exist, so
  // it has to be self-contained. Fix both or neither.
  const sanitize = (text) => String(text ?? "")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/`{1,3}([^`]*)`{1,3}/g, "$1")
    .replace(/^\s*(?:[-*•]|\d+[.)])\s+/gm, "")
    .replace(/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/gm, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  // Inline copy of fillFormFromProfile's `visitControl`/`leaveControl` — the
  // reasoning is there in full, and it STAYS a copy for `sanitize`'s reason:
  // this function is injected into the page, where the namespace does not
  // exist. DELIBERATELY OUTSIDE the guarded span below: that regex captures
  // everything between `setNativeValue` and `commitValue`, and this pair sits
  // above it in both copies so the ladder test compares the same three blocks
  // it always did rather than silently acquiring two more.
  const visitControl = (el) => el?.focus?.({ preventScroll: true });
  const leaveControl = (el) => { if (el?.isConnected) el.blur(); };
  const clickControl = (el) => { visitControl(el); el.click(); leaveControl(el); };
  // Inline copy of autofill.js's `stillChecked` — see it for the reasoning,
  // and `sanitize` above for why this file carries copies at all.
  const stillChecked = (el) => el?.isConnected === true && el.checked === true;
  // Inline copy of fillFormFromProfile's setNativeValue + commit ladder — see
  // the reasoning there. All three blocks are kept identical by
  // test_both_copies_of_the_commit_ladder_stay_identical; fix both or neither.
  const setNativeValue = (input, value) => {
    const proto = input instanceof HTMLTextAreaElement
      ? window.HTMLTextAreaElement.prototype
      : input instanceof HTMLSelectElement
        ? window.HTMLSelectElement.prototype
        : window.HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
    if (setter) setter.call(input, value);
    else input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  };
  const sameIgnoringFormat = (actual, wrote) => {
    const strip = (s) => String(s).normalize("NFKD").replace(/\p{M}/gu, "")
      .toLowerCase().replace(/[^a-z0-9]/g, "");
    const left = strip(actual);
    return left !== "" && left === strip(wrote);
  };

  const COMMIT_OK = new Set(["filled", "filled_normalized"]);

  const valueHolds = (input, value) => new Promise((resolve) => {
    let samples = 0;
    let settled = false;
    const timers = [];
    const hidden = document.visibilityState === "hidden";
    const settle = (outcome) => {
      if (settled) return;
      settled = true;
      for (const timer of timers) clearTimeout(timer);
      resolve(outcome);
    };
    const check = (last) => {
      if (!input.isConnected) return settle("not_stuck");
      if (input.value !== value) {
        return settle(sameIgnoringFormat(input.value, value)
          ? "filled_normalized"
          : "not_stuck");
      }
      samples += 1;
      if (!hidden && samples >= 2) return settle("filled");
      if (last) return settle("filled_unverified");
    };
    [50, 150, 400, 1000].forEach((delay, index, delays) => {
      timers.push(setTimeout(() => check(index === delays.length - 1), delay));
    });
  });
  const commitValue = async (input, value, { blur = true } = {}) => {
    input.focus({ preventScroll: true });
    setNativeValue(input, value);
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Unidentified", bubbles: true }));
    input.dispatchEvent(new KeyboardEvent("keyup", { key: "Unidentified", bubbles: true }));
    // Kept identical to the profile writer's copy (see its comment for the
    // Workday split-date measurement); this path writes no date sections yet.
    if (blur) input.blur();
    return valueHolds(input, value);
  };
  // The prompt asks for exactly one option, so exact/containment match is enough.
  const optionMatches = (optionText, answer) => {
    const o = norm(optionText);
    const a = norm(answer);
    return !!o && !!a && (o === a || o.includes(a) || a.includes(o));
  };

  const filled = [];
  for (const { qid, answer, kind } of pairs) {
    const clean = sanitize(answer);
    const el = document.querySelector(`[data-rt-qid="${CSS.escape(qid)}"]`);
    if (!el) continue;
    if (kind === "select") {
      const opt = [...el.options].find((o) =>
        o.value !== "" && optionMatches(o.textContent ?? "", clean));
      if (!opt) continue;
      visitControl(el); // see `visitControl` — a set value is not a visit
      setNativeValue(el, opt.value);
      leaveControl(el);
      filled.push(qid);
    } else if (kind === "radio") {
      const group = el.name
        ? [...document.querySelectorAll(`input[type="radio"][name="${CSS.escape(el.name)}"]`)]
        : [el];
      const hit = group.find((r) => {
        const lab = r.closest("label") ?? (r.id
          ? document.querySelector(`label[for="${CSS.escape(r.id)}"]`) : null);
        return optionMatches(lab?.innerText ?? "", clean);
      });
      if (!hit) continue;
      clickControl(hit); // see `visitControl` — click() moves no focus
      // The READBACK the other two limbs already had: this one pushed the qid
      // on the strength of having clicked, so a group the page re-rendered
      // under the blur was reported answered. See `stillChecked`.
      if (stillChecked(hit)) filled.push(qid);
    } else {
      // Controlled inputs can reject the write — only a value that stuck
      // counts as answered (profile-fill's not_stuck parity for the AI path).
      // Membership in COMMIT_OK, not truthiness: commitValue resolves an
      // outcome string now, and every one of them is truthy.
      if (COMMIT_OK.has(await commitValue(el, clean))) filled.push(qid);
    }
  }
  return filled;
}
// Historical sentinel retained for source-level diagnostics; the harness now
// executes this module's published function directly.
// ---- end fillAnswersByQid ----


  ns.collectOpenQuestions = collectOpenQuestions;
  ns.applyGuidedChoices = applyGuidedChoices;
  ns.fillAnswersByQid = fillAnswersByQid;
})();
