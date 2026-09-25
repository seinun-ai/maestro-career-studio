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
 * checked state is. The one exception is a free-text autocomplete (a search
 * box with no select structure at all): what its input holds IS the answer.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const clean = (s) => ns.readFieldText(s);
  const TEXT_TYPES = new Set(["text", "email", "tel", "url", "number", "search"]);
  const SEARCH_BOX = '[data-uxi-widget-type="selectinput"], [data-uxi-widget-type="multiselectinput"]';
  const DATE_SECTION = /dateSection(Month|Day|Year)-input/;
  const SECTION = 'input[data-automation-id^="dateSection"]';
  const DATE_PATTERN = /^(mm|dd|yyyy)([/.\-](mm|dd|yyyy)){1,2}$/i;
  const HASPOPUP = /^(listbox|true|menu|dialog)$/;
  // "Select", "Select One", "Select an option", "-- Select --", "Please
  // choose", "Choose one…" — and nothing at all. Trailing glyphs (▾) go first.
  const PLACEHOLDER = new RegExp("^[-–—\\s]*(?:(?:please\\s+)?(?:select|choose|pick)"
    + "(?:\\s+(?:an?\\s+option|one(?:\\s+or\\s+more)?|an?\\s+answer|an?\\s+item|a\\s+value|all\\s+that\\s+apply))?"
    + "\\s*(?:\\.{2,}|…)?)?[-–—\\s]*$", "i");
  const GLYPHS = /[\p{So}\s]+$/u;
  const CHIP = '[data-automation-id="selectedItem"], [class*="multi-value__label" i], [class*="multiValue" i] [class*="label" i]';
  const SINGLE = '[class*="single-value" i], [class*="singleValue" i], [class*="selection-item" i]';
  const SELECT_STRUCTURE = `${SINGLE}, ${CHIP}, [class*="placeholder" i], [class*="value-container" i], [class*="valueContainer" i]`;
  const GROUPER = 'fieldset, [role="radiogroup"], [role="group"]';
  const STAR = /\s*\*+\s*$/;
  const edge = (n) => n === document.body || n === document.documentElement || n.tagName === "FORM";

  // Per-pass memo (the inventory wraps one list() in `pass`): readField and
  // members are asked for the same element many times in one pass.
  let cache = null;
  const memo = (kind, el, fn) => {
    if (!cache) return fn();
    const m = cache[kind];
    if (!m.has(el)) m.set(el, fn());
    return m.get(el);
  };
  const readField = (el) => memo("field", el, () => ns.readField(el));
  const pass = (fn) => {
    cache = { field: new Map(), members: new Map() };
    try {
      return fn();
    } finally {
      cache = null;
    }
  };

  // A group's question is its container's (legend, labelledby, aria-label,
  // nearby); the first member's own label ("Yes") is never the question.
  const describeBy = (container) => {
    const d = container ? readField(container) : null;
    return d?.question ? { question: d.question, source: d.source, required: d.required } : {};
  };

  const searchLike = (el) => el.getAttribute("role") === "combobox"
    || (el.hasAttribute("aria-autocomplete") && el.getAttribute("aria-autocomplete") !== "none")
    || el.closest(SEARCH_BOX) !== null || el.parentElement?.closest('[role="combobox"]') != null;
  // A read-only input that opens a list when pressed (antd, many design systems).
  const pressInput = (el) => el instanceof HTMLInputElement && el.readOnly
    && (el.getAttribute("role") === "combobox" || HASPOPUP.test(el.getAttribute("aria-haspopup") ?? ""));
  const buttonLike = (el) => el.tagName === "BUTTON" || el.getAttribute("role") === "button";
  // A toggle button beside a search input (Headless UI, Downshift) is part of
  // the input's field: same aria-controls, or the only other control in the
  // nearest ancestor that holds one.
  const companionSearch = (btn) => {
    if (!buttonLike(btn)) return null;
    const search = (c) => c instanceof HTMLInputElement && TEXT_TYPES.has(c.type) && !c.readOnly && searchLike(c);
    const ctl = btn.getAttribute("aria-controls");
    if (ctl) {
      const twin = btn.getRootNode().querySelector?.(`input[aria-controls="${CSS.escape(ctl)}"]`);
      if (twin && search(twin)) return twin;
    }
    const { CONTROL } = ns.fieldControls;
    for (let n = btn.parentElement, d = 0; n && d < 2 && !edge(n); n = n.parentElement, d += 1) {
      const others = [...n.querySelectorAll(CONTROL)].filter((c) => c !== btn && !btn.contains(c));
      if (others.length) return others.length === 1 && search(others[0]) ? others[0] : null;
    }
    return null;
  };

  // A search widget's box: Workday's widget wrapper, else the highest ancestor
  // (3 levels) holding no OTHER field (its own toggle button is not one), never
  // <body>, <html> or a <form> — a page-wide wrapper would read a neighbour's
  // value as this one's. No such ancestor: no box.
  const box = (el) => {
    const own = el.closest(SEARCH_BOX);
    if (own) return own;
    const { CONTROL, otherControl } = ns.fieldControls;
    let found = null;
    for (let n = el.parentElement, d = 0; n && d < 3 && !edge(n); n = n.parentElement, d += 1) {
      if ([...n.querySelectorAll(CONTROL)].some((c) => otherControl(c, el) && companionSearch(c) !== el)) break;
      found = n;
    }
    return found;
  };
  // The widget's own root, when it has one: Workday's wrapper, the element's
  // own combobox wrapper, or a react-select-style container within the box.
  const widgetRoot = (el) => {
    const container = el.closest('[class*="container" i]');
    return el.closest(SEARCH_BOX) ?? el.parentElement?.closest('[role="combobox"]')
      ?? (container && box(el)?.contains(container) ? container : null);
  };
  // A hidden backing input counts only inside the widget's root — never a
  // form's csrf token.
  const backing = (el) => widgetRoot(el)?.querySelector('input[type="hidden"]')?.value ?? "";
  const chips = (el) => [...(box(el)?.querySelectorAll(CHIP) ?? [])].map((c) => clean(c.textContent)).filter(Boolean);
  const searchMulti = (el) => el.closest('[data-uxi-widget-type="multiselectinput"]') !== null
    || /is-multi/i.test(box(el)?.className ?? "") || box(el)?.querySelector('[class*="is-multi" i]') != null;
  // A select-style widget shows its value somewhere other than the input.
  const selectStructure = (el) => Boolean(widgetRoot(el) || box(el)?.querySelector(SELECT_STRUCTURE));
  const readSearch = (el) => {
    if (searchMulti(el)) return chips(el);
    if (!selectStructure(el)) return el.value; // free-text autocomplete ("Location (City)")
    const single = box(el)?.querySelector(SINGLE);
    if (single) return clean(single.textContent);
    if (chips(el)[0]) return chips(el)[0];
    return backing(el);
  };

  // Radio/checkbox members: same name in the same form (or root), else the
  // nearest grouping container; a nameless one outside any container is alone.
  const members = (el) => memo("members", el, () => {
    if (el.name) {
      return [...(el.form ?? el.getRootNode()).querySelectorAll(`input[type="${el.type}"][name="${CSS.escape(el.name)}"]`)];
    }
    const c = el.closest(GROUPER);
    return c ? [...c.querySelectorAll(`input[type="${el.type}"]`)] : [el];
  });
  const lone = (el) => el.type === "checkbox" && members(el).length < 2;
  const labelOf = (input) => readField(input).question;
  // A group with no container question asks the text BEFORE its first member:
  // the nearest preceding visible sibling (climbing at most 4 levels) that is
  // not a member's label, stopping at another field's control.
  const precedingQuestion = (ms) => {
    const { CONTROL } = ns.fieldControls;
    const memberLabels = new Set(ms.flatMap((m) => [...(m.labels ?? [])]));
    let node = ms[0].closest("label") ?? ms[0];
    for (let d = 0; node && d < 4 && !edge(node); d += 1, node = node.parentElement) {
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
    const before = precedingQuestion(ms);
    if (before?.question && !options.has(before.question)) return before;
    return { question: "", source: null };
  };
  const realOptions = (el) => [...el.options].filter((o, i) => !o.disabled && clean(o.text)
    && !(i === 0 && (o.value === "" || /^(select|choose|please select|--|—)/i.test(clean(o.text)))));

  const partOf = (s) => DATE_SECTION.exec(s.getAttribute("data-automation-id") ?? "")?.[1]?.toLowerCase();
  const dateKind = (el) => {
    if (DATE_SECTION.test(el.getAttribute("data-automation-id") ?? "")) return "sections";
    if (el.type === "month" || el.type === "date") return el.type;
    if (DATE_PATTERN.test(el.getAttribute("placeholder") ?? "")) return "pattern";
    return null;
  };
  // Sections of ONE date widget: its dateInputWrapper, else the highest
  // ancestor (4 levels) holding no other field, split into widgets in document
  // order — a part seen again starts the next widget (From M/Y, To M/Y).
  const dateScope = (el) => {
    const wrap = el.closest('[data-automation-id="dateInputWrapper"]');
    if (wrap) return wrap;
    const { CONTROL } = ns.fieldControls;
    let scope = el.parentElement;
    for (let n = el.parentElement, d = 0; n && d < 4 && !edge(n); n = n.parentElement, d += 1) {
      if ([...n.querySelectorAll(CONTROL)].some((c) => !c.matches(SECTION))) break;
      scope = n;
    }
    return scope;
  };
  const dateSections = (el) => {
    let run = [];
    const runs = [run];
    for (const s of dateScope(el).querySelectorAll(SECTION)) {
      if (run.some((r) => partOf(r) === partOf(s))) runs.push((run = []));
      run.push(s);
    }
    return runs.find((r) => r.includes(el)) ?? [el];
  };
  // The question of a date widget: its wrapper's, or the smallest ancestor
  // holding exactly its sections; else the first section's own (label-for).
  const dateQuestion = (el) => {
    const wrap = el.closest('[data-automation-id="dateInputWrapper"]');
    if (wrap) return describeBy(wrap);
    const run = dateSections(el);
    let n = run[0].parentElement;
    while (n && !edge(n) && !run.every((s) => n.contains(s))) n = n.parentElement;
    return n && !edge(n) && n.querySelectorAll(SECTION).length === run.length ? describeBy(n) : {};
  };
  const pad = (v) => (/^\d$/.test(v) ? `0${v}` : v);

  // An editing host (not an editable node inside one).
  const editingHost = (el) => el.isContentEditable && !(el.parentElement?.isContentEditable)
    && !(el instanceof HTMLInputElement) && !(el instanceof HTMLTextAreaElement);

  const SHAPES = [
    {
      name: "date", kind: "text",
      match: (el) => el instanceof HTMLInputElement && dateKind(el) !== null,
      groupKey: (el) => (dateKind(el) === "sections" ? dateSections(el)[0] : null),
      parts: (el) => (dateKind(el) === "sections" ? dateSections(el) : [el]),
      describe: (el) => (dateKind(el) === "sections" ? dateQuestion(el) : {}),
      answered: (el) => (dateKind(el) === "sections" ? dateSections(el).every((s) => s.value.trim()) : Boolean(el.value)),
      read: (el) => {
        if (dateKind(el) !== "sections") return el.value;
        const got = Object.fromEntries(dateSections(el).map((s) => [partOf(s), s.value.trim()]));
        return [got.year, pad(got.month ?? ""), pad(got.day ?? "")].filter(Boolean).join("-");
      },
      dateKind, dateSections, partOf,
    },
    {
      // Inputs, textareas and contenteditable editing hosts (rich-text boxes);
      // typeText types into all three.
      name: "text", kind: "text",
      match: (el) => el instanceof HTMLTextAreaElement
        || (el instanceof HTMLInputElement && TEXT_TYPES.has(el.type) && !searchLike(el) && !pressInput(el))
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
      // A select with no placeholder always shows its first option: that is
      // an answer only when the page marked it (`selected`) or someone moved
      // off it.
      answered: (el) => !el.multiple && Boolean(realOptions(el).some((o) => o.selected))
        && (el.selectedIndex > 0 || Boolean(el.options[el.selectedIndex]?.defaultSelected)),
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
      // input combobox. What was typed into a select-style widget is never
      // its value.
      name: "search", kind: "choice", open: "search",
      match: (el) => el instanceof HTMLInputElement && TEXT_TYPES.has(el.type) && !el.readOnly && searchLike(el),
      multi: searchMulti,
      read: readSearch,
    },
    {
      // A button (or div role=button, or read-only input) that opens a list,
      // or a non-input combobox. An ARIA 1.1 combobox wrapping its own text
      // input, and a toggle beside a search input, belong to that input.
      name: "popup", kind: "choice", open: "press",
      match: (el) => {
        if (el instanceof HTMLInputElement) return pressInput(el);
        if (companionSearch(el)) return false;
        if (el.getAttribute("role") === "combobox") return !el.querySelector('input:not([type="hidden"])');
        return buttonLike(el) && HASPOPUP.test(el.getAttribute("aria-haspopup") ?? "");
      },
      read: (el) => {
        const own = el instanceof HTMLInputElement ? el.value : (el.innerText || el.textContent);
        let t = clean(clean(own).replace(GLYPHS, ""));
        if (!t && el instanceof HTMLInputElement) t = clean(box(el)?.querySelector(SINGLE)?.textContent);
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
    // For the inventory: a toggle that belongs to a search input is not a field.
    companionSearch,
    readField,
    pass,
  };
})();
