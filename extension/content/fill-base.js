/* Maestro CS Companion — page primitives every fill operation shares.
 *
 * CANCELLATION IS REAL. Every operation runs under `withinBudget(fn, ms)`,
 * which hands `fn` its own token. Every gesture primitive (press, enter,
 * keyPress, typeText, closePopups, settle, waitFor) checks the token AND the
 * latched Stop before it acts and throws `Cancelled`, so a timed-out or stopped
 * operation cannot land a click later — Promise.race alone would only stop
 * waiting for it. The exceptions: closePopups in cleanup mode, which may still
 * close a popup the engine itself opened, and `leave`, which takes no token —
 * moving focus OUT of a field is what a cancelled operation may still do.
 * Stop (cancelAll) also settles every budget at once.
 *
 * FOCUS IS REPORTED BY HAND WHEN THE BROWSER WILL NOT. While the browser
 * window is not focused, el.focus()/el.blur() move focus but fire no focus
 * events, so Workday never commits text or dates. `enter` and `leave` send the
 * missing events only when the browser stayed silent: the page hears one
 * focus and one leave either way.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  // LOAD ONCE. panel_prepare re-injects every content script into the SAME
  // isolated world; a second run would reset this module's state (see
  // INTERNALS.md, "A tab that was already open…").
  const loaded = (ns.loadedOnce ??= new Set());
  if (loaded.has("content/fill-base.js")) return;
  loaded.add("content/fill-base.js");
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
  const NAMED = '[data-automation-id^="formField"], .form-group, .field, [class*="field" i]';
  const GROUP = 'fieldset, [role="radiogroup"], [role="group"]';
  // CONTROL / isChoice / otherControl: the field reader's rule (read at call time).
  const isDatePart = (c) => c.getAttribute("role") === "spinbutton";
  const ownGroup = (el) => {
    const { CONTROL, isChoice } = ns.fieldControls;
    if (!isChoice(el) && !isDatePart(el)) return null;
    const sameField = (c) => (isChoice(el) ? isChoice(c) && c.name === el.name : isDatePart(c));
    const g = el.closest(isDatePart(el) ? `${GROUP}, [data-automation-id="dateInputWrapper"]` : GROUP) ?? el.parentElement;
    return g && [...g.querySelectorAll(CONTROL)].every((c) => c === el || sameField(c)) ? g : null;
  };
  const fieldBox = (el) => {
    const { CONTROL, otherControl } = ns.fieldControls;
    const grp = ownGroup(el);
    const foreign = (n) => [...n.querySelectorAll(CONTROL)].some((c) => otherControl(c, el) && !grp?.contains(c));
    let box = null;
    for (let n = el.parentElement, d = 0; n && n !== document.body && d < 6; n = n.parentElement, d += 1) {
      if (foreign(n)) break; // the next level up holds another field: stop below it
      box = n;
      if (n.matches(NAMED)) break; // a named wrapper holding only this field is the box
    }
    return box;
  };
  // Live Workday marks a date's error on ONE part (the year), and writes the
  // message as a plain span "Error: …" with no errorMessage id. Only that
  // "Error:" lead counts: the word mid-sentence or without the colon ("Error
  // messages you wrote:") is help text, and text anywhere inside a label or
  // legend is the question, never the error; text inside the control itself
  // (an editable answer) is the answer. Leaves only: an error split across
  // elements ("Error: <b>…</b>") is not seen by this rule.
  const ERROR_LEAD = /^error\s*:/i;
  const errorLeaf = (n, el) => !n.childElementCount && !n.matches("script, style, template")
    && !n.closest("label, legend") && !n.contains(el) && !el.contains(n)
    && ERROR_LEAD.test(clean(n.textContent)) && visible(n);
  const invalid = (el) => {
    if (el.getAttribute("aria-invalid") === "true") return true;
    const described = (el.getAttribute("aria-describedby") ?? "").split(/\s+/).filter(Boolean)
      .map((id) => byId(el, id));
    if (described.some((n) => n && describedError(n))) return true;
    const box = fieldBox(el);
    if (!box) return false;
    if ([...box.querySelectorAll(ns.fieldControls.CONTROL)].some((c) => c.getAttribute("aria-invalid") === "true")) {
      return true;
    }
    return [...box.querySelectorAll(ERROR_NODE)].some((n) => visible(n) && !n.contains(el) && clean(n.textContent))
      || [...box.querySelectorAll("*")].some((n) => errorLeaf(n, el));
  };

  const POPUP = '[role="listbox"], [role="menu"], [role="tree"], [role="grid"], [role="dialog"]';
  const popups = () => [...document.querySelectorAll(POPUP)].filter(visible);
  const ownedPopup = (el, before) => {
    // A linked node is the popup only when it IS one (a popup role, or holds
    // options) — aria-controls may point at a hint or a live region.
    const linked = ["aria-controls", "aria-owns"]
      .flatMap((a) => (el.getAttribute(a) ?? "").split(/\s+/).filter(Boolean))
      .map((id) => byId(el, id)).find((n) => n && visible(n) && (n.matches(POPUP) || n.querySelector(OPTION)));
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
  // BOUNDED: an engine popup that survives MAX_OUTSIDE outside clicks in a
  // row (each given CLOSE_WAIT_MS to close) is not clicked at again (nor sent Escape) — a popup that will not close is left,
  // never fought in a loop that clicks the page on every later operation.
  const closePopups = async (el, t, { cleanup = false } = {}) => {
    if (!cleanup) check(t);
    if (!engineOpen()) return;
    el?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await sleep(60);
    if (!cleanup) check(t);
    if (engineOpen()) {
      document.body.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
      document.body.click();
      // A popup with an exit transition closes a little late: give it that
      // long before counting it as one that survived the click.
      const end = Date.now() + CLOSE_WAIT_MS;
      do await sleep(40); while (engineOpen() && Date.now() < end);
      for (const p of enginePopups) if (visible(p)) survived.set(p, (survived.get(p) ?? 0) + 1);
    }
  };
  const proto = (el) => (el instanceof HTMLTextAreaElement ? HTMLTextAreaElement : HTMLInputElement).prototype;
  const activeIn = (el) => el.getRootNode().activeElement ?? document.activeElement;
  // Whether the browser itself fired `type` on el while fn ran (a focused
  // window does; an unfocused one moves focus in silence). A page that stops
  // focus events at the window in capture fools it into a second, dispatched
  // pair — rare, and a repeat focus is harmless where a missing one is not.
  const fired = (el, type, fn) => {
    let hit = false;
    const h = () => {
      hit = true;
    };
    el.addEventListener(type, h, { capture: true, once: true });
    try {
      fn();
    } finally {
      el.removeEventListener(type, h, { capture: true });
    }
    return hit;
  };
  // ENTER a field: real focus, plus the focus + focusin an unfocused window
  // does not fire — so the page hears exactly one pair either way. A field
  // that already has focus moves nothing and hears nothing; one that will not
  // take focus throws Unfocusable. `focusIn` skips the token check, for
  // typeText's undo alone.
  const enter = (el, t) => {
    check(t);
    focusIn(el);
  };
  // Silent too is the LEAVE of the field focus came from: it hears blur +
  // focusout first (relatedTarget: el, so a widget sees a move inside itself).
  const focusIn = (el) => {
    const prev = activeIn(el);
    if (prev === el) return;
    const native = fired(el, "focus", () => el.focus({ preventScroll: true }));
    if (activeIn(el) !== el) throw new Unfocusable();
    if (native) return;
    if (prev && prev !== document.body && prev !== el) {
      prev.dispatchEvent(new FocusEvent("blur", { composed: true, relatedTarget: el }));
      prev.dispatchEvent(new FocusEvent("focusout", { bubbles: true, composed: true, relatedTarget: el }));
    }
    el.dispatchEvent(new FocusEvent("focus", { composed: true }));
    el.dispatchEvent(new FocusEvent("focusin", { bubbles: true, composed: true }));
  };
  // LEAVE a field: blur whatever inside its WIDGET holds focus now — Workday
  // moves focus between a date's parts by itself, so blurring the box typed
  // in leaves focus inside and nothing validates — THEN, only if the browser
  // stayed silent, tell the page focus left. Blur first, events second: a
  // focusout sent while focus is still inside is ignored. Focus already
  // elsewhere (the page moved it out, as an auto-advancing box does) has
  // nothing to leave: a second focusout would report a leave that never happened.
  const leave = (el, widget = el) => {
    const a = activeIn(el);
    if (!a || a === document.body || !(a === el || widget.contains(a))) return;
    const native = fired(a, "blur", () => a.blur?.());
    if (!native) {
      a.dispatchEvent(new FocusEvent("blur", { composed: true }));
      a.dispatchEvent(new FocusEvent("focusout", { bubbles: true, composed: true, relatedTarget: null }));
    }
  };
  // A key press is keydown AND keyup: Workday searches on the key-up. For
  // search widgets only — never sent to a plain text box.
  const KEYS = { Enter: 13, Escape: 27, ArrowDown: 40 };
  const keyPress = (el, key, t) => {
    check(t);
    const code = KEYS[key] ?? 0;
    const init = { key, code: key, keyCode: code, which: code, bubbles: true, cancelable: true, composed: true };
    el.dispatchEvent(new KeyboardEvent("keydown", init));
    el.dispatchEvent(new KeyboardEvent("keyup", init));
  };
  // Typing the way a person does: the browser fires REAL input events for
  // execCommand("insertText"), which React-controlled boxes (Workday) accept
  // where a setter + synthetic event is ignored. execCommand types into
  // whatever HAS focus, so the box is ENTERED first, and a target that did not
  // take focus (disabled, hidden) throws Unfocusable rather than typing into
  // another field. Typing does not leave: the caller does. The setter is a
  // fallback only when typing changed nothing; a page that reformatted or
  // truncated (maxlength) what was typed has answered, and is not overwritten.
  // `undo` skips the token and latch checks for ONE purpose: a cancelled or
  // timed-out operation taking back a search query the engine itself typed.
  const typeText = (el, value, t, { undo = false } = {}) => {
    if (!undo) check(t);
    focusIn(el);
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
  // meaning ("C" ≠ "C++", "123456.7" ≠ "12345.67"). Phone numbers and money
  // are the values a page may re-punctuate ("$80,000" for 80000), and only the
  // FACT decides which it is (the loop passes format "phone" / "money" by
  // slot) — never its characters. Both empty is NOT equal.
  const fold = (s) => String(s ?? "").normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase().replace(/\s+/g, " ").trim();
  // ONE plain amount: an optional currency (code and/or currency sign) either
  // side, digits grouped by 3 with commas or spaces, at most 2 decimals,
  // nothing else. A range, "80k", "/hour", "80000+", "(80,000)" or "80.000"
  // (a European thousands mark) is not one, and is compared as text.
  const MONEY = /^([A-Z]{3})?\s*(\p{Sc}{0,2})\s*(\d{1,3}(?:[,\u00a0 ]\d{3})+|\d+)(?:\.(\d{1,2}))?\s*(\p{Sc}{0,2})\s*([A-Z]{3})?$/u;
  const moneyOf = (s) => {
    const m = MONEY.exec(String(s ?? "").trim());
    if (!m) return null;
    const [, code1, sym1, whole, cents = "", sym2, code2] = m;
    if (code1 && code2 && code1 !== code2) return null;
    return { value: Number(`${whole.replace(/\D/g, "")}.${cents || "0"}`), code: code1 ?? code2 ?? "", symbol: sym1 + sym2 };
  };
  // Money compares as a number only when BOTH sides are one plain amount, and
  // a currency both sides state must be the same one ("80000 CAD" ≠ "80000 USD").
  // A sign on one side and only a code on the other proves nothing ("$" may
  // be a mask over a fact given in EUR): unequal, the safe direction.
  const signOnly = (m) => Boolean(m.symbol) && !m.code;
  const codeOnly = (m) => Boolean(m.code) && !m.symbol;
  const sameMoney = (x, y) => x.value === y.value && (!x.code || !y.code || x.code === y.code)
    && (!x.symbol || !y.symbol || x.symbol === y.symbol)
    && !(signOnly(x) && codeOnly(y)) && !(codeOnly(x) && signOnly(y));
  const equivalent = (actual, wrote, { format } = {}) => {
    const a = fold(actual);
    const w = fold(wrote);
    if (!a || !w) return false;
    if (format === "phone") return a.replace(/\D/g, "") !== "" && a.replace(/\D/g, "") === w.replace(/\D/g, "");
    if (format === "money") {
      const x = moneyOf(actual);
      const y = moneyOf(wrote);
      if (x && y) return sameMoney(x, y);
    }
    return a === w;
  };
  // Popups the engine itself opened: their controls are never inventoried as
  // page fields (a real modal form, which the engine did not open, is), and
  // they are the only popups closePopups acts on. Held until they leave the page.
  const enginePopups = new Set();
  const markEnginePopup = (pop) => {
    if (pop) enginePopups.add(pop);
  };
  const MAX_OUTSIDE = 2;
  const CLOSE_WAIT_MS = 300;
  // Engine popup -> outside clicks it outlived IN A ROW: a popup seen closed
  // starts again at zero, so only one that never closes stops being clicked at.
  const survived = new WeakMap();
  // OPEN IS VISIBLE. An outside click hides a Workday list and leaves
  // aria-expanded="true" on its button, the list still in the DOM (notes
  // §8a): aria-expanded is never read, so a hidden list is closed and the
  // next press opens it rather than "closing" it.
  const engineOpen = () => {
    for (const p of enginePopups) {
      if (!p.isConnected) enginePopups.delete(p);
      else if (!visible(p)) survived.delete(p);
    }
    return [...enginePopups].some((p) => visible(p) && (survived.get(p) ?? 0) < MAX_OUTSIDE);
  };
  const insideEnginePopup = (el) => {
    for (let n = el; n; n = n.parentElement) if (enginePopups.has(n)) return true;
    return false;
  };

  ns.fillBase = {
    Cancelled, Unfocusable, check, sleep, settle, withinBudget, cancelAll, resume, waitFor, visible, invalid,
    popups, ownedPopup, optionsOf, press, closePopups, enter, leave, keyPress, typeText, equivalent, clean,
    markEnginePopup, insideEnginePopup, engineOpen,
  };
})();
