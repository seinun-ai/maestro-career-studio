/* Maestro CS Companion — the generic fill mechanics.
 *
 * Two kinds of field. TEXT-LIKE: type like a person (fillBase.typeText), one
 * blur per widget (date sections are written first, then blurred once), then
 * verify. CHOICE-LIKE: passive shapes (select, radio/checkbox) act directly;
 * popup shapes OPEN (press, or type a term for search shapes), read the options
 * of the popup they OWN (scrolling long lists), and either close (explore) or
 * click one (commit: press, then click as a second gesture), blur, close, and
 * verify. Verify always runs after the final blur and treats a field error as
 * not filled. What the generic path cannot finish it reports as `unexpected`
 * with a reason; the loop's adaptive step takes it from there.
 *
 * Every popup the engine opens or reads is MARKED (fillBase.markEnginePopup) —
 * including the menu a widget re-renders on every keystroke — because
 * closePopups only ever closes marked popups. Every option text is run through
 * the never-fill policy: a blocked option is never clicked or ticked.
 *
 * THE ADAPTIVE STEP (stepState/move) is for a popup widget the generic path
 * could not finish. stepState reports the field's state now and the moves code
 * allows — click:<oid> (never a blocked option, never an item a multi widget
 * already holds), search:value, search:word:<n>, open, scroll, close, give_up —
 * under a fresh VERSION. The model chooses one of those ids; move() acts only
 * on the state it was chosen from, consumes that state (one move per state),
 * refuses an id the state did not offer, and treats a click on a list that
 * changed since as stale. A filtered search view is never complete.
 *
 * Nothing here catches errors: fill-ops turns a throw (Cancelled, Unfocusable,
 * a refused editable box) into an outcome.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  // LOAD ONCE. panel_prepare re-injects every content script into the SAME
  // isolated world; a second run would reset this module's state (see
  // INTERNALS.md, "A tab that was already open…").
  const loaded = (ns.loadedOnce ??= new Set());
  if (loaded.has("content/fill-core.js")) return;
  loaded.add("content/fill-core.js");
  const b = () => ns.fillBase;
  const OPEN_MS = 2500; // a pressed widget's popup, or a typed search's results
  const SEARCH_OPEN_MS = 1000; // a search box pressed with no term may show nothing at all
  const EMPTY_MS = 600; // a popup that lists nothing and is not loading this long is empty
  const CLEANUP_WAIT_MS = 500; // a cancelled search's debounce, waited out before closing
  const BUSY = /^(loading|searching)/i;
  const OPTIONISH = '[role="option"], [role="menuitem"], [role="treeitem"], [role="menuitemradio"], [role="menuitemcheckbox"]';
  const INNER_SEARCH = 'input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"])';
  // A commit that deliberately left a popup open (a category's children):
  // el -> { pop, before }. Iterable so fill-ops can close them before any
  // other field is touched.
  const leftOpen = new Map();
  const opened = new WeakMap(); // el -> the page's popups before the engine last opened it
  const typed = new WeakMap(); // el -> { prior, query }: a search query the engine typed
  const searched = new WeakSet(); // fields whose held popup shows FILTERED results (a search move)

  const blockedText = (text, consentForms) => Boolean(ns.isPolicyBlocked?.(text ?? "", { consentForms }));
  const flag = (options, consentForms) => options.map(({ oid, text, selected }) => ({
    oid, text, selected: Boolean(selected), policyBlocked: blockedText(text, consentForms),
  }));
  const same = (x, y) => JSON.stringify(x) === JSON.stringify(y);
  // The option a decision named: its exact text, else the one equivalent
  // (case/space/accent-folded) text. Two candidates is no answer.
  const match = (options, text) => {
    const exact = options.filter((o) => o.text === text);
    return exact.length ? exact : options.filter((o) => b().equivalent(o.text, text));
  };

  const parseDate = (v) => {
    const m = /^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$/.exec(String(v ?? "").trim());
    return m ? { year: m[1], month: m[2] ?? "", day: m[3] ?? "" } : null;
  };
  const formatPattern = (pattern, d) => pattern.replace(/yyyy/i, d.year).replace(/mm/i, d.month).replace(/dd/i, d.day);

  const verify = (el, shape, expected, { format } = {}) => {
    if (!el.isConnected) return "stale";
    if (b().invalid(el)) return "reverted";
    const have = [shape.read(el)].flat();
    if (shape.name === "date") {
      const want = parseDate(expected);
      if (shape.dateKind(el) === "pattern") {
        return want && el.value === formatPattern(el.getAttribute("placeholder"), want) ? "verified" : "reverted";
      }
      const got = parseDate(have[0]);
      // Every part the fact HAS must match; parts the fact lacks are never invented.
      return got && want && got.year === want.year && (!want.month || got.month === want.month)
        && (!want.day || got.day === want.day) ? "verified" : "reverted";
    }
    return [expected].flat().every((w) => have.some((h) => b().equivalent(h, w, { format }))) ? "verified" : "reverted";
  };

  const blurOut = async (el, t) => {
    b().check(t);
    el.blur?.();
    await b().settle(t, 150);
  };

  // ---- text-like
  async function write(el, shape, value, t, { format } = {}) {
    if (shape.kind !== "text") return { outcome: "unexpected", reason: "not_text" };
    if (shape.name === "date") {
      const d = parseDate(value);
      if (!d) return { outcome: "unexpected", reason: "not_a_date" };
      const kind = shape.dateKind(el);
      const placeholder = el.getAttribute("placeholder") ?? "";
      // Never manufacture precision: a widget that asks for a part the fact
      // does not have (a day, or a month) is left for the user.
      const asks = kind === "sections" ? shape.dateSections(el).map(shape.partOf)
        : kind === "date" ? ["year", "month", "day"] : kind === "month" ? ["year", "month"]
          : ["yyyy", "mm", "dd"].filter((p) => new RegExp(p, "i").test(placeholder))
            .map((p) => ({ yyyy: "year", mm: "month", dd: "day" })[p]);
      if (asks.some((part) => !d[part])) return { outcome: "unexpected", reason: "needs_more_date_precision" };
      if (kind === "sections") {
        const parts = shape.dateSections(el);
        for (const s of parts) b().typeText(s, d[shape.partOf(s)], t);
        await blurOut(parts.at(-1), t);
      } else {
        b().typeText(el, kind === "month" ? `${d.year}-${d.month}` : kind === "date" ? `${d.year}-${d.month}-${d.day}`
          : formatPattern(placeholder, d), t);
        await blurOut(el, t);
      }
    } else {
      b().typeText(el, String(value ?? ""), t);
      await blurOut(el, t);
    }
    return { outcome: verify(el, shape, value, { format }) };
  }

  // ---- choice-like: popups
  const own = (el, before) => {
    const pop = b().ownedPopup(el, before);
    b().markEnginePopup(pop);
    return pop;
  };
  const busy = (pop) => pop.getAttribute("aria-busy") === "true"
    || [...pop.querySelectorAll(OPTIONISH)].some((o) => BUSY.test(b().clean(o.textContent)));
  // The popup the element owns once it lists options — or once it has listed
  // nothing, without loading, for EMPTY_MS (an honest empty result). Every
  // popup seen on the way is marked: widgets re-render their menu per keystroke.
  const waitOptions = async (el, before, t) => {
    let emptySince = null;
    const pop = await b().waitFor(() => {
      const p = own(el, before);
      if (!p || busy(p)) {
        emptySince = null;
        return p && b().optionsOf(p).length ? p : null;
      }
      if (b().optionsOf(p).length) return p;
      emptySince ??= Date.now();
      return Date.now() - emptySince >= EMPTY_MS ? p : null;
    }, OPEN_MS, t);
    return pop ?? own(el, before);
  };
  // A query typed into the field's OWN box is remembered so tidy can take it
  // back; one typed into a search box inside the popup leaves with the popup.
  const typeQuery = async (box, term, t, { own: remember = false } = {}) => {
    if (remember && !typed.has(box)) typed.set(box, { prior: box.value ?? "", query: null });
    b().typeText(box, term, t);
    if (remember) typed.get(box).query = box.value;
    await b().settle(t, 100); // let a debounced search replace the old list first
  };
  const open = async (el, shape, term, t) => {
    const before = b().popups();
    opened.set(el, before);
    let searchable = shape.open === "search";
    // A search widget with a term is typed into, never pressed: some close
    // their results on a click in their own box.
    if (searchable && term) {
      await typeQuery(el, term, t, { own: true });
      return { pop: await waitOptions(el, before, t), before, searchable };
    }
    el.focus?.({ preventScroll: true });
    b().press(el, t);
    const pop = await b().waitFor(() => own(el, before), searchable ? SEARCH_OPEN_MS : OPEN_MS, t);
    if (!pop) return { pop: null, before, searchable };
    const box = pop.querySelector(INNER_SEARCH);
    if (box) searchable = true;
    if (term && box) await typeQuery(box, term, t);
    return { pop: await waitOptions(el, before, t), before, searchable };
  };
  const scrollerOf = (pop) => [pop, ...pop.querySelectorAll("*")]
    .find((n) => n.scrollHeight > n.clientHeight + 4 && /(auto|scroll)/.test(getComputedStyle(n).overflowY)) ?? null;
  const readAll = async (pop, t) => {
    const seen = new Map();
    const box = scrollerOf(pop);
    let complete = !box;
    for (let i = 0; i < 30; i += 1) {
      for (const o of b().optionsOf(pop)) if (!seen.has(o.text)) seen.set(o.text, o);
      if (complete) break;
      const top = box.scrollTop;
      box.scrollTop = top + box.clientHeight;
      await b().settle(t, 80);
      if (box.scrollTop === top) complete = true; // the next pass reads the last page, then stops
    }
    return { options: [...seen.values()].map((o, i) => ({ oid: `o${i + 1}`, text: o.text, selected: o.selected })), complete };
  };
  // The one option to click, scrolling a long list to find it.
  const findOption = async (pop, text, t) => {
    let hits = match(b().optionsOf(pop), text);
    const box = hits.length ? null : scrollerOf(pop);
    for (let i = 0; box && !hits.length && i < 30; i += 1) {
      const top = box.scrollTop;
      box.scrollTop = top + box.clientHeight;
      await b().settle(t, 80);
      hits = match(b().optionsOf(pop), text);
      if (box.scrollTop === top) break;
    }
    return hits.length === 1 ? hits[0] : null;
  };

  // Close what the engine opened. A search query the ENGINE typed, and only
  // while the box still holds exactly that query, is put back to what the box
  // held before; a value anybody else put there is never touched, and CLEANUP
  // (after a cancel or timeout) never types at all — it may only close popups
  // the engine opened.
  // In CLEANUP (after Stop or a timeout) taking back the engine's own query
  // is still allowed — it undoes the engine's write, nobody else's — and the
  // search it re-triggers is waited out (bounded) so no late result stays open.
  const tidy = async (el, t, { cleanup = false } = {}) => {
    leftOpen.delete(el);
    searched.delete(el);
    const before = opened.get(el);
    const q = typed.get(el);
    typed.delete(el);
    const restore = q && el.isConnected && el.value === q.query && q.prior !== q.query;
    if (restore) {
      b().typeText(el, q.prior, t, { undo: cleanup });
      const settled = () => !before || !own(el, before) || !busy(own(el, before));
      if (cleanup) {
        await b().sleep(120);
        for (const end = Date.now() + CLEANUP_WAIT_MS; !settled() && Date.now() < end;) await b().sleep(40);
      } else {
        await b().settle(t, 120);
        await b().waitFor(settled, OPEN_MS, t);
      }
    }
    if (before && el.isConnected) own(el, before); // a menu re-rendered by that typing
    await b().closePopups(el, t, { cleanup });
    if (!cleanup) await blurOut(el, t);
    else if (restore) el.blur?.(); // the undo focused the box: focus is not left in it
  };

  async function explore(el, shape, { term, consentForms } = {}, t) {
    if (shape.kind !== "choice") return { options: [], complete: false, searchable: false, error: "not_a_choice" };
    if (shape.passive) {
      const p = shape.passive(el);
      return { options: flag(p.options, consentForms), complete: p.complete, searchable: false };
    }
    b().check(t);
    let { pop, searchable } = await open(el, shape, term, t);
    let options = pop ? b().optionsOf(pop) : [];
    if (!options.length && term) {
      const word = term.split(/\s+/).find((w) => w.length > 2 && w !== term);
      if (word) {
        await tidy(el, t);
        ({ pop, searchable } = await open(el, shape, word, t));
        options = pop ? b().optionsOf(pop) : [];
      }
    }
    const got = pop && options.length ? await readAll(pop, t) : { options: [], complete: false };
    await tidy(el, t);
    // A filtered search view is never the complete list.
    const out = { options: flag(got.options, consentForms), complete: got.complete && !term, searchable };
    if (!got.options.length) out.error = pop ? "empty_popup" : "no_popup";
    return out;
  }

  // A hidden custom radio/checkbox is operated through its label.
  const clickTarget = (input) => (b().visible(input) ? input
    : (input.id && input.getRootNode().querySelector?.(`label[for="${CSS.escape(input.id)}"]`)) || input.closest("label") || input);
  const tick = (input, t) => {
    b().check(t);
    clickTarget(input).click();
  };
  const selectIndex = (el, index, t) => {
    b().check(t);
    el.focus({ preventScroll: true });
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "selectedIndex").set.call(el, index);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  };

  const addSelected = (el, opts, t) => {
    b().check(t);
    el.focus({ preventScroll: true });
    for (const o of opts) o.selected = true;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  };

  async function choosePassive(el, shape, text, t, consentForms) {
    const options = flag(shape.passive(el).options, consentForms);
    const hits = match(options, text);
    if (hits.length !== 1) return { outcome: "unexpected", reason: "option_missing", options };
    if (hits[0].policyBlocked) return { outcome: "blocked" };
    const want = hits[0].text;
    // The control behind the option, found again: an option the page dropped
    // since it was read is missing, not an error.
    if (shape.name === "select") {
      const opt = shape.realOptions(el).find((o) => b().clean(o.text) === want);
      if (!opt) return { outcome: "unexpected", reason: "option_missing", options };
      if (!opt.selected && el.multiple) addSelected(el, [opt], t); // the other selections stay
      else if (!opt.selected) selectIndex(el, opt.index, t);
    } else if (shape.lone(el)) {
      if (want !== "Yes" && want !== "No") return { outcome: "unexpected", reason: "option_missing", options };
      if (el.checked !== (want === "Yes")) tick(el, t);
    } else {
      const input = shape.members(el).find((m) => shape.labelOf(m) === want);
      if (!input) return { outcome: "unexpected", reason: "option_missing", options };
      if (!input.checked) tick(input, t);
    }
    await blurOut(el, t);
    return verify(el, shape, want) === "verified"
      ? { outcome: "verified", text: want } : { outcome: "unexpected", reason: "not_committed" };
  }

  const GESTURES = [(o, t) => b().press(o, t), (o, t) => {
    b().check(t);
    o.click();
  }];
  // Whether the field's committed value already holds this text — presence
  // only, whatever error the field shows.
  const holds = (el, shape, x) => [shape.read(el)].flat().some((h) => b().equivalent(h, x));
  // An item a multi widget already holds is never clicked (a click toggles it off).
  const alreadyThere = (el, shape, text) => ({
    outcome: verify(el, shape, text) === "verified" ? "verified" : "reverted", text,
  });

  async function choose(el, shape, { text, term, consentForms } = {}, t) {
    if (shape.kind !== "choice") return { outcome: "unexpected", reason: "not_a_choice" };
    if (blockedText(text, consentForms)) return { outcome: "blocked" };
    if (shape.passive) return choosePassive(el, shape, text, t, consentForms);
    const multi = Boolean(shape.multi?.(el));
    if (multi && holds(el, shape, text)) return alreadyThere(el, shape, text);
    const before0 = shape.read(el);
    for (const gesture of GESTURES) {
      const { pop, before } = await open(el, shape, shape.open === "search" ? (term ?? text) : term, t);
      if (!pop) {
        await tidy(el, t);
        return { outcome: "unexpected", reason: "no_popup" };
      }
      const hit = await findOption(pop, text, t);
      if (!hit) {
        const options = flag(b().optionsOf(pop), consentForms);
        await tidy(el, t);
        return { outcome: "unexpected", reason: options.length ? "option_missing" : "empty_popup", options };
      }
      if (blockedText(hit.text, consentForms)) {
        await tidy(el, t);
        return { outcome: "blocked" };
      }
      if (multi && (hit.selected || holds(el, shape, hit.text))) {
        await tidy(el, t);
        return alreadyThere(el, shape, hit.text);
      }
      const shown = b().optionsOf(pop).map((o) => o.text).join("\n");
      hit.el.scrollIntoView?.({ block: "nearest" });
      gesture(hit.el, t);
      await b().settle(t, 200);
      // The pick is committed: the query typed to find it is no longer the
      // engine's to take back (a free-text box whose pick equals the query).
      // Only when the box's own value IS the committed value: a widget that
      // shows the pick in a pill and leaves the query in its box still gets
      // the query taken back.
      if (holds(el, shape, hit.text) && [shape.read(el)].flat().includes(el.value)) typed.delete(el);
      const after = own(el, before);
      const next = after ? b().optionsOf(after) : [];
      if (next.length && next.map((o) => o.text).join("\n") !== shown && same(shape.read(el), before0)) {
        leftOpen.set(el, { pop: after, before });
        return { outcome: "unexpected", reason: "new_options", options: flag(next, consentForms) };
      }
      await tidy(el, t);
      if (verify(el, shape, hit.text) === "verified") return { outcome: "verified", text: hit.text };
      // Something else got committed: a second click could undo it (a chip
      // that un-picks on click). Only a click that changed nothing is retried.
      if (!same(shape.read(el), before0)) break;
    }
    return { outcome: "unexpected", reason: "not_committed" };
  }

  // Sets add, never remove: an existing choice is kept and never unticked,
  // and a set is verified only when EVERY requested item is committed. Items
  // the never-fill policy refuses are reported as `blocked`, apart from the
  // `missing` ones the page did not offer or did not take.
  async function set(el, shape, { texts = [], terms = [], consentForms } = {}, t) {
    if (shape.kind !== "choice" || !shape.multi?.(el)) return { outcome: "unexpected", reason: "not_a_set" };
    const options = shape.passive ? flag(shape.passive(el).options, consentForms) : null;
    // Blocked by its own text, or (passive) by the one option it names.
    const blocked = texts.filter((x) => blockedText(x, consentForms)
      || (options && match(options, x).length === 1 && match(options, x)[0].policyBlocked));
    const allowed = texts.filter((x) => !blocked.includes(x));
    if (texts.length && !allowed.length) return { outcome: "blocked", added: [], missing: [], blocked };
    const had = [shape.read(el)].flat();
    if (shape.passive) {
      const wanted = allowed.map((x) => match(options, x)).filter((h) => h.length === 1).map(([h]) => h.text);
      if (shape.name === "select") {
        const add = shape.realOptions(el).filter((o) => !o.selected && wanted.includes(b().clean(o.text)));
        if (add.length) addSelected(el, add, t);
      } else {
        for (const want of wanted) {
          const input = shape.members(el).find((m) => shape.labelOf(m) === want);
          if (input && !input.checked) {
            tick(input, t);
            await b().settle(t, 60);
          }
        }
      }
      await blurOut(el, t);
    } else {
      for (const [i, text] of texts.entries()) {
        if (!allowed.includes(text) || holds(el, shape, text)) continue;
        const got = await choose(el, shape, { text, term: terms[i] ?? text, consentForms }, t);
        if (got.outcome === "blocked") blocked.push(text); // the option shown for it is a never-fill one
        if (leftOpen.has(el)) await tidy(el, t); // a category is not an item: close it and move on
      }
    }
    // `added` is what THIS call added; `missing` what the field still lacks.
    const added = allowed.filter((x) => holds(el, shape, x) && !had.some((h) => b().equivalent(h, x)));
    const missing = allowed.filter((x) => !holds(el, shape, x) && !blocked.includes(x));
    if (b().invalid(el)) return { outcome: "reverted", added, missing, blocked };
    return { outcome: missing.length || blocked.length ? "partial" : "verified", added, missing, blocked };
  }

  // A text field holding a value the page shows an error on: commit its OWN
  // value again, the way a person would (Workday only takes real typing).
  async function recommit(el, shape, t) {
    if (shape.kind !== "text") return { outcome: "unexpected", reason: "not_text" };
    const value = shape.read(el);
    if (!value) return { outcome: "reverted" };
    return { ...(await write(el, shape, value, t)), text: value };
  }

  // ---- the adaptive step: the field's state now, and the moves code allows.
  const MAX_CLICKS = 50;
  const MAX_WORDS = 4; // the backend accepts search:word:0..9
  const GIVE_UP = { mid: "give_up", describe: "Stop: no move will select an option that states the value" };
  const lastState = new WeakMap(); // el -> { version, mids, clicks: [{oid, text}], value, words }
  let stateVersion = 0;
  const quote = (s) => (s.length > 200 ? `${s.slice(0, 199)}…` : s);
  const wordsOf = (value) => {
    const whole = String(value ?? "").trim();
    return [...new Set(whole.split(/[\s,/()&-]+/).filter((w) => w.length > 2 && w !== whole))].slice(0, MAX_WORDS);
  };
  // The popup a move (or a category commit) left open for this field, found
  // again if the widget re-rendered it; forgotten if the page closed it.
  const heldPopup = (el) => {
    const held = leftOpen.get(el);
    if (!held) return null;
    const pop = (el.isConnected ? own(el, held.before) : null) ?? (b().visible(held.pop) ? held.pop : null);
    if (!pop) {
      leftOpen.delete(el);
      searched.delete(el);
      return null;
    }
    b().markEnginePopup(pop);
    if (pop !== held.pop) leftOpen.set(el, { pop, before: held.before });
    return { pop, before: held.before };
  };
  // A search box inside the popup, else the field's own box when it is one.
  const searchBoxOf = (el, shape, pop) => {
    const inner = pop && [...pop.querySelectorAll(INNER_SEARCH)].find((n) => b().visible(n) && !n.readOnly && !n.disabled);
    return inner || (shape.open === "search" ? el : null);
  };
  // The options a click move may name: never a never-fill one, never an item a
  // multi widget already holds (a click would un-pick it). Capped.
  const clickable = (el, shape, pop, consentForms) => {
    const multi = Boolean(shape.multi?.(el));
    return b().optionsOf(pop)
      .filter((o) => !blockedText(o.text, consentForms) && !(multi && (o.selected || holds(el, shape, o.text))))
      .slice(0, MAX_CLICKS);
  };
  const ids = (options) => options.map(({ oid, text }) => ({ oid, text }));

  async function stepState(el, shape, { value, consentForms } = {}, t) {
    b().check(t);
    const version = (stateVersion += 1);
    // Passive shapes and text have no popup to explore: nothing but give_up.
    const adaptive = shape.kind === "choice" && !shape.passive;
    const held = adaptive ? heldPopup(el) : null;
    const all = held ? b().optionsOf(held.pop) : [];
    const clicks = held ? clickable(el, shape, held.pop, consentForms) : [];
    const box = adaptive ? searchBoxOf(el, shape, held?.pop) : null;
    const whole = String(value ?? "").trim();
    const words = box ? wordsOf(whole) : [];
    const scroller = held ? scrollerOf(held.pop) : null;
    const more = Boolean(scroller) && scroller.scrollTop + scroller.clientHeight < scroller.scrollHeight - 4;
    const candidates = adaptive ? [
      ...clicks.map((o) => ({ mid: `click:${o.oid}`, describe: `Click the option "${quote(o.text)}"` })),
      ...(box && whole ? [{ mid: "search:value", describe: "Type the applicant value into the search box" }] : []),
      ...words.map((w, i) => ({ mid: `search:word:${i}`, describe: `Type "${quote(w)}" into the search box` })),
      ...(held ? [] : [{ mid: "open", describe: "Open the dropdown" }]),
      ...(more ? [{ mid: "scroll", describe: "Scroll the list to see more options" }] : []),
      ...(held ? [{ mid: "close", describe: "Close the dropdown" }] : []),
      GIVE_UP,
    ] : [GIVE_UP];
    lastState.set(el, { version, mids: new Set(candidates.map((c) => c.mid)), clicks: ids(clicks), value: whole, words });
    // Complete = every option is in view: not capped, nothing to scroll, and
    // not a filtered search result (a search widget's list always is one).
    const complete = Boolean(held) && shape.open !== "search" && !searched.has(el)
      && all.length <= MAX_CLICKS && !scroller;
    return {
      version, complete, committed: shape.read(el), invalid: b().invalid(el), popupOpen: Boolean(held),
      options: flag(all.slice(0, MAX_CLICKS), consentForms), candidates,
    };
  }

  // One move against the state it was chosen from (`version`). Outcomes:
  // verified (a click committed), progressed (the page moved on: a popup
  // opened, a search listed results, a category showed its children, the list
  // scrolled), closed, stale, unexpected (with a reason), blocked.
  async function move(el, shape, { mid, version, consentForms } = {}, t) {
    b().check(t);
    const last = lastState.get(el);
    const closing = mid === "give_up" || mid === "close";
    // Closing what the engine opened is allowed from any state.
    if (!closing && (!last || last.version !== version)) return { outcome: "stale" };
    lastState.delete(el); // consumed: the next move needs a fresh state
    if (closing) {
      await tidy(el, t);
      return { outcome: "closed" };
    }
    if (!last.mids.has(mid)) return { outcome: "unexpected", reason: "not_offered" };
    const held = heldPopup(el);
    if (mid === "open") {
      const o = await open(el, shape, undefined, t);
      if (!o.pop) {
        await tidy(el, t);
        return { outcome: "unexpected", reason: "no_popup" };
      }
      leftOpen.set(el, { pop: o.pop, before: o.before });
      return { outcome: "progressed" };
    }
    if (mid === "scroll") {
      const box = held && scrollerOf(held.pop);
      if (!box) return { outcome: "stale" };
      b().check(t);
      const top = box.scrollTop;
      box.scrollTop = top + box.clientHeight;
      await b().settle(t, 120);
      return box.scrollTop === top ? { outcome: "unexpected", reason: "list_end" } : { outcome: "progressed" };
    }
    if (mid.startsWith("search:")) {
      const box = searchBoxOf(el, shape, held?.pop);
      const term = mid === "search:value" ? last.value : last.words[Number(mid.slice("search:word:".length))];
      if (!box || !term) return { outcome: "unexpected", reason: "no_search_box" };
      const before = held?.before ?? b().popups();
      if (!held) opened.set(el, before);
      await typeQuery(box, term, t, { own: box === el });
      searched.add(el);
      const pop = await waitOptions(el, before, t);
      if (!pop) return { outcome: "unexpected", reason: "no_popup" };
      leftOpen.set(el, { pop, before });
      return b().optionsOf(pop).length ? { outcome: "progressed" } : { outcome: "unexpected", reason: "no_results" };
    }
    if (mid.startsWith("click:")) {
      // The popup must still show the list the decision was made on.
      const now = held ? clickable(el, shape, held.pop, consentForms) : [];
      if (!held || !same(ids(now), last.clicks)) return { outcome: "stale" };
      const hit = now.find((o) => `click:${o.oid}` === mid);
      const before0 = shape.read(el);
      const shown = b().optionsOf(held.pop).map((o) => o.text).join("\n");
      hit.el.scrollIntoView?.({ block: "nearest" });
      for (const gesture of GESTURES) {
        gesture(hit.el, t);
        await b().settle(t, 200);
        const after = own(el, held.before) ?? (b().visible(held.pop) ? held.pop : null);
        const next = after ? b().optionsOf(after).map((o) => o.text).join("\n") : "";
        const unchanged = same(shape.read(el), before0);
        if (next && next !== shown && unchanged) { // a category: its children are the next state
          leftOpen.set(el, { pop: after, before: held.before });
          return { outcome: "progressed" };
        }
        // Only a click that changed nothing at all gets the second gesture.
        if (!unchanged || next !== shown || !hit.el.isConnected) break;
      }
      if (holds(el, shape, hit.text) && [shape.read(el)].flat().includes(el.value)) typed.delete(el);
      await tidy(el, t);
      return verify(el, shape, hit.text) === "verified"
        ? { outcome: "verified", text: hit.text } : { outcome: "unexpected", reason: "not_committed" };
    }
    return { outcome: "unexpected", reason: "unknown_move" };
  }

  ns.fillCore = {
    write, explore, choose, set, recommit, verify, tidy, open, readAll, own, leftOpen, stepState, move,
  };
})();
