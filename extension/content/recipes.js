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
  const UP = 4; // ancestors read, at most: the field box is never further out
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
  // The marker names on the element and its ancestors, up to the field box
  // (Workday's `formField-*` wrapper, else UP levels, never past a form).
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

  ns.recipes = { ENGINE_VERSION, signature };
})();
