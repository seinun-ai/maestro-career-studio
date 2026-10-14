/* Maestro CS Companion — a widget's recipe keys: its family, and its family here.
 *
 * The fill loop remembers which of the engine's own moves worked for a KIND
 * of control (shared/recipe-book.js). This module names the kind: a hash of
 * the widget's STRUCTURE — its shape, tag and role, the NAMES of the
 * `data-automation-id` / `data-uxi-widget-type` values on it and on its
 * ancestors up to its field box (GUID-like tokens stripped: they differ per
 * tenant, per page load), whether it names the list it controls, the kind of
 * popup it says it opens, one answer or several, the kind of committed
 * evidence it exposes, and ENGINE_VERSION. Never its label, value, options or
 * any URL: two controls that differ only in what they ask or hold are one
 * family.
 *
 * `site` is the family on this host: a hash of the family key and
 * `location.hostname`. No host leaves this module, only the hash — which is
 * not a URL, though a host someone already knows can be tested against it.
 *
 * Only widgets with a move to learn get keys: the popup and search shapes,
 * whose opening and searching have more than one known move. Text boxes and
 * passive choices (a select, radios, checkboxes) are written one way.
 *
 * It also WATCHES: when a field is parked and the user fixes it by hand, the
 * panel asks the page what they did (`watch` / `report`). The answer is one of
 * the engine's own moves, in the recipe book's words (`open:press`,
 * `open:keys`, `search:enter`, `search:debounce`). The watcher records event
 * TYPES and, for a fixed few keys, their NAMES (ArrowDown, ArrowUp, Enter,
 * Space, Tab, Escape); it never reads `key` for anything else and never
 * `value`, so what was typed is not in it to leak. Only trusted input counts: the
 * engine's own presses and keys are synthetic. (A page's own script can fire a trusted
 * `input` with execCommand("insertText"); that can only shape a lesson for its own site
 * key, and a family is trusted only after two hosts agree.)
 *
 * Bump ENGINE_VERSION when a move's meaning changes: every recipe learned
 * under the old meaning then matches nothing and expires.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  // LOAD ONCE. panel_prepare re-injects every content script into the SAME
  // isolated world (see INTERNALS.md, "A tab that was already open…").
  const loaded = (ns.loadedOnce ??= new Set());
  if (loaded.has("content/recipes.js")) return;
  loaded.add("content/recipes.js");
  const ENGINE_VERSION = 1;
  const MARKERS = ["data-automation-id", "data-uxi-widget-type"];
  // A 32-hex id, a UUID: per tenant or per load, never part of a kind.
  const GUIDISH = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{16,}/gi;
  const UP = 4; // ancestors read above the element, at most: the field box is never further out
  const edge = (n) => !n || n === document.body || n === document.documentElement || n.tagName === "FORM";

  // A 53-bit string hash (cyrb53), in base 36. Not a secret: it only has to
  // be stable, short and one-way enough that the book holds no words.
  const hash = (text) => {
    let h1 = 0xdeadbeef;
    let h2 = 0x41c6ce57;
    for (let i = 0; i < text.length; i += 1) {
      const c = text.charCodeAt(i);
      h1 = Math.imul(h1 ^ c, 2654435761);
      h2 = Math.imul(h2 ^ c, 1597334677);
    }
    h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
    h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
    return (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(36);
  };
  // The marker names on the element and on up to UP of its ancestors (so UP
  // + 1 nodes at most), stopping at the field box (Workday's `formField-*`
  // wrapper) and never reaching past a form.
  const markers = (el) => {
    const names = [];
    for (let n = el, d = 0; !edge(n) && d <= UP; n = n.parentElement, d += 1) {
      for (const a of MARKERS) {
        const v = n.getAttribute(a);
        if (v) names.push(`${a}=${v.replace(GUIDISH, "")}`);
      }
      if (n !== el && n.getAttribute("data-automation-id")?.startsWith("formField")) break;
    }
    return names;
  };
  const evidenceKind = (el, shape) => {
    const { proof } = shape.evidence(el);
    if (proof === null) return "display";
    if (Array.isArray(proof)) return "pills";
    return shape.name === "popup" ? "backing" : "self";
  };
  const multiplicity = (el, shape) => {
    const m = shape.multi?.(el);
    return m == null ? "unknown" : m ? "multi" : "single";
  };

  // { family, site } keys for a widget with a move to learn; else null.
  const signature = (el, shape) => {
    if (!shape?.open) return null;
    const family = hash([
      `v${ENGINE_VERSION}`, shape.name, el.tagName.toLowerCase(), el.getAttribute("role") ?? "",
      ...markers(el), el.hasAttribute("aria-controls") ? "controls" : "", el.getAttribute("aria-haspopup") ?? "",
      multiplicity(el, shape), evidenceKind(el, shape),
    ].join("|"));
    return { family: `f:${family}`, site: `s:${hash(`${family}@${location.hostname}`)}` };
  };

  // ---------- watching a hand fix ----------

  const KEY_NAMES = { ArrowDown: "ArrowDown", ArrowUp: "ArrowUp", Enter: "Enter", " ": "Space", Tab: "Tab", Escape: "Escape" };
  // Keys that open a list from the keyboard.
  const OPENERS = new Set(["ArrowDown", "Enter", "Space"]);
  // The engine waits this long for a widget's own filter before it sends an Enter (fill-core's
  // ANSWER_MS); a pick that came after at least as long a pause is the "wait" move.
  const PAUSE_MS = 300;
  const MAX_LOG = 64;
  const MAX_WATCHED = 40;
  // What a pointer lands on when it picks from a popup.
  const OPTIONISH = '[role="option"], [role="listbox"], [role="menu"], [role="menuitem"], [role="treeitem"], [role="tree"]';
  const watching = new Map(); // fid -> { family, site, log }
  // The ONE field the user's hands are on: engaging a field disengages every other, so a pick in
  // one field's popup is never credited to another field they typed in earlier.
  let active = null;
  const EVENTS = ["pointerdown", "keydown", "input", "focusin"];

  // Whether the event's path runs through this field (its element or any part of it).
  const within = (path, fid) => path.some((n) => n instanceof Element && ns.fillInventory.fidFor(n, { relist: false }) === fid);
  // Consecutive repeats are one gesture: a held key, a burst of typing.
  const push = (entry, token) => {
    const last = entry.log.at(-1);
    if (last && last.t === token.t && last.k === token.k) last.at = token.at;
    else if (entry.log.length < MAX_LOG) entry.log.push(token);
  };

  const onEvent = (e) => {
    if (!e.isTrusted) return;
    const path = e.composedPath();
    const at = performance.now();
    const fid = [...watching.keys()].find((one) => within(path, one));
    if (fid !== undefined) {
      active = fid;
      const entry = watching.get(fid);
      if (e.type === "pointerdown") push(entry, { t: "press", at });
      else if (e.type === "input") push(entry, { t: "type", at });
      else {
        // Only the names above, by exact match: a printable key is never read past this lookup.
        const name = KEY_NAMES[e.key];
        if (name) push(entry, { t: "key", k: name, at });
      }
      return;
    }
    if (!watching.has(active)) return;
    const inPopup = path.some((n) => n instanceof Element && n.matches(OPTIONISH));
    // A key, typing or focus outside every watched field (and outside a popup, where arrowing through
    // a list is still the field's) is the user's hands on another field: a later pick in THAT field's
    // popup is not this one's.
    if (e.type !== "pointerdown") {
      if (!inPopup) active = null;
      return;
    }
    // A pick lands in the popup of the field the user is on; anywhere else they have moved on.
    if (inPopup) push(watching.get(active), { t: "pick", at });
    else active = null;
  };

  // The recipe book's moves a log says the user made: how the widget was opened (the first
  // thing they did to it) and how a search was committed (the last time typing ended in an Enter,
  // or in a pick after a pause).
  const gesturesOf = (log) => {
    const out = [];
    const first = log.find((t) => t.t === "press" || t.t === "type" || (t.t === "key" && OPENERS.has(t.k)));
    if (first?.t === "press") out.push("open:press");
    if (first?.t === "key") out.push("open:keys");
    let typed = null;
    let search = null;
    for (const t of log) {
      if (t.t === "type") typed = t.at;
      else if (typed !== null && t.t === "key" && t.k === "Enter") [search, typed] = ["search:enter", null];
      else if (typed !== null && t.t === "pick" && t.at - typed >= PAUSE_MS) [search, typed] = ["search:debounce", null];
    }
    if (search) out.push(search);
    return out;
  };

  const stopListening = () => { for (const type of EVENTS) document.removeEventListener(type, onEvent, true); };
  // Start watching one field (a fid the last inventory named) for the user's hands. False when
  // the field is gone or has no family, i.e. nothing a recipe could hold.
  const watch = (fid) => {
    const el = ns.fillInventory.resolve(fid);
    const shape = ns.fillInventory.shapeOf(fid);
    const keys = el && shape ? signature(el, shape) : null;
    if (!keys || (!watching.has(fid) && watching.size >= MAX_WATCHED)) return false;
    if (!watching.size) for (const type of EVENTS) document.addEventListener(type, onEvent, true);
    watching.set(fid, { ...keys, log: [] });
    return true;
  };
  // What the user did to a watched field, once: `{ family, site, gestures }`, or null for a field
  // not being watched. Ends that field's watch.
  const report = (fid) => {
    const entry = watching.get(fid);
    if (!entry) return null;
    watching.delete(fid);
    if (active === fid) active = null;
    if (!watching.size) stopListening();
    return { family: entry.family, site: entry.site, gestures: gesturesOf(entry.log) };
  };
  // Forget every watch (a new park replaces the last one).
  const unwatch = () => {
    watching.clear();
    active = null;
    stopListening();
  };

  ns.recipes = { signature, watch, report, unwatch };
})();
