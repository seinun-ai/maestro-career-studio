/* Maestro CS Companion — repeating sections and their own Add buttons.
 *
 * A repeating section (Work Experience, Education, Websites…) grows only when
 * its own Add button is pressed, and an added entry's fields are REQUIRED
 * (notes §5): the loop asks the backend how many entries the profile can fill
 * and presses Add for the difference, one press at a time, through fill-ops.
 *
 * A SECTION is a container that OWNS an Add button:
 * - a `role=group` labelled (`aria-labelledby`) by a heading — Workday's
 *   `div[role=group][aria-labelledby=<h4 "Websites">]`; or
 * - a heading whose container (within three levels) holds entries titled
 *   "<Heading> <n>" — the same structure without ARIA.
 * Its ENTRIES are the visible blocks titled "<Heading> <n>" inside it (in a
 * labelled group, any group titled "… <n>"; a hidden prototype is not one). Its Add button is its OWN: inside the section,
 * inside no entry and no other section, reading /^add( another)?\b/i or marked
 * `data-automation-id="add-button"`. Never a form's submit, a control inside a link,
 * the page's header/nav/footer, and never anything whose words, name or
 * automation id say delete, remove or trash — Workday's Delete has no name at
 * all, and it is inside the entry, where no Add is looked for. What leaves
 * this file is text and counts, never an element: a Delete control cannot be
 * returned, only the section's own Add can be pressed, and only here.
 *
 * WHAT THIS FILE PUBLISHES: ns.fillSections = { list, add }.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  // LOAD ONCE. panel_prepare re-injects every content script into the SAME
  // isolated world; a second run would reset this module's state (see
  // INTERNALS.md, "A tab that was already open…").
  const loaded = (ns.loadedOnce ??= new Set());
  if (loaded.has("content/sections.js")) return;
  loaded.add("content/sections.js");
  const HEADING = "h1, h2, h3, h4, h5, h6, [role=heading]";
  const ARIA_SECTION = '[role="group"][aria-labelledby]';
  const BUTTON = 'button, [role="button"], input[type="button"]';
  const ADD = /^add( another)?\b/i;
  const NEVER = /delete|remove|trash/i;
  // The page's own chrome and navigation: an Add there is not a section's.
  const CHROME = 'header, nav, footer, [role="banner"], [role="navigation"], [role="contentinfo"]';
  const NAV_ID = /footer|next|submit|continue|back|save/i;
  const LEVELS = 3; // how far a heading's container is looked for
  const text = (el) => ns.readFieldText(el?.textContent ?? "");
  const base = () => ns.fillBase;

  const sidOf = new WeakMap(); // section element -> sid
  const bySid = new Map(); // sid -> WeakRef(section element)
  let counter = 0;
  const mint = (el) => {
    if (!sidOf.has(el)) {
      const sid = `${ns.fillInventory.frame}-s${(counter += 1)}`;
      sidOf.set(el, sid);
      bySid.set(sid, new WeakRef(el));
    }
    return sidOf.get(el);
  };

  const byId = (el, id) => el.getRootNode().getElementById?.(id) ?? document.getElementById(id);
  // A labelledby heading's words, or null when it names no heading.
  const labelledHeading = (el) => {
    const ids = (el.getAttribute("aria-labelledby") ?? "").split(/\s+/).filter(Boolean);
    const heads = ids.map((id) => byId(el, id)).filter((h) => h?.matches(HEADING));
    return heads.length ? ns.readFieldText(heads.map(text).join(" ")) : null;
  };
  // An entry's title: its label, else its first heading.
  const titleOf = (el) => labelledHeading(el) || ns.readFieldText(el.getAttribute("aria-label") ?? "")
    || text(el.querySelector(HEADING));
  const numbered = (title, heading) => {
    const t = (title ?? "").toLowerCase();
    const h = heading.toLowerCase();
    return t.startsWith(h) && /^\s+\d+$/.test(t.slice(h.length));
  };
  // Words, name, title and automation id: any of them saying delete, remove
  // or trash rules the control out, whatever else it says.
  const says = (b) => [text(b), b.getAttribute("aria-label"), b.getAttribute("title"),
    b.getAttribute("data-automation-id"), b.value].filter(Boolean).join(" ");
  const addLike = (b) => {
    if (!base().visible(b) || b.disabled || b.getAttribute("aria-disabled") === "true") return false;
    // A typeless <button> reports type "submit" everywhere, but submits only
    // inside a form: Workday's Add is one, outside any form. One DECLARED a
    // submit is refused anywhere.
    const submit = b.getAttribute("type")?.trim().toLowerCase() === "submit" || (b.type === "submit" && b.form);
    if (submit || b.closest("a[href]") || b.closest(CHROME)) return false;
    const auto = b.getAttribute("data-automation-id") ?? "";
    if (NEVER.test(says(b)) || (auto && auto !== "add-button" && NAV_ID.test(auto))) return false;
    return auto === "add-button" || ADD.test(text(b) || b.value || "");
  };

  // The section's own entries, visible, outermost first (never one inside
  // another). In a labelled group any group titled "… <n>" is one, even when
  // its words differ from the heading ("Job 1" under "Work History"):
  // counting one too few would ADD an entry too many, whose fields are
  // required; one too many only adds one too few.
  const entriesOf = (el, heading, aria) => {
    const found = aria
      ? [...el.querySelectorAll('[role="group"]')].filter((g) => /\S\s+\d+$/.test(titleOf(g)))
      : [...el.querySelectorAll(HEADING)].filter((h) => numbered(text(h), heading)).map((h) => {
        // The block the title heads: the highest ancestor below the section
        // that holds no other entry title.
        let node = h.parentElement;
        if (node === el) return h;
        const titles = (n) => [...n.querySelectorAll(HEADING)].filter((x) => numbered(text(x), heading)).length;
        while (node.parentElement !== el && titles(node.parentElement) === 1) node = node.parentElement;
        return node;
      });
    return found.filter((e) => base().visible(e) && !found.some((o) => o !== e && o.contains(e)));
  };
  // The section's own Add: inside it, in none of its entries and in no other
  // section nested inside it.
  const ownAdd = (el, entries) => [...el.querySelectorAll(BUTTON)].find((b) => {
    if (!addLike(b) || entries.some((e) => e.contains(b))) return false;
    const inner = b.closest(ARIA_SECTION);
    return !inner || inner === el;
  });
  // "Work Experience 2" titles an entry, never a section.
  const entryTitle = (heading) => /\s\d+$/.test(heading);

  // Every section in this frame, in page order: { el, heading, entries, button, aria }.
  const find = () => {
    const out = [];
    for (const el of document.querySelectorAll(ARIA_SECTION)) {
      const heading = labelledHeading(el);
      if (!heading || entryTitle(heading) || !base().visible(el)) continue;
      const entries = entriesOf(el, heading, true);
      const button = ownAdd(el, entries);
      if (button) out.push({ el, heading, entries, button, aria: true });
    }
    // A heading with no ARIA group around it: its container is the nearest
    // ancestor that holds entries titled after it and an Add of its own.
    for (const h of document.querySelectorAll(HEADING)) {
      const heading = text(h);
      if (!heading || entryTitle(heading) || h.closest(ARIA_SECTION) || !base().visible(h)) continue;
      let node = h.parentElement;
      for (let depth = 0; node && node !== document.body && depth < LEVELS; depth += 1, node = node.parentElement) {
        const entries = entriesOf(node, heading, false);
        if (!entries.length) continue;
        const button = ownAdd(node, entries);
        if (button && !out.some((s) => s.el.contains(node) || node.contains(s.el))) out.push({ el: node, heading, entries, button, aria: false });
        break;
      }
    }
    return out.sort((a, b) => (a.el.compareDocumentPosition(b.el) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1));
  };

  // `fields`: the inventory's, so "holds a value" means what the loop's
  // "answered" means (a set: any item). `held`: per entry, the committed
  // values of its answered fields (at most MAX_HELD, HELD_CHARS each) — for
  // the LOCAL backend to match entries to profile entries before any Add
  // (/sections never passes them to a model).
  const MAX_HELD = 10;
  const HELD_CHARS = 200;
  const list = (fields) => {
    const held = (fields ?? []).filter((f) => f.answered || (Array.isArray(f.committed) && f.committed.length))
      .map((f) => [ns.fillInventory.resolve(f.fid), [f.committed].flat()]).filter(([n]) => n);
    const holds = (e) => held.filter(([n]) => e.contains(n)).flatMap(([, values]) => values)
      .map((v) => String(v ?? "").trim()).filter(Boolean).slice(0, MAX_HELD).map((v) => v.slice(0, HELD_CHARS));
    return find().map(({ el, heading, entries, button }) => ({
      sid: mint(el), heading, entries: entries.length,
      filled: entries.map((e) => held.some(([n]) => e.contains(n))),
      held: entries.map(holds),
      add: text(button) || button.value || "",
    }));
  };

  // Press the section's own Add ONCE — a deliberate write, never a trial — on
  // the view it was decided on: the same heading and entry count, else
  // `stale` and nothing pressed. `added` only when the entry count grew.
  const ADD_WAIT_MS = 2500;
  const add = async (sid, { heading, entries }, t) => {
    const el = bySid.get(sid)?.deref();
    const now = el?.isConnected ? find().find((s) => s.el === el) : null;
    if (!now) return { outcome: "stale", entries: null };
    if (now.heading !== heading || now.entries.length !== entries) return { outcome: "stale", entries: now.entries.length };
    base().check(t);
    now.button.scrollIntoView?.({ block: "center" });
    base().press(now.button, t);
    const count = () => entriesOf(el, heading, now.aria).length;
    const grew = await base().waitFor(() => count() > entries, ADD_WAIT_MS, t);
    return { outcome: grew ? "added" : "not_added", entries: count() };
  };

  ns.fillSections = { list, add };
})();
