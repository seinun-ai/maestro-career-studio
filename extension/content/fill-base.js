/* Maestro CS Companion — page primitives every fill operation shares.
 *
 * CANCELLATION IS REAL. Every operation runs under `withinBudget(fn, ms)`,
 * which hands `fn` its own token. Every gesture primitive (press, typeText,
 * closePopups, settle, waitFor) checks the token AND the latched Stop before it
 * acts and throws `Cancelled`, so a timed-out or stopped operation cannot land
 * a click later — Promise.race alone would only stop waiting for it. The one
 * exception is closePopups in cleanup mode, which may still close a popup the
 * engine itself opened. Stop (cancelAll) also settles every budget at once.
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
  class Unfocusable extends Error {
    constructor() {
      super("the field cannot take focus");
      this.name = "Unfocusable";
    }
  }
  // A missing token does not bypass a latched Stop.
  const check = (t) => {
    if (halted || t?.cancelled) throw new Cancelled();
  };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const settle = async (t, ms = 120) => {
    check(t);
    await sleep(ms);
    check(t);
  };
  const withinBudget = async (fn, ms) => {
    if (typeof ms !== "number" || !Number.isFinite(ms)) throw new TypeError("withinBudget needs a budget in ms");
    if (halted) throw new Cancelled(); // a latched Stop never starts new work
    const t = { cancelled: false, abort: null };
    let timer;
    // The budget exists (and t.abort with it) before fn runs.
    const budget = new Promise((_, reject) => {
      t.abort = () => {
        t.cancelled = true;
        reject(new Cancelled());
      };
      timer = setTimeout(t.abort, ms);
    });
    live.add(t);
    try {
      return await Promise.race([fn(t), budget]);
    } finally {
      clearTimeout(timer);
      live.delete(t);
    }
  };
  const cancelAll = () => {
    halted = true;
    for (const t of live) t.abort();
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
  // A describedby target is an error only when it IS an error node; hint text
  // ("You must use the name on your passport") is not. A live region counts
  // only when it reads like an error.
  const describedError = (n) => visible(n) && clean(n.textContent)
    && (n.matches(ERROR_NODE) || (n.hasAttribute("aria-live") && ERROR_WORDS.test(n.textContent)));
  // The field's box: walk up while the ancestor holds no OTHER field, stopping
  // at a named wrapper. A box holding a neighbour would let its error mark this
  // field invalid ("form-fields" wrappers, a bare form). Not "other fields": a
  // plain button (a Clear beside the box), same-name radios/checkboxes, and the
  // field's own group — a fieldset/group/date wrapper holding ONLY this
  // radio/checkbox set or these date sections (a section fieldset is not one).
  const CONTROL = 'input:not([type="hidden"]), select, textarea, button[aria-haspopup], [role="combobox"], [contenteditable="true"]';
  const NAMED = '[data-automation-id^="formField"], .form-group, .field, [class*="field" i]';
  const GROUP = 'fieldset, [role="radiogroup"], [role="group"]';
  const isChoice = (c) => /^(radio|checkbox)$/.test(c.type);
  const isDatePart = (c) => c.getAttribute("role") === "spinbutton";
  const sameField = (c, el) => (isChoice(el) ? isChoice(c) && c.name === el.name : isDatePart(el) && isDatePart(c));
  const ownGroup = (el) => {
    if (!isChoice(el) && !isDatePart(el)) return null;
    const g = el.closest(isDatePart(el) ? `${GROUP}, [data-automation-id="dateInputWrapper"]` : GROUP) ?? el.parentElement;
    return g && [...g.querySelectorAll(CONTROL)].every((c) => c === el || sameField(c, el)) ? g : null;
  };
  const fieldBox = (el) => {
    const grp = ownGroup(el);
    const foreign = (n) => [...n.querySelectorAll(CONTROL)].some((c) => c !== el && !el.contains(c)
      && !grp?.contains(c) && !(isChoice(el) && el.name && isChoice(c) && c.name === el.name));
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
      .map((id) => byId(el, id));
    if (described.some((n) => n && describedError(n))) return true;
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
    const opened = popups().filter((p) => !before.includes(p));
    const fresh = opened.filter((p) => !opened.some((q) => q !== p && q.contains(p)));
    return fresh.length === 1 ? fresh[0] : null;
  };
  const OPTION = '[role="option"], [role="menuitem"], [role="treeitem"], [role="menuitemradio"], [role="menuitemcheckbox"]';
  const LOADING = /^(loading|searching|no (results|items|matches|options)|type to search)/i;
  const optionsOf = (popup) => (popup ? [...popup.querySelectorAll(OPTION)] : [])
    .filter((o) => visible(o) && o.getAttribute("aria-disabled") !== "true")
    .map((o) => ({
      text: clean(o.innerText || o.textContent),
      selected: o.getAttribute("aria-selected") === "true" || o.getAttribute("aria-checked") === "true",
      el: o,
    }))
    .filter((o) => o.text && !LOADING.test(o.text))
    .map((o, i) => ({ oid: `o${i + 1}`, ...o }));

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
  // Closes only popups the ENGINE opened (markEnginePopup): with none visible
  // it sends nothing, so a page's own modal or menu is never touched. Escape
  // first; Workday ignores a synthetic Escape, so an outside click if an engine
  // popup is still open. Normal mode checks the token before each gesture.
  // CLEANUP mode (after a cancel/timeout) skips the checks: closing a popup the
  // engine opened is the one thing a cancelled run may still do.
  const closePopups = async (el, t, { cleanup = false } = {}) => {
    if (!cleanup) check(t);
    if (!engineOpen()) return;
    el?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await sleep(60);
    if (!cleanup) check(t);
    if (engineOpen()) {
      document.body.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
      document.body.click();
      await sleep(60);
    }
  };
  const proto = (el) => (el instanceof HTMLTextAreaElement ? HTMLTextAreaElement : HTMLInputElement).prototype;
  const focused = (el) => (el.getRootNode().activeElement ?? document.activeElement) === el;
  // Typing the way a person does: the browser fires REAL input events for
  // execCommand("insertText"), which React-controlled boxes (Workday) accept
  // where a setter + synthetic event is ignored. execCommand types into
  // whatever HAS focus, so a target that did not take focus (disabled, hidden)
  // throws Unfocusable rather than typing into another field. The setter is a
  // fallback only when typing changed nothing; a page that reformatted or
  // truncated (maxlength) what was typed has answered, and is not overwritten.
  const typeText = (el, value, t) => {
    check(t);
    el.focus({ preventScroll: true });
    if (!focused(el)) throw new Unfocusable();
    if (el.isContentEditable) {
      const before = el.textContent;
      const range = document.createRange();
      range.selectNodeContents(el);
      const selection = getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      const ok = document.execCommand("insertText", false, value);
      if (!ok || (el.textContent === before && before !== value)) {
        throw new Error("the browser would not type into this editable box");
      }
      return;
    }
    const before = el.value;
    el.select?.();
    const ok = document.execCommand?.("insertText", false, value);
    if (ok && (el.value !== before || before === value)) return;
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
  // page fields (a real modal form, which the engine did not open, is), and
  // they are the only popups closePopups acts on. Held until they leave the page.
  const enginePopups = new Set();
  const markEnginePopup = (pop) => {
    if (pop) enginePopups.add(pop);
  };
  const engineOpen = () => {
    for (const p of enginePopups) if (!p.isConnected) enginePopups.delete(p);
    return [...enginePopups].some(visible);
  };
  const insideEnginePopup = (el) => {
    for (let n = el; n; n = n.parentElement) if (enginePopups.has(n)) return true;
    return false;
  };

  ns.fillBase = {
    Cancelled, Unfocusable, check, sleep, settle, withinBudget, cancelAll, resume, waitFor, visible, invalid,
    popups, ownedPopup, optionsOf, press, closePopups, typeText, equivalent, clean,
    markEnginePopup, insideEnginePopup,
  };
})();
