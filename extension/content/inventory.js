/* Maestro CS Companion — every fillable control in this frame, as fields.
 *
 * Identity is the element (WeakMap → fid `<frame>-<n>`); a fingerprint
 * (shape, question, section, repeat, name, ordinal) reacquires a re-rendered
 * node and lets an action prove it still targets the field it was decided for.
 * A field made of several elements (a radio/checkbox set, date sections) is ONE
 * field whose fid every part maps to. In one pass no two fields share a fid; a
 * fid whose node left the page and was not reacquired by the very next pass is
 * dead (resolve → null) and never handed to another field.
 *
 * A field the user changed (trusted input/change while the engine is not
 * working on THAT field) is `touched`. Never-fill fields (shared/policy.js) are
 * `policyBlocked` — by question, or when every option is a never-fill one;
 * each option also carries its own `policyBlocked`. Controls no shape
 * recognises are listed as "unknown".
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  // LOAD ONCE. panel_prepare re-injects every content script into the SAME
  // isolated world; a second run would reset this module's state (see
  // INTERNALS.md, "A tab that was already open…").
  const loaded = (ns.loadedOnce ??= new Set());
  if (loaded.has("content/inventory.js")) return;
  loaded.add("content/inventory.js");
  const FRAME = Math.random().toString(36).slice(2, 8);
  // Known shapes plus ARIA widgets no shape claims yet: an unrecognised control
  // is still LISTED (shape "unknown") so the panel can name it, never dropped.
  // A non-button element with aria-haspopup counts only as a button or
  // combobox (not an info icon or a Help link); aria-haspopup="false" never.
  const CANDIDATE = 'input, select, textarea, button[aria-haspopup]:not([aria-haspopup="false"]), '
    + '[aria-haspopup]:not([aria-haspopup="false"]):is([role="button"], [role="combobox"]):not(button):not(input), '
    + '[role="combobox"]:not(input), [contenteditable]:not([contenteditable="false"]), '
    + '[role="textbox"]:not(input):not(textarea), [role="radio"]:not(input), [role="checkbox"]:not(input), '
    + '[role="switch"], [role="spinbutton"]:not(input), [role="slider"]';
  const SKIP = new Set(["hidden", "submit", "button", "reset", "image", "file", "password"]);
  // Options inside a popup are not fields; site chrome (header, nav) is not the form.
  const NOT_A_FIELD = '[role="listbox"], [role="menu"], header, nav, [role="banner"], [role="navigation"]';
  let counter = 0;
  let lastConsentForms = false;
  const fidOf = new WeakMap(); // element (every part of a field) -> fid
  const registry = new Map(); // fid -> { ref, fp, shape, question, options }
  let lastSeen = new Set(); // fids the previous pass listed
  const touched = new Set(); // fids
  const touchedEls = new WeakSet(); // elements changed before any inventory saw them
  const shapeFor = (el) => ns.shapes.of(el) ?? ns.shapes.unknown;

  // The DOM generation: resolve() re-lists at most once per change. Shadow
  // roots are observed as the walk finds them.
  let generation = 0;
  let listedAt = -1;
  const observer = new MutationObserver(() => {
    generation += 1;
  });
  const OBSERVE = {
    childList: true, subtree: true, attributes: true,
    attributeFilter: ["style", "class", "hidden", "disabled", "readonly", "aria-hidden", "role", "name", "id", "type"],
  };
  const observed = new WeakSet();
  const observe = (root) => {
    if (observed.has(root)) return;
    observed.add(root);
    observer.observe(root, OBSERVE);
  };
  const flush = () => {
    if (observer.takeRecords().length) generation += 1;
  };

  // Document order, shadow-root fields in place.
  const walk = (root, out = []) => {
    observe(root);
    for (const el of root.querySelectorAll("*")) {
      if (el.matches(CANDIDATE)) out.push(el);
      if (el.shadowRoot) walk(el.shadowRoot, out);
    }
    return out;
  };
  const shown = (el) => {
    const { visible } = ns.fillBase;
    if (visible(el)) return true;
    // Custom radios/checkboxes hide the input and show a label.
    if (el.type !== "radio" && el.type !== "checkbox") return false;
    return [...(el.labels ?? []), el.closest("label"), el.parentElement].some((n) => n && visible(n));
  };
  const eligible = (el) => {
    if (el instanceof HTMLInputElement && SKIP.has(el.type)) return false;
    if (el.disabled) return false;
    const shape = ns.shapes.of(el);
    // Read-only is not fillable — unless it opens a list when pressed.
    if (el.readOnly && shape?.name !== "popup") return false;
    // A node inside a rich-text box is the box's content, not a field.
    if (el.parentElement?.isContentEditable) return false;
    // A modal application form (a dialog the page opened) is walked; a popup
    // the ENGINE opened is not.
    if (el.closest(NOT_A_FIELD) || ns.fillBase.insideEnginePopup(el)) return false;
    // A toggle beside a search input is part of the input's field; a select
    // that backs a popup box is part of the box's.
    if (ns.shapes.companionSearch(el)) return false;
    if (el instanceof HTMLSelectElement && ns.shapes.backsABox(el)) return false;
    // An unrecognised wrapper around a real control: the control is the field.
    if (!shape && el.querySelector(ns.fieldControls.CONTROL)) return false;
    return shown(el);
  };
  const describe = (el, shape) => {
    const own = ns.shapes.readField(el);
    const over = shape.describe?.(el) ?? {};
    return { ...own, ...over, required: own.required || Boolean(over.required) };
  };
  const baseFp = (el, shape, d) => [shape.name, d.question, d.section, d.repeatIndex, el.getAttribute("name") ?? ""].join("|");
  const blocked = (text, consentForms) => Boolean(ns.isPolicyBlocked?.(text ?? "", { consentForms }));
  // Blocked by its question, or when EVERY answer is a never-fill one (an
  // "Acknowledgements" set of attestations); a placeholder or dash row is no
  // answer either way. Lone checkboxes' Yes/No never are.
  const fieldBlocked = (question, options, consentForms) => {
    const answers = options.filter((t) => !ns.isPlaceholderText(t));
    return blocked(question, consentForms) || (answers.length > 0 && answers.every((t) => blocked(t, consentForms)));
  };

  const scan = (consentForms) => {
    const groups = new Set();
    const ordinals = new Map();
    const used = new Set();
    const claimed = new Map(); // fid -> element, this pass
    const fields = [];
    // Re-rendered nodes reacquire only from fields the PREVIOUS pass listed
    // whose node has since left the page.
    const orphans = [...lastSeen].filter((fid) => registry.has(fid) && !registry.get(fid).ref.deref()?.isConnected);
    for (const el of walk(document)) {
      if (!eligible(el)) continue;
      const shape = shapeFor(el);
      const group = shape.groupKey?.(el);
      if (group) {
        if (groups.has(group)) continue;
        groups.add(group);
      }
      const parts = shape.parts?.(el) ?? [el];
      const d = describe(el, shape);
      const base = baseFp(el, shape, d);
      const ordinal = (ordinals.get(base) ?? 0) + 1;
      ordinals.set(base, ordinal);
      const fp = `${base}|${ordinal}`;
      let fid = fidOf.get(el);
      if (fid && used.has(fid)) fid = null; // a part mapping outlived its group
      if (!fid) {
        fid = orphans.find((o) => !used.has(o) && registry.get(o).fp === fp)
          ?? `${FRAME}-${(counter += 1)}`;
      }
      used.add(fid);
      claimed.set(fid, el);
      for (const part of parts) {
        fidOf.set(part, fid);
        if (touchedEls.has(part)) touched.add(fid);
      }
      fidOf.set(el, fid);
      const passive = shape.passive?.(el) ?? null;
      const optionTexts = (shape.name === "group" && shape.lone?.(el)) ? [] : (passive?.options ?? []).map((o) => o.text);
      registry.set(fid, { ref: new WeakRef(el), fp, shape: shape.name, question: d.question, options: optionTexts });
      const committed = shape.read(el);
      // Tri-state: a search box may not know yet whether it takes one answer
      // or several (null) — the loop explores it before deciding.
      const several = shape.multi?.(el);
      const multi = several === null ? null : Boolean(several);
      fields.push({
        fid, fp, shape: shape.name, kind: shape.kind, multi,
        question: d.question, source: d.source, section: d.section, repeatIndex: d.repeatIndex,
        required: d.required, help: d.help,
        committed,
        // "Answered" is stricter than "has a value": an unchecked lone checkbox
        // reads "No" but was never answered, and a multi-select is never
        // finished just because one chip exists — missing items may be added.
        answered: shape.answered ? Boolean(shape.answered(el)) : (multi ? false : Boolean(committed)),
        options: passive?.options.map((o) => ({ ...o, policyBlocked: blocked(o.text, consentForms) })) ?? null,
        optionsComplete: passive?.complete ?? false,
        invalid: ns.fillBase.invalid(el),
        touched: touched.has(fid),
        policyBlocked: fieldBlocked(d.question, optionTexts, consentForms),
        // Value-free keys for the widget's family (content/recipes.js), or
        // null: what the loop's recipe book is looked up by.
        recipe: ns.recipes?.signature(el, shape) ?? null,
        // The one part of a date this control holds ("month" | "day" |
        // "year", the field reader's), or null: the loop writes only that part.
        part: d.part ?? null,
      });
    }
    // A fid not listed now whose node left the page is dead: never reacquired
    // by another field, and resolve() answers null at once.
    for (const [fid, entry] of registry) {
      if (!claimed.has(fid) && !entry.ref.deref()?.isConnected) registry.delete(fid);
    }
    lastSeen = new Set(claimed.keys());
    return fields;
  };

  // consentForms is per call and defaults to OFF: a caller that does not pass
  // the standing consent never inherits a previous run's.
  let lastFields = null; // what the last list() returned, whoever called it
  const list = ({ consentForms = false } = {}) => {
    lastConsentForms = consentForms;
    flush();
    const fields = ns.shapes.pass(() => scan(consentForms));
    flush();
    listedAt = generation;
    lastFields = fields;
    return { frame: FRAME, host: location.hostname, fields };
  };

  // The fids a full pass would list, cheaply (the loop's check after a
  // commit that may add or remove fields): nothing is described, read or
  // registered. A control no pass has given a fid yet — a field the page just
  // added, or a node it re-rendered — counts as new, so the set differs and
  // the loop takes a full inventory, which names (or reacquires) it.
  const peek = () => ns.shapes.pass(() => {
    const fids = new Set();
    let fresh = 0;
    for (const el of walk(document)) {
      if (!eligible(el)) continue;
      const fid = fidOf.get(el);
      fids.add(fid && registry.has(fid) ? fid : `new-${(fresh += 1)}`);
    }
    return [...fids];
  });

  // The fingerprint as the page reads NOW (question, section, repeat may have
  // changed on a live node); the ordinal is the one recorded at inventory.
  const liveFp = (fid) => {
    const entry = registry.get(fid);
    const el = entry?.ref.deref();
    if (!el?.isConnected) return null;
    const shape = shapeFor(el);
    return `${baseFp(el, shape, describe(el, shape))}|${entry.fp.split("|").at(-1)}`;
  };

  // A live node answers at once; a missing one costs at most ONE re-list per
  // DOM change, however many fids are asked about.
  const resolve = (fid) => {
    const live = () => {
      const el = registry.get(fid)?.ref.deref();
      return el?.isConnected ? el : null;
    };
    if (!registry.has(fid)) return null;
    if (live()) return live();
    flush();
    if (listedAt === generation) return null;
    ns.fillInventory.list({ consentForms: lastConsentForms });
    return live();
  };

  // Only the field the engine is working on right now is exempt — at FIELD
  // level, because a synthetic click on a radio fires a TRUSTED change on
  // whichever member it lands on. The user changing ANOTHER field while the
  // engine works still marks that field theirs. composedPath: a change inside
  // an open shadow root reaches document retargeted to its host.
  const onUserChange = (e) => {
    if (!e.isTrusted) return;
    // A value changed without the DOM changing: the last pass's committed
    // values are old (`last()` answers null until the next list()).
    generation += 1;
    const path = e.composedPath().filter((n) => n instanceof Element);
    if (!path.length) return;
    const busy = ns.fillBusyEl ?? null;
    const busyFid = busy ? fidOf.get(busy) : undefined;
    for (const el of path) {
      if (el === busy) return;
      if (fidOf.has(el)) {
        if (fidOf.get(el) !== busyFid) touched.add(fidOf.get(el));
        return;
      }
    }
    touchedEls.add(path[0]);
  };
  for (const type of ["input", "change"]) document.addEventListener(type, onUserChange, true);

  // The last list()'s fields while nothing in the DOM changed since it, else
  // null: a caller may reuse them instead of listing again. Kept HERE, with
  // the generation it was taken at, because a list() can happen anywhere
  // (resolve() re-lists on its own).
  const last = () => {
    flush();
    return listedAt === generation ? lastFields : null;
  };

  ns.fillInventory = {
    list, peek, resolve, last, frame: FRAME,
    fpOf: (fid) => registry.get(fid)?.fp ?? null,
    liveFp,
    shapeOf: (fid) => (registry.has(fid) ? ns.shapes.byName(registry.get(fid).shape) : null),
    isTouched: (fid) => touched.has(fid),
    isBlocked: (fid) => fieldBlocked(registry.get(fid)?.question, registry.get(fid)?.options ?? [], lastConsentForms),
  };
})();
