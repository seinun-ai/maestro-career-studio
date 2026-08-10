/* Maestro CS Companion — open-question collection and answer injection.
 *
 * Shared content-script module. These functions run in the content-script
 * world; the commit ladder inside fillAnswersByQid stays self-contained because
 * it is deliberately identity-pinned against the profile fill copy.
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
  const QUESTIONY =
    /\?|why\b|describe|tell (us|me)|what\b|how\b|experience|interest|motivat|excite|salary|compensation|notice|referr|hear about/i;

  const isVisible = (el) =>
    !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);

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
  const seenRadioGroups = new Set();
  const renderedKind = (el) => (el instanceof HTMLSelectElement ? "select"
    : el instanceof HTMLTextAreaElement ? "textarea"
    : el.type === "radio" ? "radio" : "text");

  for (const el of document.querySelectorAll("textarea, input, select")) {
    if (el.disabled || el.readOnly || !isVisible(el)) continue;
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
    if (EXCLUDE.test(label)) {
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
      if (EXCLUDE.test(groupLabel)) { reject(groupLabel, "radio", "excluded"); continue; }
      const qid = `${token}-${n++}`;
      el.setAttribute("data-rt-qid", qid);
      out.push({ qid, label: groupLabel.slice(0, 300), kind, options });
      continue;
    } else if (el.type === "text" || !el.getAttribute("type")) {
      if (el.value) continue;
      if (el.getAttribute("role") === "combobox" || el.hasAttribute("aria-autocomplete")) continue;
      if (!QUESTIONY.test(label)) { reject(label, "text", "not_questiony"); continue; }
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
  return { questions: out, excluded, host: location.hostname };
}
// Historical sentinel retained for source-level diagnostics; the harness now
// executes this module's published function directly.
// ---- end collectOpenQuestions ----


/** Runs IN THE PAGE. Writes AI answers back into their tagged fields —
 * matching the answer to an option for selects and radio groups. */
async function fillAnswersByQid(pairs) {
  const norm = (s) => (s ?? "").toLowerCase().replace(/\s+/g, " ").trim();
  // Inline copy of panel-scope sanitizeAnswer — injected functions are self-contained.
  const sanitize = (text) => String(text ?? "")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/`{1,3}([^`]*)`{1,3}/g, "$1")
    .replace(/^\s*(?:[-*•]|\d+[.)])\s+/gm, "")
    .replace(/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/gm, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
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
    let frames = 0;
    const timer = setTimeout(() => resolve("not_stuck"), 1000);
    const settle = (outcome) => { clearTimeout(timer); resolve(outcome); };
    const check = () => {
      if (!input.isConnected) return settle("not_stuck");
      if (input.value !== value) {
        return settle(sameIgnoringFormat(input.value, value)
          ? "filled_normalized"
          : "not_stuck");
      }
      if (++frames >= 2) return settle("filled");
      requestAnimationFrame(check);
    };
    requestAnimationFrame(check);
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
      setNativeValue(el, opt.value);
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
      hit.click();
      filled.push(qid);
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
  ns.fillAnswersByQid = fillAnswersByQid;
})();
