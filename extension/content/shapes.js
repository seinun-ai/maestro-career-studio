/* Maestro CS Companion — widget shapes: recognise, group, read committed, open.
 *
 * A shape is ONLY: `match` (is this element one of mine), `groupKey` (the
 * elements that are one field share a key — radio/checkbox members, date
 * sections), `parts` (those elements), `describe` (a question that belongs to
 * the group, not the element), `read` (what is COMMITTED), `passive` (options
 * readable without touching the page), `answered`, `open` (how a choice
 * widget shows its options: "press" or "search") and `evidence` (below). No
 * shape acts or verifies; fill-core runs one generic path over all of them.
 *
 * The committed reader is the load-bearing part: search text is never a value;
 * a single-value node, pill, chip, hidden backing input, button text or
 * checked state is. The one exception is a free-text autocomplete (a search
 * box with no select structure at all): what its input holds IS the answer.
 *
 * `evidence(el)` is `{ display, proof }`: what the widget SHOWS (the reader
 * above) and what the app SAVED, where the page exposes it — a Workday search
 * box's pills, a popup's hidden backing input (a Workday popup shows a pick
 * before it saves it, and may take it back). `proof` is null where there is
 * nothing but the display to read; fill-core's verify then falls back to the
 * display, which is weaker.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  // LOAD ONCE. panel_prepare re-injects every content script into the SAME
  // isolated world; a second run would reset this module's state (see
  // INTERNALS.md, "A tab that was already open…").
  const loaded = (ns.loadedOnce ??= new Set());
  if (loaded.has("content/shapes.js")) return;
  loaded.add("content/shapes.js");
  const clean = (s) => ns.readFieldText(s);
  const TEXT_TYPES = new Set(["text", "email", "tel", "url", "number", "search"]);
  // Workday's search widget markers. Live, `selectinput` sits ON the input and
  // the pills live in the ancestor `multiselect` container (notes §2).
  const SEARCH_BOX = '[data-uxi-widget-type="selectinput"], [data-uxi-widget-type="multiselectinput"], [data-uxi-widget-type="multiselect"]';
  const DATE_SECTION = /dateSection(Month|Day|Year)-input/;
  const SECTION = 'input[data-automation-id^="dateSection"]';
  const DATE_PATTERN = /^(mm|dd|yyyy)([/.\-](mm|dd|yyyy)){1,2}$/i;
  const HASPOPUP = /^(listbox|true|menu|dialog)$/;
  // Trailing glyphs (▾) go before a popup's text is read or tested as a
  // placeholder (ns.isPlaceholderText, shared/policy.js).
  const GLYPHS = /[\p{So}\s]+$/u;
  const CHIP = '[data-automation-id="selectedItem"], [class*="multi-value__label" i], [class*="multiValue" i] [class*="label" i]';
  const SINGLE = '[class*="single-value" i], [class*="singleValue" i], [class*="selection-item" i]';
  const SELECT_STRUCTURE = `${SINGLE}, ${CHIP}, [class*="placeholder" i], [class*="value-container" i], [class*="valueContainer" i]`;
  const GROUPER = 'fieldset, [role="radiogroup"], [role="group"]';
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
    cache = { field: new Map(), members: new Map(), pills: new Map() };
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

  // Workday's widget wrapper around a search input (the `multiselect`
  // container that holds its pills). Never the element itself: live Workday
  // marks the INPUT `selectinput`, and a box that is the input holds no pills.
  const workdayBox = (el) => el.parentElement?.closest(SEARCH_BOX) ?? null;
  // A search widget's box — the ONE boundary of a search widget (fill-core's
  // leave uses it too): Workday's wrapper, else the highest ancestor (3
  // levels) holding no OTHER field (its own toggle button is not one), never
  // <body>, <html> or a <form> — a page-wide wrapper would read a neighbour's
  // value as this one's. No such ancestor: no box.
  const box = (el) => {
    const own = workdayBox(el);
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
    return workdayBox(el) ?? el.parentElement?.closest('[role="combobox"]')
      ?? (container && box(el)?.contains(container) ? container : null);
  };
  // A search widget's hidden backing input counts only inside the widget's
  // root — never a form's csrf token.
  const backingInput = (el) => widgetRoot(el)?.querySelector('input[type="hidden"]') ?? null;
  const searchBacking = (el) => backingInput(el)?.value ?? "";
  const chips = (el) => [...(box(el)?.querySelectorAll(CHIP) ?? [])].map((c) => clean(c.textContent)).filter(Boolean);

  // Single or several. Live Workday wraps School (one answer) and Skills
  // (several) in the SAME container; the difference shows only when its list
  // is open — single rows hold a radio, multi rows a checkbox (notes §2 rule
  // 7). So what a list the engine opened for this element showed is
  // remembered (fill-core's open calls `learnRows`), and it outranks
  // everything else; before that, several pills, an `aria-multiselectable`
  // list or a multi-value widget's own marker say "several". Anything else is
  // not known yet (null) — never guessed from the question.
  const learned = new WeakMap(); // el -> "multi" | "single", from the rows of a list it opened
  const rowsKind = (pop) => {
    if (!pop) return null;
    if (pop.matches('[aria-multiselectable="true"]') || pop.querySelector('[role="option"] input[type="checkbox"]')) return "multi";
    return pop.querySelector('[role="option"] input[type="radio"]') ? "single" : null;
  };
  const learnRows = (el, pop) => {
    const kind = rowsKind(pop);
    if (kind) learned.set(el, kind);
    return kind;
  };
  const multiplicity = (el) => {
    if (learned.has(el)) return learned.get(el);
    const b = box(el);
    if (el.closest('[data-uxi-widget-type="multiselectinput"]') || /is-multi/i.test(b?.className ?? "")
      || b?.querySelector('[class*="is-multi" i]') || b?.matches('[aria-multiselectable="true"]')
      || b?.querySelector('[aria-multiselectable="true"]') || chips(el).length > 1) return "multi";
    return null;
  };
  // Tri-state for the inventory and fill-core: true (several), false (one),
  // null (not known yet — a Workday box before its list has been seen).
  const searchMulti = (el) => {
    const kind = multiplicity(el);
    return kind === null ? null : kind === "multi";
  };
  // A select-style widget shows its value somewhere other than the input.
  const selectStructure = (el) => Boolean(widgetRoot(el) || box(el)?.querySelector(SELECT_STRUCTURE));
  // A select-style box that keeps its pick as the INPUT's own text, with no
  // separate value node. Oracle JET's `oj-combobox-one` says so itself: the host
  // loses `oj-has-no-value` once it holds a value (REAL proof, ahead of anything
  // else). Any other autocomplete, with no hidden backing input to say otherwise,
  // reads its text as the value only while it is AT REST: the list closed and the
  // box not focused — a query being typed, or one whose list is still coming, is
  // never a value. That is a WEAK read (`weakRead`): the text may be nothing but
  // the query the engine typed.
  const jetHost = (el) => el.closest("oj-combobox-one");
  const restingText = (el) => {
    const text = el.value.trim();
    if (!text) return "";
    const live = el.getAttribute("aria-autocomplete");
    if (!live || live === "none" || el.getAttribute("aria-expanded") === "true") return "";
    return el.getRootNode().activeElement === el ? "" : text;
  };
  // `kind` (multiplicity) and `pills` (chips) are read once by a caller that
  // needs them again.
  const readSearch = (el, kind = multiplicity(el), pills = chips(el)) => {
    if (kind === "multi") return pills;
    // A Workday pill box not yet known to be single reads as the list of pills
    // it shows (one, or none: ""); known single, its one pill.
    if (workdayBox(el)) return kind === "single" ? (pills[0] ?? "") : (pills.length ? pills : "");
    if (!selectStructure(el)) return el.value; // free-text autocomplete ("Location (City)")
    const single = box(el)?.querySelector(SINGLE);
    if (single) return clean(single.textContent);
    if (pills[0]) return pills[0];
    const jet = jetHost(el);
    if (jet) return jet.classList.contains("oj-has-no-value") ? "" : el.value.trim();
    const backing = backingInput(el);
    return backing ? backing.value : restingText(el);
  };
  // Whether the box's value is read from its own text alone and by the weak rule above
  // (no value node, no pill, no backing input, no JET marker).
  // Whether the box is of that kind BEFORE anything is typed or picked: select-style, with no value node,
  // pill, backing input or JET marker to prove a pick by (the read above is then all it has).
  const weakBox = (el) => !workdayBox(el) && selectStructure(el) && !box(el)?.querySelector(SINGLE) && chips(el).length === 0
    && !jetHost(el) && !backingInput(el);
  const weakRead = (el) => !workdayBox(el) && selectStructure(el) && !box(el)?.querySelector(SINGLE) && chips(el).length === 0
    && !jetHost(el) && !backingInput(el) && restingText(el) !== "";
  // A multi widget is never finished (items may be missing), and a Workday
  // pill box whose multiplicity is not known yet is not either: its one pill
  // may be the first of several.
  const searchAnswered = (el) => {
    const kind = multiplicity(el);
    if (kind === "multi" || (workdayBox(el) && kind !== "single")) return false;
    return [readSearch(el, kind)].flat().some(Boolean);
  };
  // What the app saved. A search box's PROOF is its pills: a Workday box's
  // (the display, read again — Workday keeps what it saved nowhere else the
  // page shows) or a multi widget's chips. Any other search widget shows its
  // value only (proof null: the display decides).
  const searchEvidence = (el) => {
    const kind = multiplicity(el);
    const pills = chips(el);
    return { display: readSearch(el, kind, pills), proof: workdayBox(el) || kind === "multi" ? pills : null };
  };

  // A popup's backing input: the one non-visible input BESIDE it — a direct
  // sibling, where Workday puts it and fills it only when the app takes the
  // pick (notes §8a). Never one further out: a hidden "Other" text box in the
  // question's wrapper is a different answer, and proving by it would call a
  // good pick unconfirmed. Never one in the popup's own list or a menu (a
  // search box a closed menu keeps), never a checkable. Two candidates is no
  // backing: a guess would prove a neighbour's value.
  const popupBacking = (el) => {
    const list = el.getAttribute("aria-controls");
    const hidden = [...(el.parentElement?.children ?? [])].filter((i) => i !== el && i.tagName === "INPUT"
      && !/^(checkbox|radio|file)$/.test(i.type) && !ns.fillBase.visible(i)
      && !i.closest('[role="listbox"], [role="menu"]') && !(list && i.closest(`[id="${CSS.escape(list)}"]`)));
    return hidden.length === 1 ? hidden[0] : null;
  };
  // A select2-style widget's native <select>, which the page hides and the app
  // submits (iCIMS, live 2026-10-01: a box showing "— Make a Selection —" over
  // an empty one was read as answered). Only a select the page TIES to the box
  // counts, never one that is merely nearby (a hidden follow-up question's):
  // the select right before the box's own container (select2's layout: a
  // wrapper holding no label, no heading and no control but the box, so never
  // the NEXT question's wrapper), or one the box's aria-labelledby /
  // aria-controls names, itself or by its label. It must hide ITSELF inside a
  // shown parent: not displayed, or select2's 1px clip (aria-hidden alone
  // hides nothing on screen). Two candidates: none.
  const clipped = (s) => {
    const r = s.getBoundingClientRect();
    return r.width <= 1 && r.height <= 1;
  };
  const hidesItself = (s) => ns.fillBase.visible(s.parentElement) && (!ns.fillBase.visible(s) || clipped(s));
  const widgetOnly = (n, el) => !n.matches(`label, ${ns.ANY_HEADING}`) && !n.querySelector(`label, ${ns.ANY_HEADING}`)
    && [...n.querySelectorAll(ns.fieldControls.CONTROL)].every((c) => c === el || el.contains(c));
  const backingSelect = (el) => {
    const tied = new Set();
    for (let n = el, d = 0; n && d < 4 && !edge(n) && widgetOnly(n, el); n = n.parentElement, d += 1) {
      if (n.previousElementSibling instanceof HTMLSelectElement) tied.add(n.previousElementSibling);
    }
    for (const attr of ["aria-labelledby", "aria-controls"]) {
      for (const id of (el.getAttribute(attr) ?? "").split(/\s+/).filter(Boolean)) {
        const t = ns.byIdIn(el, id);
        const s = t instanceof HTMLLabelElement ? t.control : t;
        if (s instanceof HTMLSelectElement) tied.add(s);
      }
    }
    const own = [...tied].filter(hidesItself);
    return own.length === 1 ? own[0] : null;
  };
  // What a backing select holds: its value, or "" while it holds nothing (an
  // empty value, a disabled option, or a placeholder row whatever its value:
  // "-1", "0", its own text), whatever the box shows.
  const selectHeld = (s) => {
    const o = s.options[s.selectedIndex];
    return o && !o.disabled && o.value !== "" && !ns.isPlaceholderText(o.text) ? s.value : "";
  };
  // A select that is a popup box's backing (above) is the box's, never a
  // field of its own: select2's 1px clip counts as visible, and two fields
  // would be two writes.
  const POPUPISH = '[role="combobox"], [aria-haspopup]:not([aria-haspopup="false"])';
  const backsABox = (s) => {
    if (!hidesItself(s)) return false;
    const boxes = [...(s.nextElementSibling?.matches(POPUPISH) ? [s.nextElementSibling] : []),
      ...(s.nextElementSibling?.querySelectorAll(POPUPISH) ?? [])];
    for (const id of [s.id, ...[...(s.labels ?? [])].map((l) => l.id)].filter(Boolean)) {
      boxes.push(...s.getRootNode().querySelectorAll(
        `[aria-labelledby~="${CSS.escape(id)}"], [aria-controls~="${CSS.escape(id)}"]`));
    }
    return boxes.some((b) => b !== s && ns.shapes.of(b)?.name === "popup" && backingSelect(b) === s);
  };
  // A popup's text (placeholder: nothing), else a read-only input's value or
  // the single-value node beside it.
  const readPopup = (el) => {
    const own = el instanceof HTMLInputElement ? el.value : (el.innerText || el.textContent);
    let t = clean(clean(own).replace(GLYPHS, ""));
    if (!t && el instanceof HTMLInputElement) t = clean(box(el)?.querySelector(SINGLE)?.textContent);
    return ns.isPlaceholderText(t) ? "" : t;
  };
  // Display and proof are one thing for a text box, a date, a select and a
  // checked state: the element's own value is what the page holds.
  const selfEvidence = (read) => (el) => {
    const v = read(el);
    return { display: v, proof: v };
  };

  // Radio/checkbox members: same name in the same form (or root; a checkbox's
  // nearest grouping container first), else the
  // nearest grouping container. A nameless RADIO outside any container (Gem)
  // belongs with the nameless radios of the nearest ancestor holding others
  // and no other kind of control — only its own run of them, cut at any
  // visible text that is not an option's label (a second question), and never
  // a run in which two options read the same. A nameless checkbox there is
  // alone (a yes/no answer of its own).
  const namelessRadio = (x) => x instanceof HTMLInputElement && x.type === "radio" && !x.name && !x.closest(GROUPER);
  const radioRun = (n, radios, el) => {
    const labels = radios.flatMap((r) => [...r.labels]);
    const runs = [[]];
    const walk = document.createTreeWalker(n, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    for (let x = walk.nextNode(); x; x = walk.nextNode()) {
      if (radios.includes(x)) runs.at(-1).push(x);
      else if (x.nodeType === Node.TEXT_NODE && clean(x.data) && ns.fillBase.visible(x.parentElement)
        && !labels.some((l) => l.contains(x)) && runs.at(-1).length) runs.push([]);
    }
    const run = runs.find((r) => r.includes(el));
    const texts = run.map((r) => readField(r).question);
    return new Set(texts).size === texts.length ? run : [el];
  };
  const members = (el) => memo("members", el, () => {
    if (el.name) {
      // A named CHECKBOX looks no further than its nearest grouping container:
      // live Workday names every entry's "I currently work here" box alike
      // (`currentlyWorkHere`, CarMax 2026-09-30), and a set spanning entries
      // asked the entry's title. Radios keep the form (a native radio set).
      const scope = (el.type === "checkbox" && el.closest(GROUPER)) || el.form || el.getRootNode();
      return [...scope.querySelectorAll(`input[type="${el.type}"][name="${CSS.escape(el.name)}"]`)];
    }
    const c = el.closest(GROUPER);
    if (c) return [...c.querySelectorAll(`input[type="${el.type}"]`)];
    if (el.type !== "radio") return [el];
    const { CONTROL } = ns.fieldControls;
    for (let n = el.parentElement; n && !edge(n); n = n.parentElement) {
      const controls = [...n.querySelectorAll(CONTROL)];
      if (!controls.every(namelessRadio)) break;
      if (controls.length > 1) return radioRun(n, controls, el);
    }
    return [el];
  });
  const lone = (el) => el.type === "checkbox" && members(el).length < 2;
  const labelOf = (input) => readField(input).question;
  // A group with no container question asks the text BEFORE its first
  // member (ns.precedingLabel, field-reader.js: the same stops as a field's),
  // or, for a set of options, the paragraph sentence that asks for one.
  const precedingQuestion = (ms) => {
    const t = (ms.length > 1 ? ns.textBefore(ms[0]) : "")
      || ns.precedingLabel(ms[0].closest("label") ?? ms[0], ms, { group: true, prose: ms.length > 1 })
      || (ms.length > 1 && ms.every((m) => m.closest("tr") === ms[0].closest("tr")) ? ns.rowAbove(ms[0]) : "");
    const marked = t ? ns.unmark(t) : null;
    return marked ? { question: marked.text, source: "preceding", required: marked.required } : null;
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

  // PILL GROUPS: a row of buttons that each hold a state (`aria-pressed`) or
  // ARIA radios (`role=radio` + `aria-checked`) that are not inputs. The group
  // is the `role=radiogroup`, else the nearest ancestor holding two or more
  // of them and no other control. A toolbar's toggles are not an answer.
  // Buttons need a question to be a field at all (a lone toggle, an icon row
  // with no label is not one); ARIA radios were always listed.
  const PRESSABLE = 'button[aria-pressed], [role="button"][aria-pressed]';
  const ARIA_RADIO = '[role="radio"][aria-checked]';
  // A list of buttons with no ARIA state at all (`ul[role=list][aria-label]` of button-only items): the
  // state, when the page shows one, is a class on the button.
  const LISTED = 'ul[role="list"][aria-label] > li > button:only-child';
  const SELECTED_CLASS = /(^|[-_\s])(selected|active|pressed|checked)($|[-_\s])/i;
  const stateless = (m) => !m.hasAttribute("aria-pressed") && !m.hasAttribute("aria-checked");
  const pillOn = (m) => m.getAttribute("aria-pressed") === "true" || m.getAttribute("aria-checked") === "true"
    || (stateless(m) && m.matches(LISTED) && SELECTED_CLASS.test(m.getAttribute("class") ?? ""));
  const pillText = (m) => clean(m.textContent) || clean(m.getAttribute("aria-label") ?? "");
  // A `required` label the page marks by class (a CSS-only star): the nearest
  // label before the group, in the nearest ancestor that holds one.
  const labelRequired = (container) => {
    for (let n = container.parentElement, d = 0; n && d < 3 && !edge(n); n = n.parentElement, d += 1) {
      const before = [...n.querySelectorAll("label")].filter((l) => !container.contains(l)
        && (l.compareDocumentPosition(container) & Node.DOCUMENT_POSITION_FOLLOWING));
      if (before.length) {
        const l = before.at(-1);
        return /required/i.test(l.className) || ns.unmark(clean(l.textContent)).required;
      }
    }
    return false;
  };
  // A `ul[role=list][aria-label]` whose items each ARE one plain button: the button is the item's only
  // child and the item says nothing else (a file's name beside its Remove button is not a pill), two or
  // more of them. Not a menu, a pager, a tab list, or buttons that act on something (Remove, Edit...).
  const NOT_A_PILL = '[aria-haspopup]:not([aria-haspopup="false"]), [aria-expanded], [aria-current], [aria-controls], [role="tab"], [role="menuitem"]';
  const ACTION_WORDS = /\b(remove|delete|edit|view|download|upload|replace)\b/i;
  // A button that sends or moves the form on (Back, Next, Submit) is never an answer: a group holding one is
  // a row of actions. ARIA radios are not buttons and cannot send anything.
  const movesOn = (m) => !m.matches(ARIA_RADIO) && Boolean(ns.pageKind?.movesOn(m));
  const listedGroup = (el) => {
    const container = el.closest('ul[role="list"][aria-label]');
    if (!container || container.closest('[role="toolbar"]')) return null;
    const items = [...container.children];
    const members = items.map((li) => (li.tagName === "LI" && li.childElementCount === 1 && li.firstElementChild.tagName === "BUTTON"
      ? li.firstElementChild : null));
    const pill = (b) => b && !b.matches(NOT_A_PILL) && clean(b.parentElement.textContent) === clean(b.textContent)
      && !ACTION_WORDS.test(`${clean(b.textContent)} ${b.getAttribute("aria-label") ?? ""}`);
    if (items.length < 2 || !members.every(pill) || members.some(movesOn)) return null;
    const q = describeBy(container);
    return q.question ? { container, members, ...q, radio: false } : null;
  };
  const pillGroup = (el) => memo("pills", el, () => {
    if (el instanceof HTMLInputElement || !el.matches(`${PRESSABLE}, ${ARIA_RADIO}, ${LISTED}`)) return null;
    const radio = el.matches(ARIA_RADIO);
    if (!radio && !el.matches(PRESSABLE)) return listedGroup(el);
    const kind = radio ? ARIA_RADIO : PRESSABLE;
    const whole = (container) => {
      if (container.closest('[role="toolbar"]') || container.querySelector(ns.fieldControls.CONTROL)) return null;
      return { container, members: [...container.querySelectorAll(kind)] };
    };
    const grouped = radio ? el.closest('[role="radiogroup"]') : null;
    let found = grouped ? whole(grouped) : null;
    for (let n = el.parentElement, d = 0; !grouped && n && d < 6 && !edge(n); n = n.parentElement, d += 1) {
      if (n.querySelectorAll(kind).length < 2) continue;
      found = whole(n);
      break;
    }
    if (!found || found.members.some(movesOn)) return null;
    const q = describeBy(found.container);
    return radio || q.question ? { ...found, ...q, radio } : null;
  });
  // The pills a person can press: shown, and not disabled unless it holds the answer.
  const pillChoices = (el) => pillGroup(el).members
    .filter((m) => ns.fillBase.visible(m) && (pillOn(m) || m.getAttribute("aria-disabled") !== "true"));
  const pillMulti = (el) => {
    const g = pillGroup(el);
    if (g.radio) return false;
    if (g.container.getAttribute("aria-multiselectable") === "true") return true;
    for (let n = g.container, d = 0; n && d < 3 && !edge(n); n = n.parentElement, d += 1) {
      if (/multi-?select/i.test(`${n.tagName} ${n.className}`)) return true;
    }
    return false;
  };

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
      answered: searchAnswered,
      read: readSearch,
      weakRead,
      weakBox,
      evidence: searchEvidence,
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
      read: readPopup,
      // A select2/iCIMS box shows no star of its own: the hidden select under
      // it carries `required`, and a field wrongly read optional is now left
      // blank rather than asked.
      describe: (el) => {
        const s = popupBacking(el) ? null : backingSelect(el);
        return { required: Boolean(s && (s.required || s.getAttribute("aria-required") === "true")) };
      },
      // Over a backing select, answered is what the select holds, never the
      // box's words.
      answered: (el) => {
        const s = popupBacking(el) ? null : backingSelect(el);
        return s ? selectHeld(s) !== "" : Boolean(readPopup(el));
      },
      // The button shows the pick at once; the app has it only when the
      // backing input beside it holds a value (notes §8a: picks that showed,
      // then reverted, never filled it), or the backing select does. Neither
      // found: display only.
      evidence: (el) => {
        const input = popupBacking(el);
        const s = input ? null : backingSelect(el);
        return { display: readPopup(el), proof: input ? input.value : s ? selectHeld(s) : null };
      },
    },
    {
      // A group of pill buttons (aria-pressed) or ARIA radios. Passive, like a
      // radio set: the options are the pills' texts and the answer is the
      // pressed one. A click on a pressed pill un-selects it, so a choose
      // looks first and never presses one that is already on.
      name: "pills", kind: "choice",
      // Listed to the loop and the backend as a radio set ("group"): they know
      // six shapes, and a pill group answers like one.
      reports: "group",
      match: (el) => pillGroup(el) !== null,
      multi: pillMulti,
      groupKey: (el) => pillGroup(el).members[0],
      parts: (el) => pillGroup(el).members,
      describe: (el) => {
        const g = pillGroup(el);
        return { question: g.question ?? "", source: g.source ?? null,
          required: Boolean(g.required) || g.container.getAttribute("aria-required") === "true" || labelRequired(g.container) };
      },
      passive: (el) => ({
        options: pillChoices(el).map((m, i) => ({ oid: `o${i + 1}`, text: pillText(m), selected: pillOn(m) })),
        complete: true,
      }),
      // Never finished while several are allowed (missing items may be added).
      answered: (el) => !pillMulti(el) && pillChoices(el).some(pillOn),
      read: (el) => {
        const on = pillChoices(el).filter(pillOn).map(pillText);
        return pillMulti(el) ? on : (on[0] ?? "");
      },
      members: pillChoices, labelOf: pillText, pressed: pillOn,
    },
  ];
  // Every other shape shows what it holds: display and proof are its value.
  for (const s of SHAPES) s.evidence ??= selfEvidence(s.read);

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
    // For the inventory: a toggle that belongs to a search input is not a
    // field, nor a select that backs a popup box.
    companionSearch,
    backsABox,
    readField,
    pass,
    // For fill-core: a search widget's boundary (its leave), what the rows
    // of a list the engine opened say about single or several, and the pill
    // nodes its box shows (explore takes back one it added).
    box,
    learnRows,
    // A Workday search box (its `multiselect` container around the input):
    // the one widget that searches on Enter, whatever its typing showed.
    workday: (el) => Boolean(workdayBox(el)),
    pills: (el) => [...(box(el)?.querySelectorAll(CHIP) ?? [])].map((node) => ({ node, text: clean(node.textContent) })),
  };
})();
