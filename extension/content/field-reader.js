/* Maestro CS Companion — the field reader: ONE answer to "what is this field
 * asking", with the source it came from. Strength order:
 *   label-for → label-wrap → labelledby (every id) → aria-label → legend → nearby
 * A Workday dropdown's aria-label is "<question> <value> Required"; on its
 * Application Questions step the question part is EMPTY and the real question
 * is the fieldset legend — so the button's own value and "Required" are
 * stripped, and an aria-label left empty falls through to the legend.
 * Zero-width characters are whitespace; ids resolve in the element's own root.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const ZERO_WIDTH = /[​-‍⁠﻿‎‏]/g;
  const clean = (s) => String(s ?? "").replace(ZERO_WIDTH, " ").replace(/\s+/g, " ").trim();
  const STAR = /\s*\*+\s*$/;
  const text = (el) => clean(el?.innerText || el?.textContent);
  const rootOf = (el) => (el?.getRootNode?.() instanceof ShadowRoot ? el.getRootNode() : document);
  const byId = (el, id) => rootOf(el).getElementById?.(id) ?? document.getElementById(id);
  const isPopupButton = (el) =>
    el?.tagName === "BUTTON" && /^(listbox|true|menu|dialog)$/.test(el.getAttribute("aria-haspopup") ?? "");
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
    ["aria-label", (el) => {
      let label = clean(el.getAttribute("aria-label"));
      if (label && isPopupButton(el)) {
        const own = text(el);
        if (own) label = clean(label.split(own).join(" "));
        label = clean(label.replace(/\brequired\b/gi, " "));
      }
      return label;
    }],
    ["legend", (el) => text(el.closest("fieldset")?.querySelector("legend"))],
    ["nearby", (el) => {
      let node = el.parentElement;
      for (let depth = 0; node && depth < 3; depth += 1, node = node.parentElement) {
        const cand = node.querySelector('[class*="label" i], [class*="question" i]');
        if (cand && !cand.contains(el) && !cand.querySelector("input, select, textarea, button")) {
          const t = text(cand);
          if (t) return t;
        }
      }
      return "";
    }],
  ];
  const HEADING = "h1, h2, h3, h4, h5, [role=heading]";
  const sectionOf = (el) => {
    for (let node = el.parentElement; node; node = node.parentElement) {
      const heads = [...node.querySelectorAll(HEADING)]
        .filter((h) => !h.contains(el) && (h.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING));
      if (heads.length) return text(heads.at(-1));
    }
    return "";
  };

  ns.readFieldText = clean;
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
    const m = /(\d+)\s*$/.exec(section);
    return {
      question: clean(question.replace(STAR, "")),
      source,
      help: fromIds(el, "aria-describedby"),
      section,
      repeatIndex: m ? Math.max(0, Number(m[1]) - 1) : 0,
      required: Boolean(el.required) || el.getAttribute("aria-required") === "true" || starred,
    };
  };
})();
