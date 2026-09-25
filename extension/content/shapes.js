/* Maestro CS Companion — widget shapes: recognise, group, read committed, open.
 *
 * A shape is ONLY: `match` (is this element one of mine), `groupKey` (the
 * elements that are one field share a key — radio/checkbox members, date
 * sections), `parts` (those elements), `describe` (a question that belongs to
 * the group, not the element), `read` (what is COMMITTED), `passive` (options
 * readable without touching the page), `answered`, and `open` (how a choice
 * widget shows its options: "press" or "search"). No shape acts or verifies;
 * fill-core runs one generic path over all of them.
 *
 * The committed reader is the load-bearing part: search text is never a value;
 * a single-value node, pill, chip, hidden backing input, button text or
 * checked state is.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const clean = (s) => ns.readFieldText(s);
  const TEXT_TYPES = new Set(["text", "email", "tel", "url", "number", "search"]);
  const SEARCH_BOX = '[data-uxi-widget-type="selectinput"], [data-uxi-widget-type="multiselectinput"]';
  const DATE_SECTION = /dateSection(Month|Day|Year)-input/;
  const DATE_PATTERN = /^(mm|dd|yyyy)([/.\-](mm|dd|yyyy)){1,2}$/i;
  const PLACEHOLDER = /^(select( one)?|choose( one)?|please select|--|—|-)?$/i;
  const CHIP = '[data-automation-id="selectedItem"], [class*="multi-value__label" i], [class*="multiValue" i] [class*="label" i]';
  const SINGLE = '[class*="single-value" i], [class*="singleValue" i]';
  const GROUPER = 'fieldset, [role="radiogroup"], [role="group"]';

  // A group's question is its container's (legend, labelledby, aria-label,
  // nearby); the first member's own label ("Yes") is never the question.
  const describeBy = (container) => {
    const d = container ? ns.readField(container) : null;
    return d?.question ? { question: d.question, source: d.source, required: d.required } : {};
  };

  // A search widget's box: Workday's widget wrapper, else the highest ancestor
  // (3 levels) holding no OTHER field, never <body>, <html> or a <form> — a
  // page-wide wrapper would read a neighbour's value as this one's. No such
  // ancestor: no box, and nothing but the widget itself is read.
  const box = (el) => {
    const own = el.closest(SEARCH_BOX);
    if (own) return own;
    const { CONTROL, otherControl } = ns.fieldControls;
    let found = null;
    for (let n = el.parentElement, d = 0; n && d < 3; n = n.parentElement, d += 1) {
      if (n === document.body || n === document.documentElement || n.tagName === "FORM") break;
      if ([...n.querySelectorAll(CONTROL)].some((c) => otherControl(c, el))) break;
      found = n;
    }
    return found;
  };
  // A hidden backing input counts only when it is structurally the widget's:
  // inside Workday's widget wrapper, the element's own combobox wrapper, or a
  // react-select-style container within the box — never a form's csrf token.
  const backing = (el) => {
    const container = el.closest('[class*="container" i]');
    const root = el.closest(SEARCH_BOX) ?? el.parentElement?.closest('[role="combobox"]')
      ?? (container && box(el)?.contains(container) ? container : null);
    return root?.querySelector('input[type="hidden"]')?.value ?? "";
  };
  const chips = (el) => [...(box(el)?.querySelectorAll(CHIP) ?? [])].map((c) => clean(c.textContent)).filter(Boolean);

  // Radio/checkbox members: same name in the same form (or root), else the
  // nearest grouping container; a nameless one outside any container is alone.
  const members = (el) => {
    if (el.name) {
      return [...(el.form ?? el.getRootNode()).querySelectorAll(`input[type="${el.type}"][name="${CSS.escape(el.name)}"]`)];
    }
    const c = el.closest(GROUPER);
    return c ? [...c.querySelectorAll(`input[type="${el.type}"]`)] : [el];
  };
  const lone = (el) => el.type === "checkbox" && members(el).length < 2;
  const labelOf = (input) => ns.readField(input).question;
  // A group with no container question asks the text BEFORE its first member:
  // the nearest preceding visible sibling (climbing at most 4 levels) that is
  // not a member's label, stopping at another field's control.
  const STAR = /\s*\*+\s*$/;
  const precedingQuestion = (el, ms) => {
    const { CONTROL } = ns.fieldControls;
    const memberLabels = new Set(ms.flatMap((m) => [...(m.labels ?? [])]));
    let node = ms[0].closest("label") ?? ms[0];
    for (let d = 0; node && d < 4; d += 1, node = node.parentElement) {
      if (node === document.body || node === document.documentElement) break;
      for (let s = node.previousElementSibling; s; s = s.previousElementSibling) {
        if (s.matches("script, style, template") || !ns.fillBase.visible(s)) continue;
        const controls = [...(s.matches(CONTROL) ? [s] : []), ...s.querySelectorAll(CONTROL)];
        if (controls.some((c) => !ms.includes(c))) return null;
        if (controls.length || memberLabels.has(s)) continue;
        const t = clean(s.innerText || s.textContent);
        if (t) return { question: clean(t.replace(STAR, "")), source: "nearby", required: STAR.test(t) };
      }
    }
    return null;
  };
  // Never a member's own option label ("Yes"): no question beats a wrong one.
  const groupQuestion = (el) => {
    const ms = members(el);
    const options = new Set(ms.map(labelOf));
    const fromContainer = describeBy(el.closest(GROUPER));
    if (fromContainer.question && !options.has(fromContainer.question)) return fromContainer;
    const before = precedingQuestion(el, ms);
    if (before?.question && !options.has(before.question)) return before;
    return { question: "", source: null };
  };
  const realOptions = (el) => [...el.options].filter((o, i) => !o.disabled && clean(o.text)
    && !(i === 0 && (o.value === "" || /^(select|choose|please select|--|—)/i.test(clean(o.text)))));

  const dateKind = (el) => {
    if (DATE_SECTION.test(el.getAttribute("data-automation-id") ?? "")) return "sections";
    if (el.type === "month" || el.type === "date") return el.type;
    if (DATE_PATTERN.test(el.getAttribute("placeholder") ?? "")) return "pattern";
    return null;
  };
  const dateWrapper = (el) => el.closest('[data-automation-id="dateInputWrapper"]') ?? el.parentElement;
  const dateSections = (el) => [...dateWrapper(el).querySelectorAll('input[data-automation-id^="dateSection"]')];
  const partOf = (s) => DATE_SECTION.exec(s.getAttribute("data-automation-id") ?? "")?.[1]?.toLowerCase();

  // An editing host (not an editable node inside one).
  const editingHost = (el) => el.isContentEditable && !(el.parentElement?.isContentEditable)
    && !(el instanceof HTMLInputElement) && !(el instanceof HTMLTextAreaElement);
  const searchLike = (el) => el.getAttribute("role") === "combobox" || el.hasAttribute("aria-autocomplete")
    || el.closest(SEARCH_BOX) !== null || el.parentElement?.closest('[role="combobox"]') != null;

  const SHAPES = [
    {
      name: "date", kind: "text",
      match: (el) => el instanceof HTMLInputElement && dateKind(el) !== null,
      groupKey: (el) => (dateKind(el) === "sections" ? dateWrapper(el) : null),
      parts: (el) => (dateKind(el) === "sections" ? dateSections(el) : [el]),
      describe: (el) => (dateKind(el) === "sections" ? describeBy(dateWrapper(el)) : {}),
      read(el) {
        if (dateKind(el) !== "sections") return el.value;
        const got = Object.fromEntries(dateSections(el).map((s) => [partOf(s), s.value]));
        return [got.year, got.month, got.day].filter(Boolean).join("-");
      },
      dateKind, dateSections, partOf,
    },
    {
      // Inputs, textareas and contenteditable editing hosts (rich-text boxes);
      // typeText types into all three.
      name: "text", kind: "text",
      match: (el) => el instanceof HTMLTextAreaElement
        || (el instanceof HTMLInputElement && TEXT_TYPES.has(el.type) && !searchLike(el))
        || (el instanceof HTMLElement && editingHost(el)),
      read: (el) => (editingHost(el) ? clean(el.innerText ?? el.textContent) : el.value),
    },
    {
      name: "select", kind: "choice",
      match: (el) => el instanceof HTMLSelectElement,
      multi: (el) => el.multiple,
      passive: (el) => ({
        options: realOptions(el).map((o, i) => ({ oid: `o${i + 1}`, text: clean(o.text), selected: o.selected })),
        complete: true,
      }),
      read: (el) => {
        const chosen = realOptions(el).filter((o) => o.selected).map((o) => clean(o.text));
        return el.multiple ? chosen : (chosen[0] ?? "");
      },
      realOptions,
    },
    {
      // A radio set, a checkbox set, or ONE checkbox (a Yes/No question).
      name: "group", kind: "choice",
      match: (el) => el instanceof HTMLInputElement && (el.type === "radio" || el.type === "checkbox"),
      multi: (el) => el.type === "checkbox" && !lone(el),
      groupKey: (el) => (lone(el) ? null : members(el)[0]),
      parts: (el) => (lone(el) ? [el] : members(el)),
      describe: (el) => (lone(el) ? {} : groupQuestion(el)),
      passive: (el) => (lone(el)
        ? { options: [{ oid: "yes", text: "Yes", selected: el.checked }, { oid: "no", text: "No", selected: !el.checked }], complete: true }
        : { options: members(el).map((m, i) => ({ oid: `o${i + 1}`, text: labelOf(m), selected: m.checked })), complete: true }),
      // An unchecked lone checkbox reads "No" but was never answered; a
      // checkbox set is never finished just because one box is ticked.
      answered: (el) => (lone(el) ? el.checked : el.type === "radio" && members(el).some((m) => m.checked)),
      read: (el) => {
        if (lone(el)) return el.checked ? "Yes" : "No";
        const on = members(el).filter((m) => m.checked).map(labelOf);
        return el.type === "radio" ? (on[0] ?? "") : on;
      },
      members, lone, labelOf,
    },
    {
      // A text box that searches: Workday selectinput, react-select, any
      // input combobox. What was typed is never the value.
      name: "search", kind: "choice", open: "search",
      match: (el) => el instanceof HTMLInputElement && TEXT_TYPES.has(el.type) && searchLike(el),
      multi: (el) => el.closest('[data-uxi-widget-type="multiselectinput"]') !== null
        || /is-multi/i.test(box(el)?.className ?? "") || box(el)?.querySelector('[class*="is-multi" i]') != null,
      read(el) {
        if (this.multi(el)) return chips(el);
        const single = box(el)?.querySelector(SINGLE);
        if (single) return clean(single.textContent);
        if (chips(el)[0]) return chips(el)[0];
        return backing(el);
      },
    },
    {
      // A button (or non-input combobox) that opens a list. An ARIA 1.1
      // combobox wrapping its own text input is the input's field, not this.
      name: "popup", kind: "choice", open: "press",
      match: (el) => (el.tagName === "BUTTON" && /^(listbox|true|menu|dialog)$/.test(el.getAttribute("aria-haspopup") ?? ""))
        || (el.getAttribute("role") === "combobox" && el.tagName !== "INPUT"
          && !el.querySelector('input:not([type="hidden"])')),
      read: (el) => {
        const t = clean(el.innerText || el.textContent);
        return PLACEHOLDER.test(t) ? "" : t;
      },
    },
  ];

  // A control no shape recognises: LISTED so the panel can name it (and the
  // user can jump to it), never acted on. ARIA radios/checkboxes in one group
  // are one field.
  const CHECKABLE = '[role="radio"], [role="checkbox"], [role="switch"]';
  const ariaGroup = (el) => (el.matches(CHECKABLE) ? el.parentElement?.closest('[role="radiogroup"], [role="group"]') : null);
  const ariaMembers = (el) => (ariaGroup(el) ? [...ariaGroup(el).querySelectorAll(CHECKABLE)] : [el]);
  const UNKNOWN = {
    name: "unknown", kind: "unknown",
    groupKey: (el) => ariaGroup(el) ?? null,
    parts: ariaMembers,
    describe: (el) => (ariaGroup(el) ? describeBy(ariaGroup(el)) : {}),
    // Never answered: a default aria-valuenow or a pre-set state is not the
    // user's answer, and nothing here can tell them apart.
    answered: () => false,
    read: (el) => {
      if (el.matches(CHECKABLE)) {
        return ariaMembers(el).filter((m) => m.getAttribute("aria-checked") === "true")
          .map((m) => clean(m.textContent)).join(", ");
      }
      return clean(el.getAttribute("aria-valuetext") ?? el.getAttribute("aria-valuenow") ?? el.value ?? el.textContent);
    },
  };

  ns.shapes = {
    list: SHAPES,
    unknown: UNKNOWN,
    of: (el) => SHAPES.find((s) => s.match(el)) ?? null,
    byName: (n) => (n === "unknown" ? UNKNOWN : SHAPES.find((s) => s.name === n)),
  };
})();
