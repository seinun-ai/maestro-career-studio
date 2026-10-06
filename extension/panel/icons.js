/* Maestro CS Companion — the panel's icons.
 *
 * Glyph data from Lucide (lucide-react v1.48.0, ISC licence, https://lucide.dev): the same drawings the web app
 * uses, one per concept (frontend/lib/concept-icons.ts: done = circle-check, warning = triangle-alert,
 * attachment = paperclip, locked = lock, none = minus). `ns.icon(name, { size, label })` builds an <svg> with
 * createElementNS and setAttribute, never innerHTML, so the panel stays CSP-clean and the node harness can read it.
 *
 * An icon never stands alone. With no `label` it is `aria-hidden` and a word sits beside it; with one it is an
 * image named by it. `data-icon` carries the name for tests and for CSS.
 *
 * Loaded before every stage and action script (panel.html); panel.js throws at boot if it did not publish.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const SVG_NS = "http://www.w3.org/2000/svg";

  const ICONS = {
    "check": [["path", { d: "M20 6 9 17l-5-5" }]],
    "circle-check": [["circle", { cx: "12", cy: "12", r: "10" }], ["path", { d: "m16 9-5.5 5.5L8 12" }]],
    "circle-minus": [["circle", { cx: "12", cy: "12", r: "10" }], ["path", { d: "M8 12h8" }]],
    "circle-alert": [["circle", { cx: "12", cy: "12", r: "10" }],
      ["line", { x1: "12", x2: "12", y1: "8", y2: "12" }],
      ["line", { x1: "12", x2: "12.01", y1: "16", y2: "16" }]],
    "triangle-alert": [
      ["path", { d: "m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3" }],
      ["path", { d: "M12 9v4" }], ["path", { d: "M12 17h.01" }]],
    "chevron-down": [["path", { d: "m6 9 6 6 6-6" }]],
    "chevron-right": [["path", { d: "m9 18 6-6-6-6" }]],
    "external-link": [["path", { d: "M15 3h6v6" }], ["path", { d: "M10 14 21 3" }],
      ["path", { d: "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" }]],
    "arrow-right": [["path", { d: "M5 12h14" }], ["path", { d: "m12 5 7 7-7 7" }]],
    "paperclip": [["path", {
      d: "m16 6-8.414 8.586a2 2 0 0 0 2.829 2.829l8.414-8.586a4 4 0 1 0-5.657-5.657l-8.379 8.551a6 6 0 1 0 8.485 8.485l8.379-8.551" }]],
    "lock": [["rect", { width: "18", height: "11", x: "3", y: "11", rx: "2", ry: "2" }],
      ["path", { d: "M7 11V7a5 5 0 0 1 10 0v4" }]],
    "minus": [["path", { d: "M5 12h14" }]],
  };

  /** An <svg> for `name`, `size` px square. Throws on a name this file does not hold: a typo should fail the
   * render that made it, not draw an empty box. */
  ns.icon = (name, { size = 14, label = null } = {}) => {
    const shapes = ICONS[name];
    if (!shapes) throw new Error(`panel/icons: no icon named ${name}`);
    const svg = document.createElementNS(SVG_NS, "svg");
    const attrs = {
      class: "ico", width: size, height: size, viewBox: "0 0 24 24", fill: "none",
      stroke: "currentColor", "stroke-width": 2, "stroke-linecap": "round",
      "stroke-linejoin": "round", "data-icon": name,
    };
    for (const [key, value] of Object.entries(attrs)) svg.setAttribute(key, value);
    if (label) {
      svg.setAttribute("role", "img");
      svg.setAttribute("aria-label", label);
    } else {
      svg.setAttribute("aria-hidden", "true");
    }
    for (const [tag, shape] of shapes) {
      const part = document.createElementNS(SVG_NS, tag);
      for (const [key, value] of Object.entries(shape)) part.setAttribute(key, value);
      svg.appendChild(part);
    }
    return svg;
  };
})();
