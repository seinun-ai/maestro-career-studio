/* Maestro CS Companion — the field reader: ONE answer to "what is this field
 * asking", with the source it came from. Strength order:
 *   label-for → label-wrap → labelledby (every id) → aria-label → legend → nearby
 * A Workday dropdown's aria-label is "<question> <value> Required"; on its
 * Application Questions step the question part is EMPTY and the real question
 * is the fieldset legend — so the button's own value and "Required" are
 * stripped from the END only (a question may contain either word), a stripped
 * "Required" makes the field required, and an aria-label left empty falls
 * through to the legend.
 * Zero-width characters are whitespace; ids resolve in the element's own root.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  // LOAD ONCE. panel_prepare re-injects every content script into the SAME
  // isolated world; a second run would reset this module's state (see
  // INTERNALS.md, "A tab that was already open…").
  const loaded = (ns.loadedOnce ??= new Set());
  if (loaded.has("content/field-reader.js")) return;
  loaded.add("content/field-reader.js");
  const ZERO_WIDTH = /[​-‍⁠﻿‎‏]/g;
  const clean = (s) => String(s ?? "").replace(ZERO_WIDTH, " ").replace(/\s+/g, " ").trim();
  const STAR = /\s*\*+\s*$/;
  const text = (el) => clean(el?.innerText || el?.textContent);
  const rootOf = (el) => (el?.getRootNode?.() instanceof ShadowRoot ? el.getRootNode() : document);
  const byId = (el, id) => rootOf(el).getElementById?.(id) ?? document.getElementById(id);
  const isPopupButton = (el) =>
    el?.tagName === "BUTTON" && /^(listbox|true|menu|dialog)$/.test(el.getAttribute("aria-haspopup") ?? "");
  const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  // "<question> <value> Required" → {label: "<question>", required: true}.
  // The value is matched without trailing glyphs ("United States▾"); when it
  // is not in the label at all, a bare trailing "Required" is still stripped.
  const BARE_REQUIRED = /(?:^|\s+)(required)\s*$/i;
  // A popup's "choose something" text is never a question: ns.isPlaceholderText
  // (shared/policy.js, the ONE definition).
  const popupLabel = (el) => {
    const label = clean(el.getAttribute("aria-label"));
    if (!label || !isPopupButton(el)) return { label, required: false };
    const own = clean(text(el).replace(/[\p{So}\s]+$/u, ""));
    const m = (own && new RegExp(`(?:^|\\s+)${escapeRe(own)}\\s*(required)?\\s*$`, "i").exec(label))
      || BARE_REQUIRED.exec(label);
    const left = m ? clean(label.slice(0, m.index)) : label;
    // A widget that never updates its label after a pick leaves its placeholder
    // here ("<placeholder> Required" over the value): that is no question, so
    // the reader falls through to the legend.
    return { label: ns.isPlaceholderText(left) ? "" : left, required: Boolean(m?.[1]) };
  };
  // What counts as ANOTHER field's control; fill-base reads the same rule
  // (ns.fieldControls) for its field box. A same-name radio/checkbox is the
  // same field; a plain button (a Clear beside a box) is no field.
  const CONTROL = 'input:not([type="hidden"]), select, textarea, button[aria-haspopup], [role="combobox"], [contenteditable="true"]';
  const isChoice = (el) => /^(radio|checkbox)$/.test(el.type);
  const otherControl = (c, el) => c !== el && !el.contains(c)
    && !(isChoice(el) && el.name && isChoice(c) && c.name === el.name);
  ns.fieldControls = { CONTROL, isChoice, otherControl };
  const precedes = (a, b) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
  const withoutControls = (node) => {
    const copy = node.cloneNode(true);
    copy.querySelectorAll("input, select, textarea, button, [role=listbox]").forEach((n) => n.remove());
    return clean(copy.textContent);
  };
  const fromIds = (el, attr) => clean((el.getAttribute(attr) ?? "").split(/\s+/).filter(Boolean)
    .map((id) => text(byId(el, id))).join(" "));
  const SOURCES = [
    ["label-for", (el) => {
      const lab = el.id && rootOf(el).querySelector?.(`label[for="${CSS.escape(el.id)}"]`);
      return lab ? withoutControls(lab) : "";
    }],
    ["label-wrap", (el) => (el.closest("label") ? withoutControls(el.closest("label")) : "")],
    ["labelledby", (el) => fromIds(el, "aria-labelledby")],
    ["aria-label", (el) => popupLabel(el).label],
    ["legend", (el) => text(el.closest("fieldset")?.querySelector("legend"))],
    // The closest label-like node BEFORE the field with no other field between
    // them; at a level holding only this field, else the first one AFTER it (a
    // checkbox's trailing label). Climbing stops at an ancestor holding another
    // field.
    ["nearby", (el) => {
      let node = el.parentElement;
      for (let depth = 0; node && depth < 3; depth += 1, node = node.parentElement) {
        const others = [...node.querySelectorAll(CONTROL)].filter((c) => otherControl(c, el));
        const cands = [...node.querySelectorAll('[class*="label" i], [class*="question" i]')]
          .filter((c) => !c.contains(el) && !c.querySelector("input, select, textarea, button") && text(c));
        const before = cands.filter((c) => precedes(c, el)).at(-1);
        if (before && !others.some((c) => precedes(before, c) && precedes(c, el))) return text(before);
        if (others.length) break;
        const after = cands.find((c) => precedes(el, c));
        if (after) return text(after);
      }
      return "";
    }],
  ];
  // A field's SECTION comes from h1–h5: an <h6> is a sub-label inside an
  // entry ("Dates" in "Work Experience 2"), and taking it would drop the
  // entry's number. ANY_HEADING (h6 too) is for content/sections.js alone.
  const HEADING = "h1, h2, h3, h4, h5, [role=heading]";
  const ANY_HEADING = "h1, h2, h3, h4, h5, h6, [role=heading]";
  // "Work Experience 2" is the second repeat; "Step 2 of 4" / "Page 2" is not.
  // ONE rule for what a numbered title is: `ns.repeatOf` (also content/
  // sections.js); shared/fill-loop.js keeps a mirror of these two patterns,
  // pinned identical by test_the_loop_reads_repeated_titles_by_the_field_readers_rule.
  const REPEAT = /(\p{L}+)\s+(\d+)$/u;
  const NOT_REPEAT = /^(of|step|page)$/i;
  // "Work Experience 2" → { base: "Work Experience", n: 2 }; else null.
  const repeatOf = (title) => {
    const t = clean(title);
    const m = REPEAT.exec(t);
    if (!m || NOT_REPEAT.test(m[1])) return null;
    return { base: clean(t.slice(0, m.index + m[1].length)), n: Number(m[2]) };
  };
  const repeatIndex = (section) => {
    const r = repeatOf(section);
    return r ? Math.max(0, r.n - 1) : 0;
  };
  const sectionOf = (el) => {
    for (let node = el.parentElement; node; node = node.parentElement) {
      const heads = [...node.querySelectorAll(HEADING)]
        .filter((h) => !h.contains(el) && (h.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING));
      if (heads.length) return text(heads.at(-1));
    }
    return "";
  };

  ns.readFieldText = clean;
  ns.repeatOf = repeatOf;
  ns.ANY_HEADING = ANY_HEADING;
  ns.byIdIn = byId; // an id, resolved in the element's own root
  ns.readField = (el) => {
    let question = "";
    let source = null;
    for (const [name, read] of SOURCES) {
      try {
        question = read(el);
      } catch {
        question = "";
      }
      if (question) {
        source = name;
        break;
      }
    }
    const starred = STAR.test(question);
    const section = sectionOf(el);
    return {
      question: clean(question.replace(STAR, "")),
      source,
      help: fromIds(el, "aria-describedby"),
      section,
      repeatIndex: repeatIndex(section),
      required: Boolean(el.required) || el.getAttribute("aria-required") === "true" || starred
        || popupLabel(el).required,
    };
  };
})();
