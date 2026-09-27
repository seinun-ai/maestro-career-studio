/* Maestro CS Companion — the recipe book: which moves worked, per widget family.
 *
 * Panel-side and pure: it touches no `document`, `location` or `chrome`. The
 * panel keeps the book under one `chrome.storage.local` key (`fill.recipes`,
 * panel.js) and hands the fill loop `store(...)` as `deps.recipes`.
 *
 * A RECIPE REORDERS THE ENGINE'S OWN VARIANTS, and nothing else: which of a
 * widget family's known moves to try first — `open: press | keys` (a press,
 * or the keyboard), `search: enter | debounce` (an Enter after the typing, or
 * a wait for the widget's own filter). It is a proposal to the field's one
 * controller, never an executor: every gate still decides (the Enter gate, the
 * `reacted` lockout, the budget), the other move is still the fallback, and
 * verification is unchanged. `click` and `leave` are not axes: the engine has
 * no fallback there (a tick is a toggle; a date is left from inside its
 * widget), so reordering them would be an experiment, not a shortcut.
 *
 * VALUE-FREE BY CONSTRUCTION. Keys are hashes the page made of the widget's
 * STRUCTURE (content/recipes.js): `f:<family>` and `s:<site>` (the family on
 * one host). An entry holds only the moves (known words), its state, counts,
 * the site keys that proved a family, and the DAY it was last kept. `clean`
 * drops anything else on every read, so no label, value or URL survives in it.
 *
 * THE LIFECYCLE. Only a move the page VERIFIED, that nothing reverted and
 * that the final sweep re-checked and found holding is learned (a lesson
 * `kept`, fill-loop.js), and only a move other than the
 * generic one (a generic win teaches nothing):
 * - the first kept run → `probation`, at the site and the family;
 * - a site's recipe is `trusted` after TWO kept runs (one run counts once,
 *   however many fields it kept);
 * - a family's is `trusted` only once two SITES kept it; it is tried on a new
 *   site only then (a probation recipe is tried on its own site only);
 * - a lesson that contradicts it (the move produced an unconfirmed or
 *   reverted value, or the other move won) → `demoted`, never tried again;
 * - a learned move the control could not take (a structural mismatch the
 *   signature missed) → `quarantined`, never tried again;
 * - an entry not kept for TTL_DAYS expires, demoted ones included, and the
 *   book holds at most LIMIT entries, the least recently kept going first.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const VERSION = 1;
  const LIMIT = 200;
  const TTL_DAYS = 60;
  const DAY_MS = 24 * 60 * 60 * 1000;
  // Each axis's moves, the generic (first) one first: the order the engine
  // uses with no recipe.
  const AXES = { open: ["press", "keys"], search: ["enter", "debounce"] };
  const STATES = new Set(["probation", "trusted", "demoted", "quarantined"]);
  const TRIED = new Set(["probation", "trusted"]);
  const KEY = /^[sf]:[0-9a-z]{1,24}$/;
  const MAX_SITES = 4;
  const count = (n) => Number.isInteger(n) && n >= 0;

  const empty = () => ({ v: VERSION, entries: {} });
  // Only the moves an axis knows.
  const movesOf = (raw) => Object.fromEntries(Object.entries(raw && typeof raw === "object" ? raw : {})
    .filter(([axis, move]) => AXES[axis]?.includes(move)));
  // The moves a lesson teaches: the known ones that are not the generic move.
  const learnt = (moves) => Object.fromEntries(Object.entries(movesOf(moves)).filter(([axis, move]) => move !== AXES[axis][0]));
  const cleanEntry = (key, e) => {
    if (!KEY.test(key) || !e || typeof e !== "object" || !STATES.has(e.state) || !count(e.seen)) return null;
    const moves = movesOf(e.moves);
    if (!Object.keys(moves).length) return null;
    const out = { moves, state: e.state };
    if (key.startsWith("s:")) out.wins = count(e.wins) ? e.wins : 1;
    else out.sites = (Array.isArray(e.sites) ? e.sites : []).filter((s) => typeof s === "string" && KEY.test(s)
      && s.startsWith("s:")).slice(0, MAX_SITES);
    out.seen = e.seen;
    return out;
  };
  // What a stored book may hold, and nothing more: a book of another version,
  // or anything unreadable, is an empty one.
  const clean = (raw) => {
    if (!raw || typeof raw !== "object" || raw.v !== VERSION || !raw.entries || typeof raw.entries !== "object") {
      return empty();
    }
    const entries = {};
    for (const [key, e] of Object.entries(raw.entries)) {
      const got = cleanEntry(key, e);
      if (got) entries[key] = got;
    }
    return { v: VERSION, entries };
  };
  const live = (e, today) => Boolean(e) && today - e.seen <= TTL_DAYS;
  const orderOf = (moves) => Object.fromEntries(Object.entries(moves)
    .map(([axis, move]) => [axis, [move, ...AXES[axis].filter((m) => m !== move)]]));

  // The order to try for a widget (`recipe`: the page's { family, site }
  // keys), or null for the generic order. Its site's recipe while that is
  // tried; else the family's once trusted — unless its site's was demoted or
  // quarantined, which speaks for this site.
  const consult = (raw, recipe, today) => {
    const { entries } = clean(raw);
    const site = live(entries[recipe?.site], today) ? entries[recipe.site] : null;
    if (site) return TRIED.has(site.state) ? { key: recipe.site, variant: orderOf(site.moves) } : null;
    const family = live(entries[recipe?.family], today) ? entries[recipe.family] : null;
    return family?.state === "trusted" ? { key: recipe.family, variant: orderOf(family.moves) } : null;
  };

  // Whether a lesson's moves agree with an entry's: every axis the entry
  // names, the lesson either did not exercise or moved the same way.
  const agrees = (e, moves) => Object.entries(e.moves).every(([axis, move]) => moves[axis] === undefined || moves[axis] === move);

  // A new book from `raw` and one run's lessons ({ recipe, used, moves,
  // outcome: kept | contradicted | mismatch }). Kept lessons first, so a run
  // that both kept and contradicted a move ends with it demoted.
  const learn = (raw, lessons, today) => {
    const entries = new Map(Object.entries(clean(raw).entries).filter(([, e]) => live(e, today)));
    // Re-inserted when kept, so the map's order is least recently kept first.
    const put = (key, e) => {
      entries.delete(key);
      entries.set(key, e);
    };
    const demote = (key, state = "demoted") => {
      const e = entries.get(key);
      if (e) entries.set(key, { ...e, state });
    };
    const won = new Set(); // one run is one success, however many fields it kept
    const all = (Array.isArray(lessons) ? lessons : []).filter((l) => l && KEY.test(l.recipe?.family ?? "")
      && KEY.test(l.recipe?.site ?? ""));
    for (const { recipe, moves: said } of all.filter((l) => l.outcome === "kept")) {
      const moves = movesOf(said);
      const teach = learnt(moves);
      for (const key of [recipe.site, recipe.family]) {
        const e = entries.get(key);
        if (e && !TRIED.has(e.state)) continue; // demoted and quarantined stay so until they expire
        if (e && !agrees(e, moves)) { // the other move won
          demote(key);
          continue;
        }
        if (!Object.keys(teach).length) continue; // nothing a recipe holds was exercised
        const was = e ?? { moves: {}, state: "probation", ...(key === recipe.site ? { wins: 0 } : { sites: [] }) };
        const next = { ...was, moves: { ...was.moves, ...teach }, seen: today };
        if (key === recipe.site) {
          if (!won.has(key)) next.wins = was.wins + 1;
          if (next.wins >= 2) next.state = "trusted";
        } else {
          if (!was.sites.includes(recipe.site)) next.sites = [...was.sites, recipe.site].slice(-MAX_SITES);
          if (next.sites.length >= 2) next.state = "trusted";
        }
        won.add(key);
        put(key, next);
      }
    }
    for (const { recipe, used, moves: said, outcome } of all.filter((l) => l.outcome !== "kept")) {
      if (outcome === "mismatch") {
        if (used) demote(used, "quarantined");
        continue;
      }
      if (outcome !== "contradicted") continue;
      const teach = learnt(said);
      // The recipe that was tried, and any entry that teaches the move that
      // just produced a value the page did not keep.
      for (const key of [recipe.site, recipe.family]) {
        const e = entries.get(key);
        if (e && TRIED.has(e.state) && (key === used || (Object.keys(teach).length && agrees(e, teach)))) demote(key);
      }
    }
    // Bounded: the least recently kept go first.
    const keys = [...entries.keys()].sort((x, y) => entries.get(x).seen - entries.get(y).seen);
    for (const key of keys.slice(0, Math.max(0, entries.size - LIMIT))) entries.delete(key);
    return { v: VERSION, entries: Object.fromEntries(entries) };
  };

  const size = (raw) => Object.keys(clean(raw).entries).length;

  // The fill loop's `deps.recipes` over a store: `read()` / `write(book)` are
  // the panel's storage (async; a failed read is an empty book), `today()`
  // the day number. The book is read once for a run's lookups and again right
  // before its one write, so a book another run wrote meanwhile is kept.
  const store = ({ read, write, today = () => Math.floor(Date.now() / DAY_MS) }) => {
    const load = async () => {
      try {
        return clean(await read());
      } catch {
        return empty();
      }
    };
    let book = null;
    return {
      get: async (recipe) => consult((book ??= await load()), recipe, today()),
      record: async (lessons) => {
        if (!Array.isArray(lessons) || !lessons.length) return;
        book = learn(await load(), lessons, today());
        await write(book);
      },
    };
  };

  ns.recipeBook = { VERSION, LIMIT, TTL_DAYS, AXES, clean, consult, learn, size, store };
})();
