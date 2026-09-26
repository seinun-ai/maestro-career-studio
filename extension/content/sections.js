/* Maestro CS Companion — repeating sections and their own Add buttons.
 *
 * A repeating section (Work Experience, Education, Websites…) grows only when
 * its own Add button is pressed, and an added entry's fields are REQUIRED
 * (notes §5): the loop asks the backend how many entries the profile can fill
 * and presses Add for the difference, one press at a time, through fill-ops.
 *
 * A SECTION OWNS an Add button, and is one of two shapes:
 * - a `role=group` labelled (`aria-labelledby`) by a heading — Workday's
 *   `div[role=group][aria-labelledby=<h4 "Websites">]`. Its ENTRIES are the
 *   visible groups inside it titled "… <n>" (whatever their words: counting
 *   one too few would add one too many, with required fields);
 * - a heading, with no labelled group around it, whose STRETCH (from it to
 *   the next heading of its level or higher) holds entries titled
 *   "<Heading> <n>". Its container is the nearest ancestor (within three
 *   levels) holding them; two such sections may share one container. An
 *   entry is the block its title heads, or — when the title sits directly in
 *   the container — the run of the page up to the next title.
 * A numbered title is `ns.repeatOf`'s (field-reader.js): "Step 2", "Page 3"
 * and "… of 4" are never entries. A hidden prototype entry is not one.
 * Its Add button is its OWN: in the section (in the stretch, for a heading —
 * after its last entry title when entries sit flat in the container, the
 * last one there), inside no entry block and no other labelled group, reading
 * /^add( another)?\b/i or marked `data-automation-id="add-button"`. Never a
 * form's submit or a declared one, a control inside a link, the page's
 * header/nav/footer, and never anything whose words, name or automation id
 * say delete, remove or trash — Workday's Delete has no name at all, and it
 * is inside the entry, where no Add is looked for. What leaves this file is
 * text and counts, never an element: a Delete control cannot be returned,
 * only the section's own Add can be pressed, and only here.
 *
 * NOT SEEN: sections inside shadow roots (the walk is `document`'s own).
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
  const headingsIn = (root) => [...root.querySelectorAll(ns.ANY_HEADING)];
  // A numbered title's base, lowercased ("work experience" for "Work Experience 2"), else null.
  const baseOf = (title) => ns.repeatOf(title)?.base.toLowerCase() ?? null;
  const precedes = (a, b) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
  const level = (h) => (/^H[1-6]$/.test(h.tagName) ? Number(h.tagName[1]) : Number(h.getAttribute("aria-level")) || 2);

  // A section's sid is minted on its KEY element: the labelled group, or the
  // heading (two heading sections may share one container).
  const sidOf = new WeakMap(); // key element -> sid
  const bySid = new Map(); // sid -> { ref: WeakRef(key element), aria }
  let counter = 0;
  const mint = (key, aria) => {
    if (!sidOf.has(key)) {
      const sid = `${ns.fillInventory.frame}-s${(counter += 1)}`;
      sidOf.set(key, sid);
      bySid.set(sid, { ref: new WeakRef(key), aria });
    }
    return sidOf.get(key);
  };

  // A labelledby heading's words, or null when it names no heading.
  const labelledHeading = (el) => {
    const ids = (el.getAttribute("aria-labelledby") ?? "").split(/\s+/).filter(Boolean);
    const heads = ids.map((id) => ns.byIdIn(el, id)).filter((h) => h?.matches(ns.ANY_HEADING));
    return heads.length ? ns.readFieldText(heads.map(text).join(" ")) : null;
  };
  // An entry's title: its label, else its first heading.
  const titleOf = (el) => labelledHeading(el) || ns.readFieldText(el.getAttribute("aria-label") ?? "")
    || text(el.querySelector(ns.ANY_HEADING));
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
  // The Adds in `root` that `mine` admits, in no entry BLOCK and no other
  // labelled group (`group`: the section's own, or none), in page order.
  const ownAdds = (root, entries, group, mine = () => true) => [...root.querySelectorAll(BUTTON)].filter((b) => mine(b)
    && addLike(b) && !entries.some((e) => e.block && e.el.contains(b)) && (b.closest(ARIA_SECTION) ?? null) === group);

  // ---- the two shapes: { key, aria, heading, entries: [{ el, block, has(node) }], button } or null.
  // A section is one only with an Add of its own — except when re-read after
  // its own press (`again`), since some sections hide their Add once full.
  const ariaSection = (el, needAdd = true) => {
    const heading = labelledHeading(el);
    if (!heading || ns.repeatOf(heading) || !base().visible(el)) return null;
    const groups = [...el.querySelectorAll('[role="group"]')].filter((g) => ns.repeatOf(titleOf(g)) && base().visible(g));
    const entries = groups.filter((g) => !groups.some((o) => o !== g && o.contains(g)))
      .map((g) => ({ el: g, block: true, has: (n) => g.contains(n) }));
    const button = ownAdds(el, entries, el)[0] ?? null;
    return button || !needAdd ? { key: el, aria: true, heading, entries, button } : null;
  };
  const headingSection = (h, heads, needAdd = true) => {
    const heading = text(h);
    const own = heading.toLowerCase();
    if (h.closest(ARIA_SECTION) || !base().visible(h)) return null;
    // The stretch: up to the next heading of this level or higher that is not one of its entry titles.
    const end = heads.slice(heads.indexOf(h) + 1).find((x) => level(x) <= level(h) && baseOf(text(x)) !== own) ?? null;
    const inStretch = (n) => precedes(h, n) && (!end || precedes(n, end));
    let container = h.parentElement;
    let titles = [];
    for (let depth = 0; container && container !== document.body && depth < LEVELS; depth += 1) {
      titles = headingsIn(container).filter((x) => baseOf(text(x)) === own && inStretch(x));
      if (titles.length) break;
      container = container.parentElement;
    }
    if (!titles.length) return null;
    const titlesIn = (n) => titles.filter((x) => n.contains(x)).length;
    const entries = titles.map((t, k) => {
      let node = t.parentElement;
      if (node === container) {
        // Flat: the title sits in the container itself; the entry runs to the next title (or the stretch's end).
        const next = titles[k + 1] ?? end;
        return { el: t, block: false, has: (n) => container.contains(n) && precedes(t, n) && (!next || precedes(n, next)) };
      }
      while (node.parentElement !== container && titlesIn(node.parentElement) === 1) node = node.parentElement;
      return { el: node, block: true, has: (n) => node.contains(n) };
    }).filter((e) => base().visible(e.el));
    // Nothing marks where a FLAT entry ends, so an Add-like button inside one
    // ("Add responsibility") could pass for the section's: with flat entries,
    // only a button after the last entry title counts, and the last one wins.
    const last = titles.at(-1);
    const flat = entries.some((e) => !e.block);
    const button = ownAdds(container, entries, null, (b) => inStretch(b) && (!flat || precedes(last, b))).at(-1) ?? null;
    return button || !needAdd ? { key: h, aria: false, heading, entries, button } : null;
  };

  // Every section in this frame, in page order. Only headings some numbered
  // title names are looked at, so a page with no repeating section costs one
  // pass over its headings.
  const find = () => {
    const out = [];
    for (const el of document.querySelectorAll(ARIA_SECTION)) {
      const s = ariaSection(el);
      if (s) out.push(s);
    }
    const heads = headingsIn(document);
    const named = new Set(heads.map((h) => baseOf(text(h))).filter(Boolean));
    for (const h of heads) {
      if (!named.has(text(h).toLowerCase())) continue;
      const s = headingSection(h, heads);
      if (s) out.push(s);
    }
    return out.sort((a, b) => (precedes(a.key, b.key) ? -1 : 1));
  };
  // ONE section again, by its sid — its Add not required — for what `add`
  // checks and counts, without a whole find().
  const again = (sid) => {
    const entry = bySid.get(sid);
    const key = entry?.ref.deref();
    if (!key?.isConnected) return null;
    return entry.aria ? ariaSection(key, false) : headingSection(key, headingsIn(document), false);
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
    const holds = (e) => held.filter(([n]) => e.has(n)).flatMap(([, values]) => values)
      .map((v) => String(v ?? "").trim()).filter(Boolean).slice(0, MAX_HELD).map((v) => v.slice(0, HELD_CHARS));
    return find().map(({ key, aria, heading, entries, button }) => ({
      sid: mint(key, aria), heading, entries: entries.length,
      filled: entries.map((e) => held.some(([n]) => e.has(n))),
      held: entries.map(holds),
      add: text(button) || button.value || "",
    }));
  };

  // Press the section's own Add ONCE — a deliberate write, never a trial — on
  // the view it was decided on: the same heading and entry count, else
  // `stale` and nothing pressed. `added` only when the entry count grew.
  const ADD_WAIT_MS = 2500;
  const add = async (sid, { heading, entries }, t) => {
    const now = again(sid);
    if (!now?.button) return { outcome: "stale", entries: now?.entries.length ?? null };
    if (now.heading !== heading || now.entries.length !== entries) return { outcome: "stale", entries: now.entries.length };
    base().check(t);
    now.button.scrollIntoView?.({ block: "center" });
    base().press(now.button, t);
    const count = () => again(sid)?.entries.length ?? 0;
    const grew = await base().waitFor(() => count() > entries, ADD_WAIT_MS, t);
    return { outcome: grew ? "added" : "not_added", entries: count() };
  };

  ns.fillSections = { list, add };
})();
