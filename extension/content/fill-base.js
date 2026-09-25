/* Maestro CS Companion — page primitives every fill operation shares.
 *
 * CANCELLATION IS REAL. Every operation runs under `withinBudget(fn, ms)`,
 * which hands `fn` its own token; every gesture primitive (press, typeText,
 * closePopups, settle, waitFor) checks the token FIRST and throws `Cancelled`.
 * A timed-out or stopped operation therefore cannot land a click later —
 * Promise.race alone would only stop waiting for it.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const clean = (s) => ns.readFieldText(s);

  class Cancelled extends Error {
    constructor() {
      super("cancelled");
      this.name = "Cancelled";
    }
  }
  const live = new Set();
  // Stop is LATCHED for the run: once cancelAll() fires, every operation that
  // starts afterwards is born cancelled, until the panel starts a new run
  // (fill-ops resets the latch when it sees a new runId).
  let halted = false;
  const resume = () => {
    halted = false;
  };
  const check = (t) => {
    if (t?.cancelled) throw new Cancelled();
  };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const settle = async (t, ms = 120) => {
    check(t);
    await sleep(ms);
    check(t);
  };
  const withinBudget = async (fn, ms) => {
    const t = { cancelled: halted };
    if (t.cancelled) throw new Cancelled(); // a latched Stop never starts new work
    live.add(t);
    let timer;
    try {
      return await Promise.race([
        fn(t),
        new Promise((_, reject) => {
          timer = setTimeout(() => {
            t.cancelled = true;
            reject(new Cancelled());
          }, ms);
        }),
      ]);
    } finally {
      clearTimeout(timer);
      live.delete(t);
    }
  };
  const cancelAll = () => {
    halted = true;
    for (const t of live) t.cancelled = true;
  };
  const waitFor = async (fn, ms, t, step = 50) => {
    const end = Date.now() + ms;
    for (;;) {
      check(t);
      const got = fn();
      if (got) return got;
      if (Date.now() > end) return null;
      await sleep(step);
    }
  };

  const visible = (el) => {
    if (!el?.isConnected || !el.getClientRects().length) return false;
    const s = getComputedStyle(el);
    return s.visibility !== "hidden" && s.display !== "none" && Number(s.opacity) !== 0;
  };

  const ERROR_NODE = '[data-automation-id="errorMessage"], [role="alert"], [class*="error" i]';
  const ERROR_WORDS = /error|required|must|invalid|enter a/i;
  const byId = (el, id) => el.getRootNode().getElementById?.(id) ?? document.getElementById(id);
  // The field's box: walk up while the ancestor holds no OTHER field, stopping
  // at a named wrapper. A box holding a neighbour would let its error mark this
  // field invalid ("form-fields" wrappers, a bare form). The field's own group
  // (radios/checkboxes by group or name, a date's spinbutton sections) and a
  // plain button (a Clear beside the box) are not "other fields".
  const CONTROL = 'input:not([type="hidden"]), select, textarea, button[aria-haspopup], [role="combobox"], [contenteditable="true"]';
  const NAMED = '[data-automation-id^="formField"], .form-group, .field, [class*="field" i]';
  const GROUP = 'fieldset, [role="radiogroup"], [role="group"]';
  const ownGroup = (el) => {
    if (/^(radio|checkbox)$/.test(el.type)) return el.closest(GROUP) ?? el.parentElement;
    if (el.getAttribute("role") === "spinbutton") {
      return el.closest(`${GROUP}, [data-automation-id="dateInputWrapper"]`) ?? el.parentElement;
    }
    return null;
  };
  const fieldBox = (el) => {
    const grp = ownGroup(el);
    const foreign = (n) => [...n.querySelectorAll(CONTROL)].some((c) => c !== el && !el.contains(c)
      && !grp?.contains(c) && !(el.name && c.name === el.name));
    let box = null;
    for (let n = el.parentElement, d = 0; n && n !== document.body && d < 6; n = n.parentElement, d += 1) {
      if (foreign(n)) break; // the next level up holds another field: stop below it
      box = n;
      if (n.matches(NAMED)) break; // a named wrapper holding only this field is the box
    }
    return box;
  };
  const invalid = (el) => {
    if (el.getAttribute("aria-invalid") === "true") return true;
    const described = (el.getAttribute("aria-describedby") ?? "").split(/\s+/).filter(Boolean)
      .map((id) => byId(el, id)).filter((n) => n && visible(n));
    if (described.some((n) => ERROR_WORDS.test(n.textContent ?? ""))) return true;
    return [...(fieldBox(el)?.querySelectorAll(ERROR_NODE) ?? [])]
      .some((n) => visible(n) && !n.contains(el) && clean(n.textContent));
  };

  const POPUP = '[role="listbox"], [role="menu"], [role="tree"], [role="grid"], [role="dialog"]';
  const popups = () => [...document.querySelectorAll(POPUP)].filter(visible);
  const ownedPopup = (el, before) => {
    const linked = ["aria-controls", "aria-owns"]
      .flatMap((a) => (el.getAttribute(a) ?? "").split(/\s+/).filter(Boolean))
      .map((id) => byId(el, id)).find((n) => n && visible(n));
    if (linked) return linked;
    const active = el.getAttribute("aria-activedescendant");
    const viaActive = active && byId(el, active)?.closest(POPUP);
    if (viaActive && visible(viaActive)) return viaActive;
    // Outermost fresh popups only: a listbox inside a new dialog is part of it.
    const fresh = popups().filter((p) => !before.includes(p) && !popups().some((q) => q !== p && !before.includes(q) && q.contains(p)));
    return fresh.length === 1 ? fresh[0] : null;
  };
  const OPTION = '[role="option"], [role="menuitem"], [role="treeitem"], [role="menuitemradio"], [role="menuitemcheckbox"]';
  const LOADING = /^(loading|searching|no (results|items|matches|options)|type to search)/i;
  const optionsOf = (popup) => (popup ? [...popup.querySelectorAll(OPTION)] : [])
    .filter((o) => visible(o) && o.getAttribute("aria-disabled") !== "true")
    .map((o, i) => ({
      oid: `o${i + 1}`,
      text: clean(o.innerText || o.textContent),
      selected: o.getAttribute("aria-selected") === "true" || o.getAttribute("aria-checked") === "true",
      el: o,
    }))
    .filter((o) => o.text && !LOADING.test(o.text));

  const press = (el, t) => {
    check(t);
    const r = el.getBoundingClientRect();
    const at = { bubbles: true, cancelable: true, composed: true, clientX: r.x + r.width / 2, clientY: r.y + r.height / 2 };
    el.dispatchEvent(new PointerEvent("pointerdown", at));
    el.dispatchEvent(new MouseEvent("mousedown", at));
    el.dispatchEvent(new PointerEvent("pointerup", at));
    el.dispatchEvent(new MouseEvent("mouseup", at));
    el.dispatchEvent(new MouseEvent("click", at));
  };
  // Workday ignores a synthetic Escape; an outside click closes its popups.
  // Two modes. Normal: the token is checked before Escape and again before the
  // outside click. CLEANUP (after a cancel/timeout): the one click a cancelled
  // run may still make is an outside click that closes a popup the ENGINE
  // opened — it touches no field. With no engine popup visible it does nothing.
  const closePopups = async (el, t, { cleanup = false } = {}) => {
    if (!cleanup) check(t);
    el?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await sleep(60);
    if (!cleanup) check(t);
    if (cleanup ? popups().some((p) => enginePopups.has(p)) : popups().length) {
      document.body.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
      document.body.click();
      await sleep(60);
    }
  };
  const proto = (el) => (el instanceof HTMLTextAreaElement ? HTMLTextAreaElement : HTMLInputElement).prototype;
  // Typing the way a person does: the browser fires REAL input events for
  // execCommand("insertText"), which React-controlled boxes (Workday) accept
  // where a setter + synthetic event is ignored. Setter only as a fallback.
  const typeText = (el, value, t) => {
    check(t);
    el.focus({ preventScroll: true });
    el.select?.();
    const ok = document.execCommand?.("insertText", false, value);
    if (ok && el.value === value) return;
    Object.getOwnPropertyDescriptor(proto(el), "value")?.set?.call(el, value);
    el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  };
  // Equal after folding case, accents and whitespace ONLY — punctuation is
  // meaning ("C" ≠ "C++", "123456.7" ≠ "12345.67"). A phone number is the one
  // value a page may re-punctuate, and only the FACT decides it is a phone
  // (the loop passes format "phone" for phone slots) — never its characters.
  // Both empty is NOT equal.
  const fold = (s) => String(s ?? "").normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase().replace(/\s+/g, " ").trim();
  const equivalent = (actual, wrote, { format } = {}) => {
    const a = fold(actual);
    const w = fold(wrote);
    if (!a || !w) return false;
    if (format === "phone") return a.replace(/\D/g, "") !== "" && a.replace(/\D/g, "") === w.replace(/\D/g, "");
    return a === w;
  };
  // Popups the engine itself opened: their controls are never inventoried as
  // page fields (a real modal form, which the engine did not open, is).
  const enginePopups = new WeakSet();
  const markEnginePopup = (pop) => {
    if (pop) enginePopups.add(pop);
  };
  const insideEnginePopup = (el) => {
    for (let n = el; n; n = n.parentElement) if (enginePopups.has(n)) return true;
    return false;
  };

  ns.fillBase = {
    Cancelled, check, sleep, settle, withinBudget, cancelAll, resume, waitFor, visible, invalid,
    popups, ownedPopup, optionsOf, press, closePopups, typeText, equivalent, clean,
    markEnginePopup, insideEnginePopup,
  };
})();
