/* Maestro CS Companion — every fillable control in this frame, as fields.
 *
 * Identity is the element (WeakMap → fid `<frame>-<n>`); a fingerprint
 * (shape, question, section, repeat, name, ordinal) reacquires a re-rendered
 * node and lets an action prove it still targets the field it was decided for.
 * A field made of several elements (a radio/checkbox set, date sections) is ONE
 * field whose fid every part maps to.
 *
 * A field the user changed (trusted input/change while the engine is not
 * typing into THAT element) is `touched`. Never-fill fields (shared/policy.js)
 * are `policyBlocked`. Controls no shape recognises are listed as "unknown".
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const FRAME = Math.random().toString(36).slice(2, 8);
  // Known shapes plus ARIA widgets no shape claims yet: an unrecognised control
  // is still LISTED (shape "unknown") so the panel can name it, never dropped.
  const CANDIDATE = 'input, select, textarea, button[aria-haspopup], [role="combobox"]:not(input), '
    + '[contenteditable]:not([contenteditable="false"]), [role="textbox"]:not(input):not(textarea), '
    + '[role="radio"]:not(input), [role="checkbox"]:not(input), [role="switch"], '
    + '[role="spinbutton"]:not(input), [role="slider"]';
  const SKIP = new Set(["hidden", "submit", "button", "reset", "image", "file", "password"]);
  const NOT_A_FIELD = '[role="listbox"], [role="menu"], [role="tree"], [role="grid"]';
  let counter = 0;
  let lastConsentForms = false;
  const fidOf = new WeakMap(); // element (every part of a field) -> fid
  const registry = new Map(); // fid -> { ref, fp, shape, question }
  const touched = new Set(); // fids
  const touchedEls = new WeakSet(); // elements changed before any inventory saw them
  const UNKNOWN = () => ns.shapes.unknown;
  const shapeFor = (el) => ns.shapes.of(el) ?? UNKNOWN();

  const walk = (root, out = []) => {
    out.push(...root.querySelectorAll(CANDIDATE));
    for (const host of root.querySelectorAll("*")) if (host.shadowRoot) walk(host.shadowRoot, out);
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
    if (el.disabled || el.readOnly) return false;
    // A node inside a rich-text box is the box's content, not a field.
    if (el.parentElement?.isContentEditable) return false;
    // Options inside a popup are not fields; neither is anything inside a popup
    // the ENGINE opened. A modal application form (a dialog the page opened)
    // is walked like any other part of the page.
    if (el.closest(NOT_A_FIELD) || ns.fillBase.insideEnginePopup(el)) return false;
    // An unrecognised wrapper around a real control: the control is the field.
    if (!ns.shapes.of(el) && el.querySelector(ns.fieldControls.CONTROL)) return false;
    return shown(el);
  };
  const describe = (el, shape) => {
    const own = ns.readField(el);
    const over = shape.describe?.(el) ?? {};
    return { ...own, ...over, required: own.required || Boolean(over.required) };
  };
  const baseFp = (el, shape, d) => [shape.name, d.question, d.section, d.repeatIndex, el.getAttribute("name") ?? ""].join("|");
  const blocked = (question, consentForms) => Boolean(ns.isPolicyBlocked?.(question ?? "", { consentForms }));

  const list = ({ consentForms = lastConsentForms } = {}) => {
    lastConsentForms = consentForms;
    const groups = new Set();
    const ordinals = new Map();
    const fields = [];
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
      if (!fid) {
        // A re-rendered node takes over the fid of a disconnected node with the
        // same fingerprint.
        for (const [known, entry] of registry) {
          if (entry.fp === fp && !entry.ref.deref()?.isConnected) {
            fid = known;
            break;
          }
        }
        fid ??= `${FRAME}-${(counter += 1)}`;
      }
      for (const part of parts) {
        fidOf.set(part, fid);
        if (touchedEls.has(part)) touched.add(fid);
      }
      fidOf.set(el, fid);
      registry.set(fid, { ref: new WeakRef(el), fp, shape: shape.name, question: d.question });
      const passive = shape.passive?.(el) ?? null;
      const committed = shape.read(el);
      const multi = Boolean(shape.multi?.(el));
      fields.push({
        fid, fp, shape: shape.name, kind: shape.kind, multi,
        question: d.question, source: d.source, section: d.section, repeatIndex: d.repeatIndex,
        required: d.required, help: d.help,
        committed,
        // "Answered" is stricter than "has a value": an unchecked lone checkbox
        // reads "No" but was never answered, and a multi-select is never
        // finished just because one chip exists — missing items may be added.
        answered: shape.answered ? Boolean(shape.answered(el)) : (multi ? false : Boolean(committed)),
        options: passive?.options ?? null,
        optionsComplete: passive?.complete ?? false,
        invalid: ns.fillBase.invalid(el),
        touched: touched.has(fid),
        policyBlocked: blocked(d.question, consentForms),
      });
    }
    return { frame: FRAME, host: location.hostname, fields };
  };

  // The fingerprint as the page reads NOW (question, section, repeat may have
  // changed on a live node); the ordinal is the one recorded at inventory.
  const liveFp = (fid) => {
    const entry = registry.get(fid);
    const el = entry?.ref.deref();
    if (!el?.isConnected) return null;
    const shape = shapeFor(el);
    return `${baseFp(el, shape, describe(el, shape))}|${entry.fp.split("|").at(-1)}`;
  };

  const resolve = (fid) => {
    const entry = registry.get(fid);
    if (!entry) return null;
    if (entry.ref.deref()?.isConnected) return entry.ref.deref();
    list();
    const again = registry.get(fid)?.ref.deref();
    return again?.isConnected ? again : null;
  };

  // Only the element the engine is typing into right now is exempt: the user
  // typing in ANOTHER field while the engine works still marks it theirs.
  // composedPath: a change inside an open shadow root reaches document
  // retargeted to its host.
  const onUserChange = (e) => {
    if (!e.isTrusted) return;
    const path = e.composedPath().filter((n) => n instanceof Element);
    if (!path.length) return;
    for (const el of path) {
      if (el === ns.fillBusyEl) return;
      if (fidOf.has(el)) {
        touched.add(fidOf.get(el));
        return;
      }
    }
    touchedEls.add(path[0]);
  };
  for (const type of ["input", "change"]) document.addEventListener(type, onUserChange, true);

  ns.fillInventory = {
    list, resolve, frame: FRAME,
    fpOf: (fid) => registry.get(fid)?.fp ?? null,
    liveFp,
    shapeOf: (fid) => (registry.has(fid) ? ns.shapes.byName(registry.get(fid).shape) : null),
    isTouched: (fid) => touched.has(fid),
    isBlocked: (fid) => blocked(registry.get(fid)?.question, lastConsentForms),
  };
})();
