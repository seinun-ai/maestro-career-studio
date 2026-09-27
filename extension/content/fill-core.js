/* Maestro CS Companion — the generic fill mechanics.
 *
 * Two kinds of field. TEXT-LIKE: type like a person (fillBase.typeText), one
 * leave per widget (date sections are written first, then left once, from
 * whichever section holds focus by then), then verify. CHOICE-LIKE: passive
 * shapes (select, radio/checkbox) act directly; popup shapes OPEN (press, or
 * the search sequence below for search shapes), read the options of the
 * popup they OWN (scrolling long lists a frame at a time), and either close
 * (explore) or click one (commit: the radio or checkbox inside the option
 * where it holds one — once, a tick is a toggle — else press, then click as a
 * second gesture), leave, close, and verify. Verify always runs after the
 * final leave and treats a field error as not filled. What the generic path
 * cannot finish it reports as `unexpected` with a reason; the loop's adaptive
 * step takes it from there.
 *
 * THE SEARCH SEQUENCE (notes §2) is how a person searches a Workday box:
 * press it and wait for its list, type the term (over any query already
 * there — a set's items share one open list), press Enter where the widget
 * searches on it, and wait until the row TEXTS change from what the list
 * showed and then stop changing (results arrive in stages, in row nodes the
 * list reuses). An Enter that found one hit may commit it on its own: the
 * evidence is read before anything is clicked. Identical option texts are
 * one option only under one visible category path; otherwise they are
 * listed apart, named by place in the click moves, and a choose by text is
 * `ambiguous`.
 *
 * VERIFY reads each widget's committed evidence (shapes `evidence`): the
 * display must state the value AND, where the page exposes what it saved
 * (`proof`: a popup's backing input, a Workday box's pills), that proof must
 * hold something and — for a pick, measured against its snapshot from before
 * the gesture — have CHANGED, unless the field already held the answer. A
 * display that matches over proof that did not move is `unconfirmed`, never
 * verified. No proof to read: the display decides, as it always did.
 *
 * NO EFFECT is judged here, on the page: an operation after whose every
 * gesture nothing moved — not the committed evidence, the open popups, the
 * element's own value or its aria-expanded / aria-activedescendant, and no
 * node changed in the field's box or was added to <body> — reports reason
 * `no_effect` with the KINDS of gesture it tried (`gestures`: pointer,
 * keyboard, type, select; insertText and its setter fallback are one `type`).
 * The loop calls a field `unsupported` only once two different kinds (typing:
 * two different values) have had no effect. A gesture that changed anything
 * is never no_effect. A press that did NOTHING on a button or combobox whose
 * press never reacted before is followed by a genuinely different gesture:
 * ArrowDown, then — only if that changed nothing anywhere under <body> —
 * Enter (never on a plain text box, a submit button or a link, never after any
 * effect). A value the keys committed is taken back, or reported
 * (`committed_while_opening`).
 *
 * EXPLORING CAN COMMIT (notes §2 rule 5: a search that finds one hit picks
 * it). fill-ops snapshots the committed value before an explore and, with an
 * allowance of its own, takes back whatever the explore committed (`moved`,
 * `takeBack`: a pill by its remove control, a popup's pick by the engine's
 * own undo); what could not be taken back is reported
 * (`committed_while_exploring`) with the value it left.
 *
 * A PLACEHOLDER ROW ("Select One", which live Workday lists as an option, or
 * an empty or dash-only row) is never offered as an answer: explore, a
 * choose's surprise options and the adaptive step drop it. Choosing it stays
 * the engine's own undo alone (explore remembers the row for takeBack).
 *
 * Every popup the engine opens or reads is MARKED (fillBase.markEnginePopup) —
 * including the menu a widget re-renders on every keystroke — because
 * closePopups only ever closes marked popups. Every option text is run through
 * the never-fill policy: a blocked option is never clicked or ticked.
 *
 * THE ADAPTIVE STEP (stepState/move) is for a popup widget the generic path
 * could not finish. stepState reports the field's state now and the moves code
 * allows — click:<oid> (never a placeholder row, never a blocked option, never
 * an item a multi widget already holds; an option that opens a group is
 * described as one), search:value, search:word:<n>, open, scroll, give_up —
 * under a fresh VERSION. A long list is
 * offered 50 options at a time, starting at the first one in view. The model chooses one of those ids; move() acts only
 * on the state it was chosen from, consumes that state (one move per state),
 * refuses an id the state did not offer, and treats a click on a list that
 * changed since as stale. A filtered search view is never complete.
 *
 * A RECIPE'S ORDER (`variant`, shared/recipe-book.js) may reach explore,
 * choose and set: which of a known pair of moves to try FIRST — `open: keys`
 * (the keyboard before the press) or `search: debounce` (a longer wait for the
 * widget's own filter before the Enter). Only the order moves: the other move
 * stays the fallback, the `reacted` lockout and the Enter gate still decide,
 * and verification is unchanged. Each operation reports the move each axis
 * took (`variant`) and an axis whose learned move the control cannot take
 * (`mismatch`), which is all the book learns from.
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
  const KEY_OPEN_MS = 500; // a popup opened from the keyboard, once a press opened nothing
  const PILL_GONE_MS = 1000; // a pill's remove control that takes a moment to take effect
  const SEARCH_OPEN_MS = 1000; // a search box pressed with no term may show nothing at all
  const EMPTY_MS = 600; // a popup that lists nothing and is not loading this long is empty
  // Search results are SETTLED once their option texts have not changed this
  // long. Longer than the gap between two stages of one answer (notes §2 rule
  // 4: School showed 1 row, then 8), so the first stage is never the answer.
  const QUIET_MS = 500;
  const ANSWER_MS = 300; // typing that shows nothing new this long did not search: a combobox gets the Enter
  const FRAME_MS = 100; // a frame, or this long where none runs (a hidden tab starves requestAnimationFrame)
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
  // Elements whose PRESS has visibly done something before: a pointer
  // widget. When its press later does nothing, something it opened is still
  // up (a role-less list), and a key would act on that — so no key is sent.
  const reacted = new WeakSet();
  // el -> the placeholder row ("Select One") its popup listed when explored:
  // never among the options a model sees, and still what the engine's own
  // undo chooses to empty the popup again (takeBack).
  const blankRow = new WeakMap();

  const blockedText = (text, consentForms) => Boolean(ns.isPolicyBlocked?.(text ?? "", { consentForms }));
  // A popup's "choose something" row — live Workday lists "Select One" as an
  // option (notes §3a, §8b) — or an empty or dash-only row is never an answer:
  // every list a model sees (explore's, a choose's surprise, the adaptive
  // step's options and click moves) drops it. Only that row goes: oids keep
  // numbering the list as the page shows it, and nothing else is hidden.
  const isAnswerRow = (o) => !ns.isPlaceholderText(o.text);
  const flag = (options, consentForms) => options.filter(isAnswerRow).map(({ oid, text, selected }) => ({
    oid, text, selected: Boolean(selected), policyBlocked: blockedText(text, consentForms),
  }));
  const same = (x, y) => JSON.stringify(x) === JSON.stringify(y);
  // The options a decision named: its exact text, else the equivalent
  // (case/space/accent-folded) ones.
  const match = (options, text) => {
    const exact = options.filter((o) => o.text === text);
    return exact.length ? exact : options.filter((o) => b().equivalent(o.text, text));
  };
  // Where an option sits in its list, as a person sees it: the labels of the
  // groups around it, its aria-level, and the nearest header before it (a
  // non-option row with text).
  const groupName = (g) => {
    const by = (g.getAttribute("aria-labelledby") ?? "").split(/\s+/).filter(Boolean)
      .map((id) => g.getRootNode().getElementById?.(id)?.textContent ?? "").join(" ");
    return b().clean(g.getAttribute("aria-label") || by);
  };
  const headerBefore = (o) => {
    for (let s = o.previousElementSibling; s; s = s.previousElementSibling) {
      if (s.matches(OPTIONISH) || s.querySelector(OPTIONISH)) continue;
      const text = b().clean(s.textContent);
      if (text) return text;
    }
    return "";
  };
  const pathOf = (o, pop) => {
    const parts = [];
    for (let n = o.parentElement; n && n !== pop.parentElement; n = n.parentElement) {
      if (n.matches('[role="group"], [role="treeitem"]')) parts.push(groupName(n));
    }
    return [...parts, o.getAttribute("aria-level") ?? "", headerBefore(o)].join("\u203a");
  };
  // The same, in words a model reads: the groups and the header, outermost first.
  const placeOf = (o, pop) => {
    const parts = [];
    for (let n = o.parentElement; n && n !== pop.parentElement; n = n.parentElement) {
      if (n.matches('[role="group"], [role="treeitem"]')) parts.unshift(groupName(n));
    }
    parts.push(headerBefore(o));
    return parts.filter((x, i) => x && x !== parts[i - 1]).join(" \u203a ");
  };
  // Which of `hits` (options with nodes, from one popup) is THE option: the
  // only one; or, of several with the same text, the first — they are one
  // option when nothing a person sees tells them apart (notes §2: Workday
  // lists "LinkedIn" twice) — but only when every one sits under the same
  // visible category path. The same text under different categories is a
  // choice nobody made: `ambiguous`.
  const one = (hits, pop) => {
    if (!hits.length) return {};
    if (hits.length === 1) return { hit: hits[0] };
    const where = pathOf(hits[0].el, pop);
    return hits.every((h) => h.text === hits[0].text && pathOf(h.el, pop) === where) ? { hit: hits[0] } : { ambiguous: true };
  };
  // One animation frame (a virtualized list draws the rows for its new
  // scroll position on the next one), bounded: a hidden tab runs none, so a
  // timer stands in after FRAME_MS.
  const frame = () => new Promise((resolve) => {
    const timer = setTimeout(resolve, FRAME_MS);
    requestAnimationFrame(() => {
      clearTimeout(timer);
      resolve();
    });
  });
  const redrawn = async (t) => {
    await frame();
    await b().settle(t, 40);
  };

  const parseDate = (v) => {
    const m = /^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$/.exec(String(v ?? "").trim());
    return m ? { year: m[1], month: m[2] ?? "", day: m[3] ?? "" } : null;
  };
  const formatPattern = (pattern, d) => pattern.replace(/yyyy/i, d.year).replace(/mm/i, d.month).replace(/dd/i, d.day);

  const nonEmpty = (proof) => [proof].flat().some((p) => p != null && p !== "");
  // `before` (a pick's snapshot of shape.evidence) makes an unmoved proof
  // "unconfirmed" unless the display already stated the answer before.
  // `undo` (the engine's OWN undo callers only, never a page action): choosing
  // a popup's placeholder ("Select One") is verified when the popup shows
  // nothing and its proof is empty — an error the page shows for an emptied
  // required field is expected, not a failure. Without it a placeholder is
  // never a verified value (the display reads "" for it, which matches nothing).
  const verify = (el, shape, expected, { format, before, undo = false } = {}) => {
    if (!el.isConnected) return "stale";
    const { proof } = shape.evidence(el);
    if (undo && shape.name === "popup" && typeof expected === "string" && ns.isPlaceholderText(expected)) {
      if (shape.read(el) !== "") return "reverted";
      return proof === null || !nonEmpty(proof) ? "verified" : "unconfirmed";
    }
    if (b().invalid(el)) return "reverted";
    const onScreen = displayed(el, shape, expected, { format });
    if (onScreen !== "verified" || proof === null) return onScreen;
    if (!nonEmpty(proof)) return "unconfirmed";
    if (!before || !same(proof, before.proof)) return "verified";
    return displayed(el, shape, expected, { format, have: before.display }) === "verified" ? "verified" : "unconfirmed";
  };
  // What a gesture can change, and a watch over one operation's gestures:
  // `saw(...kinds)` after each gesture of those kinds (never after the
  // engine's own tidy-up); `ignored` while none of them changed anything;
  // `gestures` the kinds tried. Besides what the engine reads (evidence,
  // value, role-bearing popups, the element's expanded / active-descendant
  // state), ANY structural change in the field's box or a node added to
  // <body> (a role-less list, a portal) counts: a widget that reacted at all
  // is never reported as ignoring the engine. Always `stop()`ped.
  const look = (el, shape) => ({
    ev: JSON.stringify(shape.evidence(el)), value: el.value, pops: b().popups(),
    aria: `${el.getAttribute("aria-expanded")}|${el.getAttribute("aria-activedescendant")}`,
  });
  const differs = (a, z) => a.ev !== z.ev || a.value !== z.value || a.aria !== z.aria
    || a.pops.length !== z.pops.length || a.pops.some((p, i) => p !== z.pops[i]);
  const watch = (el, shape) => {
    // Records reach the callback once the gesture's task ends, or the next
    // saw() takes them: either way they are counted.
    let mutated = false;
    const nodes = new MutationObserver(() => {
      mutated = true;
    });
    nodes.observe(ns.shapes.box(el) ?? el, { subtree: true, childList: true, attributes: true, characterData: true });
    if (document.body) nodes.observe(document.body, { childList: true });
    let last = el.isConnected ? look(el, shape) : null;
    let ignored = true;
    const tried = new Set();
    return {
      saw(...kinds) {
        for (const k of kinds) tried.add(k);
        const now = el.isConnected ? look(el, shape) : null;
        if (nodes.takeRecords().length || mutated || !last || !now || differs(last, now)) ignored = false;
        mutated = false;
        last = now;
      },
      get ignored() {
        return ignored;
      },
      // Something the watch cannot see reacted (a change deeper under <body>).
      felt() {
        ignored = false;
      },
      // What to report: no_effect with the kinds tried, or the other reason.
      reason(otherwise) {
        return ignored ? { reason: "no_effect", gestures: [...tried] } : { reason: otherwise };
      },
      stop() {
        nodes.disconnect();
      },
    };
  };

  // Whether the display states the value: the one on screen now, or `have`
  // (a display read earlier).
  const displayed = (el, shape, expected, { format, have: earlier } = {}) => {
    const have = [earlier === undefined ? shape.read(el) : earlier].flat();
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

  // The widget a field's focus may wander inside: a split date's own sections
  // (Workday moves focus between them by itself), a search widget's box (the
  // one boundary shapes.box draws: a Workday box's multiselect container);
  // else the element alone.
  const widgetOf = (el) => {
    const shape = ns.shapes.of(el);
    if (shape?.name === "date" && shape.dateKind(el) === "sections") {
      const run = shape.dateSections(el);
      let n = el.closest('[data-automation-id="dateInputWrapper"]') ?? el.parentElement;
      while (n && !run.every((s) => n.contains(s))) n = n.parentElement;
      return n ?? el;
    }
    if (shape?.open === "search") return ns.shapes.box(el) ?? el;
    return el;
  };
  // Leave the field the way Workday commits it (fillBase.leave), then let the
  // page validate.
  const blurOut = async (el, t) => {
    b().check(t);
    b().leave(el, widgetOf(el));
    await b().settle(t, 150);
  };

  // ---- text-like
  async function write(el, shape, value, t, { format } = {}) {
    if (shape.kind !== "text") return { outcome: "unexpected", reason: "not_text" };
    let parts = null;
    let text = String(value ?? "");
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
      if (kind === "sections") parts = shape.dateSections(el).map((sec) => [sec, d[shape.partOf(sec)]]);
      else {
        text = kind === "month" ? `${d.year}-${d.month}` : kind === "date" ? `${d.year}-${d.month}-${d.day}`
          : formatPattern(placeholder, d);
      }
    }
    // A box already showing the value cannot show an effect: never no_effect.
    const shown = displayed(el, shape, value, { format }) === "verified";
    const w = watch(el, shape);
    try {
      if (parts) {
        for (const [sec, part] of parts) {
          b().typeText(sec, part, t);
          w.saw("type");
        }
        await blurOut(parts.at(-1)[0], t);
      } else {
        // insertText and its setter fallback are ONE gesture: a box that takes
        // neither may be refusing this VALUE (type=number, a mask), not the engine.
        b().typeText(el, text, t);
        w.saw("type");
        await blurOut(el, t);
      }
      w.saw();
      const outcome = verify(el, shape, value, { format });
      return outcome !== "verified" && outcome !== "stale" && w.ignored && !shown
        ? { outcome, ...w.reason() } : { outcome };
    } finally {
      w.stop();
    }
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
  // Its rows say whether the widget takes one answer or several (radio or
  // checkbox rows): shapes remembers that for the element.
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
    const got = pop ?? own(el, before);
    ns.shapes.learnRows(el, got);
    return got;
  };
  // The row texts of a list (or "-": no list), the signal a search's results
  // are judged by — texts, not nodes: Workday reuses its rows and swaps their
  // text (notes §2 rule 3). Every visible row counts, a "No Items." row too:
  // an honest empty answer is a change.
  const rowsOf = (p) => [...p.querySelectorAll(OPTIONISH)].filter((o) => b().visible(o));
  const textsOf = (p) => (p ? rowsOf(p).map((o) => b().clean(o.innerText || o.textContent)).join("\n") : "-");
  // How many rows the list SAYS it holds, where it says so: the one
  // aria-setsize every visible row carries, or the list's aria-rowcount.
  const declared = (p) => {
    const rows = rowsOf(p);
    const sizes = new Set(rows.map((r) => r.getAttribute("aria-setsize")));
    const size = rows.length && sizes.size === 1 && !sizes.has(null) ? Number([...sizes][0]) : NaN;
    if (Number.isInteger(size) && size >= 0) return size;
    const count = p.hasAttribute("aria-rowcount") ? Number(p.getAttribute("aria-rowcount")) : NaN;
    return Number.isInteger(count) && count >= 0 ? count : null;
  };
  // Search results once they SETTLE. `was`: the texts the list showed just
  // before the search (before the Enter; before the typing where no Enter
  // follows). Settled is: nothing busy, the texts CHANGED from `was`, then
  // stayed unchanged QUIET_MS (results arrive in stages — School showed 1
  // row, then 8). An unchanged list (Workday's School opens EMPTY; How Did
  // You Hear shows its default categories) is the answer only once OPEN_MS
  // has passed with nothing new: a search may rightly answer with the list it
  // showed, but a slow one must not be read as empty. A declared size
  // (aria-setsize / aria-rowcount, where every row is in the DOM) only ever
  // holds the wait longer: fewer rows than it says are not settled — it is a
  // veto, never a shortcut (a page may declare the rows of one stage). A
  // list still changing — or still short of its declared size — when time
  // runs out is not taken: `unsettled`, no popup. A list that closed while
  // the committed value moved is an Enter that committed its one hit (notes
  // §2 rule 5): no popup at once, the caller reads the evidence. The rows say
  // whether the widget takes one answer or several: shapes remembers that.
  // Returns { pop, unsettled }.
  const waitSettled = async (el, shape, before, snap, was, t) => {
    const start = Date.now();
    let last = null;
    let since = start;
    let seen = false; // a list was up when time ran out
    const got = await b().waitFor(() => {
      const now = Date.now();
      const p = own(el, before);
      if (!p && moved(el, shape, snap)) return { pop: null };
      seen = Boolean(p);
      if (!p || busy(p)) {
        last = null;
        since = now;
        return null;
      }
      const sig = textsOf(p);
      if (sig !== last) {
        last = sig;
        since = now;
        return null;
      }
      const size = scrollerOf(p) ? null : declared(p);
      if (size !== null && rowsOf(p).length < size) return null; // the list says more are coming
      if (now - since < QUIET_MS) return null;
      return sig !== was || now - start >= OPEN_MS ? { pop: p } : null;
    }, OPEN_MS + QUIET_MS, t);
    const pop = got?.pop ?? null;
    ns.shapes.learnRows(el, pop);
    return { pop, unsettled: !got && seen };
  };
  // What the engine last settled for a search box: the list, its texts and
  // the query they answer. Typing that same query again into that same,
  // unchanged list would only wait for a list that cannot change.
  const settledFor = new WeakMap();
  // A query typed into the field's OWN box is remembered so tidy can take it
  // back; one typed into a search box inside the popup leaves with the popup.
  const typeQuery = async (box, term, t, { own: remember = false } = {}) => {
    if (remember && !typed.has(box)) typed.set(box, { prior: box.value ?? "", query: null });
    b().typeText(box, term, t);
    if (remember) typed.get(box).query = box.value;
    await b().settle(t, 100); // let a debounced search replace the old list first
  };
  // A box whose own ARIA says it searches: a combobox or an autocomplete.
  const comboBox = (box) => box instanceof HTMLInputElement && !box.closest("a[href]")
    && (box.getAttribute("role") === "combobox"
      || (box.hasAttribute("aria-autocomplete") && box.getAttribute("aria-autocomplete") !== "none"));
  // What typing a query can visibly change: what the app saved (never the
  // display — a free-text box shows the query itself), whether the box says
  // its list is expanded, and the owned list.
  const searchView = (el, shape, before) => {
    const p = own(el, before);
    return `${JSON.stringify(shape.evidence(el).proof)}|${el.getAttribute("aria-expanded")}|${
      p ? `${busy(p)}:${b().optionsOf(p).map((o) => o.text).join("\n")}` : "-"}`;
  };
  // THE SEARCH SEQUENCE (notes §2). PRESS the field's box (entered first) and
  // wait for its list — on Workday, typing into a box whose list is not open
  // opens nothing and an Enter sent before the list exists is lost; any other
  // widget gets a moment. `press: false` for a box inside an open popup and
  // for a list the engine already holds open (a press may toggle it shut).
  // TYPE the term over whatever query is there (no ×). ENTER (keydown and
  // keyup: Workday searches on the key-up) — the search's own step, not the
  // keyboard fallback, so no earlier effect (`reacted`) holds it back: sent
  // to a Workday box always, to a combobox / autocomplete box only when its
  // typing showed nothing new within ANSWER_MS (a widget that filters as you
  // type would take the Enter as a pick), never to anything else — a plain
  // text box, a button, anything inside a link. Then wait for the results to
  // SETTLE. Returns the popup, or null (none; or the Enter committed its one
  // hit and closed the list — the caller reads the evidence).
  // A learned `search: debounce` first (`variant`, a recipe) only waits
  // longer — OPEN_MS — for the widget's own filter before that Enter: it never
  // sends one the gate refuses. `used.search` says which it took, where an
  // Enter could go at all.
  const search = async (el, shape, box, term, before, t, w, { press = true, variant, used } = {}) => {
    const snap = snapshot(el, shape);
    const workday = box === el && ns.shapes.workday(el);
    // The same query, still answered by the list the engine settled for it
    // (a choose's second gesture): nothing to type, nothing to wait for.
    const prior = settledFor.get(box);
    if (!press && prior && box.value === prior.query && box.value === term && own(el, before) === prior.pop
      && textsOf(prior.pop) === prior.texts) return { pop: prior.pop, unsettled: false };
    let pressing = press;
    if (pressing) {
      b().enter(el, t);
      // A widget that opens its list on focus (MUI-style) is not pressed as
      // well: its press toggles that list shut.
      if (!workday && (own(el, before) || el.getAttribute("aria-expanded") === "true")) pressing = false;
    }
    if (pressing) {
      const quiet = watch(el, shape);
      try {
        await pressWatched(el, quiet, t, w, () => (workday ? b().waitFor(() => own(el, before), OPEN_MS, t) : b().settle(t, 100)));
      } finally {
        quiet.stop();
      }
    }
    const was = searchView(el, shape, before);
    let shown = textsOf(own(el, before)); // what the list showed before the search
    await typeQuery(box, term, t, { own: box === el });
    w?.saw("type");
    // A generic combobox naming a highlighted option (aria-activedescendant)
    // never gets it: its Enter would pick that option. Workday's Enter
    // searches, highlight or not.
    const gated = !workday && !box.getAttribute("aria-activedescendant") && comboBox(box);
    const patient = variant?.search?.[0] === "debounce";
    const silent = async (ms) => !(await b().waitFor(() => searchView(el, shape, before) !== was, ms, t));
    const enter = workday ? !patient || (await silent(OPEN_MS)) : gated && (await silent(patient ? OPEN_MS : ANSWER_MS));
    if (enter) {
      shown = textsOf(own(el, before));
      b().keyPress(box, "Enter", t);
      w?.saw("keyboard");
    }
    if (used && (workday || gated)) used.search = enter ? "enter" : "debounce";
    const got = await waitSettled(el, shape, before, snap, shown, t);
    if (got.pop) settledFor.set(box, { pop: got.pop, texts: textsOf(got.pop), query: box.value });
    return got;
  };
  // The list the engine opened for this search box, while it is still up.
  const heldList = (el) => {
    const before = opened.get(el);
    return before && own(el, before) ? before : null;
  };
  // A press of the field's control under `quiet` (a watch), then `until`.
  // The ONE place the `reacted` rule is kept: a press that visibly did
  // anything marks the element, and no key is ever sent to it after that.
  const pressWatched = async (el, quiet, t, w, until) => {
    b().press(el, t);
    const got = await until();
    quiet.saw();
    w?.saw("pointer");
    if (!quiet.ignored) reacted.add(el);
    return got;
  };
  // A control the keyboard may open: a button or a combobox — never a plain
  // text box, a submit button or anything inside a link (a key there can
  // submit a form or navigate).
  const keyable = (el) => {
    if (el.closest("a[href]") || el.getAttribute("type") === "submit" || (el.form && el.type === "submit")) return false;
    return !(el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) || el.readOnly
      || el.getAttribute("role") === "combobox";
  };
  // Whether anything under <body> changed while `fn` ran: the ArrowDown step
  // is watched this widely (a role-less list rendered into a portal that was
  // already there), and any change keeps the Enter from following it.
  const bodyChanged = async (fn) => {
    let changed = false;
    const all = new MutationObserver(() => {
      changed = true;
    });
    // Attributes too (a highlight moving): this only gates the Enter.
    all.observe(document.body, {
      childList: true, subtree: true, attributes: true,
      attributeFilter: ["class", "style", "hidden", "aria-hidden", "aria-selected"],
    });
    try {
      await fn();
      return changed || all.takeRecords().length > 0;
    } finally {
      all.disconnect();
    }
  };
  // `w` (a watch) hears each gesture's kind. A key is sent only while every
  // gesture before it had NO effect at all (a fresh watch, not "no readable
  // popup"), and never to an element whose press has reacted before
  // (`reacted`): after a press that visibly did something — a role-less
  // list — an Enter would accept its highlighted row. The Enter also waits
  // on the ArrowDown having changed nothing anywhere under <body>. What the
  // keys themselves committed is taken back (`reclaim`); what could not be
  // is `committed`. `reclaim: false` for explore (fill-ops owns its undo) and
  // for the engine's own undo, which must not undo itself.
  // `variant` (a recipe's order) may put the keys FIRST (`open: keys`): the
  // same keys under the same gates — keyable, nothing reacted, the Enter only
  // after an ArrowDown that changed nothing — then the press if they opened
  // nothing. A control the keys may never go to cannot take that order
  // (`used.mismatch`). `used.open` says which move opened the list.
  const open = async (el, shape, term, t, w, { reclaim = true, variant, used } = {}) => {
    let searchable = shape.open === "search";
    // A search widget with a term runs the search sequence — without the
    // press when the list it opened for an earlier item is still up.
    if (searchable && term) {
      const held = heldList(el);
      const before = held ?? b().popups();
      opened.set(el, before);
      return { ...(await search(el, shape, el, term, before, t, w, { press: !held, variant, used })), before, searchable };
    }
    const before = b().popups();
    opened.set(el, before);
    el.focus?.({ preventScroll: true });
    const snap = snapshot(el, shape);
    const quiet = watch(el, shape);
    let pop = null;
    let keyed = false;
    let how = null;
    const pressIt = async () => {
      pop = await pressWatched(el, quiet, t, w, () => b().waitFor(() => own(el, before), searchable ? SEARCH_OPEN_MS : OPEN_MS, t));
      if (pop) how = "press";
    };
    // The keyboard, a genuinely different gesture: after a press that did
    // nothing at all, or first under a recipe's order — the same gates either way.
    const keys = async () => {
      let quietBody = true;
      for (const key of ["ArrowDown", "Enter"]) {
        if (pop || !keyable(el) || !quiet.ignored || reacted.has(el) || !quietBody) break;
        try {
          b().enter(el, t);
        } catch (err) {
          if (err?.name === "Unfocusable") break; // nothing takes keys it cannot focus
          throw err;
        }
        keyed = true;
        quietBody = !(await bodyChanged(async () => {
          b().keyPress(el, key, t);
          pop = await b().waitFor(() => own(el, before), KEY_OPEN_MS, t);
        }));
        quiet.saw();
        w?.saw("keyboard");
        if (!quietBody) w?.felt(); // it reacted: a list somewhere the watch does not look
        // …and that list may still be up next time, where an ArrowDown would
        // only move its highlight: no key goes to this control again.
        if (!quietBody && !pop) reacted.add(el);
      }
      if (pop) how = "keys";
    };
    const keysFirst = variant?.open?.[0] === "keys";
    if (keysFirst && used && !keyable(el)) used.mismatch = "open";
    try {
      for (const step of keysFirst ? [keys, pressIt] : [pressIt, keys]) {
        if (pop) break;
        await step();
      }
    } finally {
      quiet.stop();
    }
    if (how && used) used.open = how;
    if (keyed && reclaim && moved(el, shape, snap)) {
      await takeBack(el, shape, snap, pop ? b().optionsOf(pop) : [], t);
      if (moved(el, shape, snap)) {
        if (pop) await tidy(el, t);
        return { pop: null, before, searchable, committed: true };
      }
      pop = own(el, before);
    }
    if (!pop) return { pop: null, before, searchable };
    const box = pop.querySelector(INNER_SEARCH);
    if (box) searchable = true;
    if (term && box) return { ...(await search(el, shape, box, term, before, t, w, { press: false, variant, used })), before, searchable };
    return { pop: await waitOptions(el, before, t), before, searchable };
  };
  const scrollerOf = (pop) => [pop, ...pop.querySelectorAll("*")]
    .find((n) => n.scrollHeight > n.clientHeight + 4 && /(auto|scroll)/.test(getComputedStyle(n).overflowY)) ?? null;
  // Every option, a page and a frame at a time down a long list (a
  // virtualized one holds only the rows in view), until the scroll position
  // stops changing. Identical options — the same text under the same
  // category path (`one`) — are read once; the same text under different
  // categories is two options, both listed.
  const readAll = async (pop, t) => {
    const seen = new Map();
    const box = scrollerOf(pop);
    let complete = !box;
    for (let i = 0; i < 30; i += 1) {
      for (const o of b().optionsOf(pop)) {
        const key = `${o.text}\n${pathOf(o.el, pop)}`;
        if (!seen.has(key)) seen.set(key, o);
      }
      if (complete) break;
      const top = box.scrollTop;
      box.scrollTop = top + box.clientHeight;
      await redrawn(t);
      if (box.scrollTop === top) complete = true; // the next pass reads the last page, then stops
    }
    return { options: [...seen.values()].map((o, i) => ({ oid: `o${i + 1}`, text: o.text, selected: isHeld(o) })), complete };
  };
  // The one option to click (`one`: { hit } | { ambiguous } | {}): in view,
  // else from the top of a long list down, a page and a frame at a time.
  const findOption = async (pop, text, t) => {
    const look = () => one(match(b().optionsOf(pop), text), pop);
    let found = look();
    const box = found.hit || found.ambiguous ? null : scrollerOf(pop);
    if (box && box.scrollTop > 0) {
      box.scrollTop = 0;
      await redrawn(t);
      found = look();
    }
    for (let i = 0; box && !found.hit && !found.ambiguous && i < 30; i += 1) {
      const top = box.scrollTop;
      box.scrollTop = top + box.clientHeight;
      await redrawn(t);
      found = look();
      if (box.scrollTop === top) break;
    }
    return found;
  };
  // The option found AGAIN by its text right before the click: bringing it
  // into view makes a virtualized list redraw, and a reused row may show
  // another option by then (notes §2 rules 3, 4).
  const refind = async (pop, hit, text, t) => {
    hit.el.scrollIntoView?.({ block: "nearest" });
    await redrawn(t);
    return (await findOption(pop, text, t)).hit ?? null;
  };
  // The real control inside an option: a Workday result row holds a radio
  // (one answer) or a checkbox (several), and a click on the ROW only
  // highlights it (notes §2 "row vs radio").
  const checkableIn = (o) => o.querySelector('input[type="radio"], input[type="checkbox"]');
  // Whether an option (from optionsOf) is already chosen: its own radio or
  // checkbox where it holds one — Workday's aria-selected is only its
  // keyboard highlight (notes §2) — else its aria-selected / aria-checked.
  const isHeld = (o) => checkableIn(o.el)?.checked ?? o.selected;

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
    else if (restore) b().leave(el, widgetOf(el)); // the undo focused the box: focus is not left in it
  };

  // What an explore must leave as it found it (fill-ops takes it before the
  // explore): the committed evidence, and a search box's pill texts.
  const snapshot = (el, shape) => ({
    evidence: shape.evidence(el), held: shape.open === "search" ? ns.shapes.pills(el).map((p) => p.text) : [],
  });
  // Whether the field's committed value moved since `snap`: its proof where
  // the page exposes one; else what it shows — unless that is the box's own
  // text (a free-text box's display IS the query tidy takes back, not a
  // commit; so a search box whose only display is its own input cannot have
  // an explore commit noticed — INTERNALS.md says so).
  const moved = (el, shape, snap) => {
    if (!el.isConnected) return false;
    const was = snap.evidence;
    const now = shape.evidence(el);
    if (was.proof !== null || now.proof !== null) return !same(was.proof, now.proof);
    if (same(was.display, now.display)) return false;
    return !(el instanceof HTMLInputElement && [now.display].flat().join(", ") === el.value);
  };
  // A pill's own node: the chip, widened while its parent holds no other chip
  // and not the field (react-select's remove button sits BESIDE its label).
  const pillUnit = (el, chip) => {
    const all = ns.shapes.pills(el).map((p) => p.node);
    let n = chip;
    while (n.parentElement && !n.parentElement.contains(el)
      && all.filter((c) => n.parentElement.contains(c)).length === 1) n = n.parentElement;
    return n;
  };
  // What the field holds now that it did not at `snap`: a search box's new
  // pills, else the new display values (a multiset difference).
  const added = (el, shape, snap) => {
    const search = shape.open === "search";
    const left = search ? [...snap.held] : [snap.evidence.display].flat();
    const now = search ? ns.shapes.pills(el).map((p) => p.text) : [shape.evidence(el).display].flat();
    return now.filter((x) => {
      const at = left.indexOf(x);
      if (at < 0) return x != null && x !== "";
      left.splice(at, 1);
      return false;
    });
  };
  const REMOVE = /delete|remove|clear/i;
  // Take back what exploring committed. A pill it added: Workday's
  // DELETE_charm, else a control inside the pill named delete/remove/clear,
  // else the pill itself (pills that un-pick on a click). A popup's pick: the
  // engine's own undo — choose what it showed before, or its placeholder
  // (from `options`, else the row the explore saw: explore never returns it).
  const takeBack = async (el, shape, snap, options, t) => {
    if (shape.open === "search") {
      const left = [...snap.held];
      for (const p of ns.shapes.pills(el)) {
        const at = left.indexOf(p.text);
        if (at >= 0) {
          left.splice(at, 1);
          continue;
        }
        const unit = pillUnit(el, p.node);
        const named = (n) => REMOVE.test(`${n.getAttribute("aria-label") ?? ""} ${n.getAttribute("data-automation-id") ?? ""}`);
        const control = unit.querySelector('[data-automation-id="DELETE_charm"]')
          ?? [...unit.querySelectorAll("*")].find((n) => n !== p.node && named(n)) ?? p.node;
        control.scrollIntoView?.({ block: "nearest" });
        b().press(control, t);
        // The pill goes when the page takes the removal — maybe a moment later.
        await b().waitFor(() => !p.node.isConnected, PILL_GONE_MS, t);
        await b().settle(t, 60);
      }
      return;
    }
    const text = snap.evidence.display || (options ?? []).find((o) => ns.isPlaceholderText(o.text))?.text
      || blankRow.get(el);
    if (text) await choose(el, shape, { text, undo: true }, t);
  };

  // What an operation's opens and searches did, for the loop's recipe book:
  // `variant` the move each axis took, and `mismatch` the axis whose learned
  // move the control could not take. Nothing when no list was opened.
  const withMoves = (result, used) => {
    const { mismatch, ...moves } = used;
    return { ...result, ...(Object.keys(moves).length ? { variant: moves } : {}), ...(mismatch ? { mismatch } : {}) };
  };

  // `variant`: a recipe's order for the opens and searches (see `open`).
  async function explore(el, shape, { term, consentForms, variant } = {}, t) {
    if (shape.kind !== "choice") return { options: [], complete: false, searchable: false, error: "not_a_choice" };
    if (shape.passive) {
      const p = shape.passive(el);
      return { options: flag(p.options, consentForms), complete: p.complete, searchable: false };
    }
    b().check(t);
    const snap = snapshot(el, shape);
    const w = watch(el, shape);
    const used = {};
    try {
      // fill-ops owns explore's undo (whatever moved, keys included).
      let { pop, searchable, unsettled } = await open(el, shape, term, t, w, { reclaim: false, variant, used });
      let options = pop ? b().optionsOf(pop) : [];
      if (!options.length && term) {
        const word = term.split(/\s+/).find((x) => x.length > 2 && x !== term);
        // A term that already committed something is not searched again by a
        // word (fill-ops takes the commit back).
        if (word && !moved(el, shape, snap)) {
          await tidy(el, t);
          ({ pop, searchable, unsettled } = await open(el, shape, word, t, w, { reclaim: false, variant, used }));
          options = pop ? b().optionsOf(pop) : [];
        }
      }
      let got = pop && options.length ? await readAll(pop, t) : { options: [], complete: false };
      const rows = pop && options.length ? ns.shapes.learnRows(el, pop) : null;
      const blank = got.options.find((o) => ns.isPlaceholderText(o.text));
      if (blank) blankRow.set(el, blank.text);
      // The search's Enter committed its one hit and closed the list (notes §2
      // rule 5): that hit is what the search found (fill-ops takes it back).
      if (!got.options.length && !pop && term && moved(el, shape, snap)) {
        got = { options: added(el, shape, snap).map((text, i) => ({ oid: `o${i + 1}`, text, selected: false })), complete: false };
      }
      await tidy(el, t);
      // A filtered search view is never the complete list. `multi` only when the
      // rows said so: checkboxes (several answers) or radios (one).
      const out = { options: flag(got.options, consentForms), complete: got.complete && !term, searchable };
      if (rows) out.multi = rows === "multi";
      if (!out.options.length) {
        if (pop) out.error = "empty_popup";
        else {
          // A list that never settled is not "no popup": it is unsettled.
          const why = unsettled ? { reason: "unsettled" } : w.reason("no_popup");
          out.error = why.reason;
          if (why.gestures) out.gestures = why.gestures;
        }
      }
      return withMoves(out, used);
    } finally {
      w.stop();
    }
  }

  // A hidden custom radio/checkbox is operated through its label.
  const clickTarget = (input) => (b().visible(input) ? input
    : (input.id && input.getRootNode().querySelector?.(`label[for="${CSS.escape(input.id)}"]`)) || input.closest("label") || input);
  const tick = (input, t) => {
    b().check(t);
    clickTarget(input).click();
  };
  const selectIndex = (el, index, t) => {
    b().enter(el, t);
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "selectedIndex").set.call(el, index);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  };

  const addSelected = (el, opts, t) => {
    b().enter(el, t);
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
    // since it was read is missing, not an error. `gesture` is null when the
    // control already holds the answer (no gesture, so no effect to judge).
    let gesture = null;
    let kind = "pointer";
    if (shape.name === "select") {
      const opt = shape.realOptions(el).find((o) => b().clean(o.text) === want);
      if (!opt) return { outcome: "unexpected", reason: "option_missing", options };
      kind = "select";
      if (!opt.selected && el.multiple) gesture = () => addSelected(el, [opt], t); // the other selections stay
      else if (!opt.selected) gesture = () => selectIndex(el, opt.index, t);
    } else if (shape.lone(el)) {
      if (want !== "Yes" && want !== "No") return { outcome: "unexpected", reason: "option_missing", options };
      if (el.checked !== (want === "Yes")) gesture = () => tick(el, t);
    } else {
      const input = shape.members(el).find((m) => shape.labelOf(m) === want);
      if (!input) return { outcome: "unexpected", reason: "option_missing", options };
      if (!input.checked) gesture = () => tick(input, t);
    }
    const w = watch(el, shape);
    try {
      if (gesture) {
        gesture();
        w.saw(kind);
      }
      await blurOut(el, t);
      w.saw();
      if (verify(el, shape, want) === "verified") return { outcome: "verified", text: want };
      return { outcome: "unexpected", ...(gesture ? w.reason("not_committed") : { reason: "not_committed" }) };
    } finally {
      w.stop();
    }
  }

  const GESTURES = [(o, t) => b().press(o, t), (o, t) => {
    b().check(t);
    o.click();
  }];
  // The gestures that may pick an option: its radio or checkbox ONCE (a tick
  // is a toggle — a second click before the redraw takes the pick back,
  // notes §2 rule 8), else a press and then a click.
  const gesturesFor = (o) => (checkableIn(o) ? [(x, t) => {
    b().check(t);
    checkableIn(x).click();
  }] : GESTURES);
  // After a click: a moment for the page, and for a tick its pill — the next
  // item is typed only once the page shows the one before (≤ OPEN_MS).
  const afterClick = async (el, shape, o, text, t) => {
    await b().settle(t, 200);
    if (checkableIn(o)?.type === "checkbox") await b().waitFor(() => holds(el, shape, text), OPEN_MS, t);
  };
  // Whether the field's committed value already holds this text — presence
  // only, whatever error the field shows.
  const holds = (el, shape, x) => [shape.read(el)].flat().some((h) => b().equivalent(h, x));
  // Whether the query in the box has become the committed value (a free-text
  // box whose pick equals the query): no pills, no backing — the box is it.
  const queryIsValue = (el, shape, x) => holds(el, shape, x) && shape.evidence(el).proof === null
    && [shape.read(el)].flat().includes(el.value);
  // An item a multi widget already holds is never clicked (a click toggles it
  // off); what the page holds is reported as it stands.
  const alreadyThere = (el, shape, text) => ({
    outcome: verify(el, shape, text) === "verified" ? "verified" : "reverted", text,
  });

  // The search's own Enter committed something (notes §2 rule 5: a single
  // hit). The answer itself is verified without a click; anything else is
  // taken back like any value the engine did not choose — and one that will
  // not go back is `committed_while_opening`. Returns { result } to report,
  // or { live }: the list still up to pick from (null when it closed).
  const enterCommitted = async (el, shape, text, snap, popsBefore, { undo, consentForms, done }, t) => {
    if (displayed(el, shape, text) === "verified") {
      const got = verify(el, shape, text, { before: snap.evidence });
      return { result: await done(got === "verified" || got === "unconfirmed" ? { outcome: got, text }
        : { outcome: "unexpected", reason: "not_committed" }) };
    }
    const hits = added(el, shape, snap);
    if (!undo) await takeBack(el, shape, snap, [], t);
    if (moved(el, shape, snap)) {
      await tidy(el, t);
      return { result: { outcome: "unexpected", reason: "committed_while_opening" } };
    }
    const live = own(el, popsBefore);
    if (live) return { live };
    const options = flag(hits.map((h, i) => ({ oid: `o${i + 1}`, text: h })), consentForms);
    return { result: await done({ outcome: "unexpected", reason: "option_missing", options }) };
  };

  // `undo`: the engine's own undo (choosing a popup's placeholder to empty
  // it). Page actions never carry it, so a decision that names a placeholder
  // ("Select One" offered as an option) is refused, never clicked.
  // `keep` (a set's items on a search box): the list stays open and the query
  // typed — the next item is typed over it; set tidies once, at its end.
  // `asSet`: a set's item on a box not known to take several — rows that turn
  // out to be radios end it (`not_a_set`) before anything is clicked.
  // `variant`: a recipe's order for the opens and searches (see `open`); the
  // result says which moves they took (`withMoves`).
  async function choose(el, shape, options = {}, t) {
    const used = {};
    return withMoves(await chooseOne(el, shape, { ...options, used }, t), used);
  }
  // choose's work; `used` hears what its opens and searches did (a set's
  // items share one).
  async function chooseOne(el, shape, {
    text, term, consentForms, undo = false, keep = false, asSet = false, variant, used,
  } = {}, t) {
    if (shape.kind !== "choice") return { outcome: "unexpected", reason: "not_a_choice" };
    if (blockedText(text, consentForms)) return { outcome: "blocked" };
    if (!undo && ns.isPlaceholderText(text)) return { outcome: "unexpected", reason: "placeholder" };
    if (shape.passive) return choosePassive(el, shape, text, t, consentForms);
    const multi = Boolean(shape.multi?.(el));
    if (multi && holds(el, shape, text)) return alreadyThere(el, shape, text);
    // A one-answer widget that already holds this answer — shown AND, where
    // the page exposes it, saved — is never clicked again. One that only
    // shows it (a popup whose backing input is empty) still gets the pick.
    if (!multi && verify(el, shape, text) === "verified") return { outcome: "verified", text };
    // What the field showed and the app held before the pick: its proof must move.
    const snap = snapshot(el, shape);
    const before = snap.evidence;
    const w = watch(el, shape);
    const done = async (result) => {
      if (!keep) await tidy(el, t);
      return result;
    };
    try {
      for (let attempt = 0; ; attempt += 1) {
        const { pop, before: popsBefore, committed, unsettled } = await open(el, shape,
          shape.open === "search" ? (term ?? text) : term, t, w, { reclaim: !undo, variant, used });
        if (committed) return { outcome: "unexpected", reason: "committed_while_opening" };
        // Only a list the search let settle is picked from — or, once an
        // Enter's commit was taken back, the list still up after it.
        let live = pop?.isConnected ? pop : null;
        if (shape.open === "search" && moved(el, shape, snap)) {
          const after = await enterCommitted(el, shape, text, snap, popsBefore, { undo, consentForms, done }, t);
          if (after.result) return after.result;
          live = after.live;
        }
        // The rows said "one answer": a set's item is not one to click.
        if (asSet && shape.multi?.(el) === false) return done({ outcome: "unexpected", reason: "not_a_set" });
        if (!live) {
          await tidy(el, t);
          return { outcome: "unexpected", ...(unsettled ? { reason: "unsettled" } : w.reason("no_popup")) };
        }
        const found = await findOption(live, text, t);
        if (!found.hit) {
          const options = flag(b().optionsOf(live), consentForms);
          if (found.ambiguous) return done({ outcome: "unexpected", reason: "ambiguous", options });
          return done({ outcome: "unexpected", reason: options.length ? "option_missing" : "empty_popup", options });
        }
        let { hit } = found;
        if (blockedText(hit.text, consentForms)) return done({ outcome: "blocked" });
        if (!undo && ns.isPlaceholderText(hit.text)) return done({ outcome: "unexpected", reason: "placeholder" });
        // The rows the list showed may only now have said "several".
        if ((multi || shape.multi?.(el)) && (isHeld(hit) || holds(el, shape, hit.text))) {
          return done(alreadyThere(el, shape, hit.text));
        }
        hit = await refind(live, hit, text, t);
        if (!hit) return done({ outcome: "unexpected", reason: "option_missing", options: flag(b().optionsOf(live), consentForms) });
        if ((multi || shape.multi?.(el)) && isHeld(hit)) return done(alreadyThere(el, shape, hit.text));
        const gestures = gesturesFor(hit.el);
        if (attempt >= gestures.length) break; // a row redrawn with a tick where a plain row was
        const shown = b().optionsOf(live).map((o) => o.text).join("\n");
        gestures[attempt](hit.el, t);
        await afterClick(el, shape, hit.el, hit.text, t);
        w.saw("pointer");
        // The pick is committed: the query typed to find it is no longer the
        // engine's to take back (a free-text box whose pick equals the query).
        // Only when the box's own value IS the committed value: a widget that
        // shows the pick in a pill (proof) and leaves the query in its box
        // still gets the query taken back, even one that reads like the pill.
        if (queryIsValue(el, shape, hit.text)) typed.delete(el);
        const after = own(el, popsBefore);
        const next = after ? b().optionsOf(after) : [];
        if (next.length && next.map((o) => o.text).join("\n") !== shown && same(shape.read(el), before.display)) {
          leftOpen.set(el, { pop: after, before: popsBefore });
          return { outcome: "unexpected", reason: "new_options", options: flag(next, consentForms) };
        }
        if (!keep) await tidy(el, t);
        const got = verify(el, shape, hit.text, { before, undo });
        if (got === "verified") return { outcome: "verified", text: hit.text };
        // It shows the pick, but the app did not take it: never a second click
        // (the loop decides what an unconfirmed value needs).
        if (got === "unconfirmed") return { outcome: "unconfirmed", text: hit.text };
        // Something else got committed: a second click could undo it (a chip
        // that un-picks on click). Only a click that changed nothing is
        // retried, with the next gesture — and a tick has no next one.
        if (!same(shape.read(el), before.display) || attempt + 1 >= gestures.length) break;
      }
      return { outcome: "unexpected", ...w.reason("not_committed") };
    } finally {
      w.stop();
    }
  }

  // Sets add, never remove: an existing choice is kept and never unticked,
  // and a set is verified only when EVERY requested item is committed. Items
  // the never-fill policy refuses are reported as `blocked`, apart from the
  // `missing` ones the page did not offer or did not take. A Workday search
  // box not yet known to take one answer or several is tried as a set: its
  // first item's rows decide (radios: `not_a_set`, nothing clicked).
  // `variant`: a recipe's order for its items' opens and searches.
  async function set(el, shape, options = {}, t) {
    const used = {};
    return withMoves(await setAll(el, shape, { ...options, used }, t), used);
  }
  async function setAll(el, shape, { texts = [], terms = [], consentForms, variant, used } = {}, t) {
    const several = shape.multi?.(el);
    const unknown = several == null && shape.open === "search" && ns.shapes.workday(el);
    if (shape.kind !== "choice" || !(several || unknown)) return { outcome: "unexpected", reason: "not_a_set" };
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
      // A search box's items share ONE open list (notes §2 rule 7): each is
      // typed over the last query, and the list is closed once, at the end.
      const keep = shape.open === "search";
      for (const [i, text] of texts.entries()) {
        if (!allowed.includes(text) || holds(el, shape, text)) continue;
        const got = await chooseOne(el, shape, { text, term: terms[i] ?? text, consentForms, keep, asSet: true, variant, used }, t);
        if (got.reason === "not_a_set") {
          await tidy(el, t);
          return { outcome: "unexpected", reason: "not_a_set" };
        }
        if (got.outcome === "blocked") blocked.push(text); // the option shown for it is a never-fill one
        if (leftOpen.has(el)) await tidy(el, t); // a category is not an item: close it and move on
      }
      if (keep) await tidy(el, t);
    }
    // `added` is what THIS call added; `missing` what the field still lacks.
    const addedNow = allowed.filter((x) => holds(el, shape, x) && !had.some((h) => b().equivalent(h, x)));
    const missing = allowed.filter((x) => !holds(el, shape, x) && !blocked.includes(x));
    if (b().invalid(el)) return { outcome: "reverted", added: addedNow, missing, blocked };
    return { outcome: missing.length || blocked.length ? "partial" : "verified", added: addedNow, missing, blocked };
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
  const lastState = new WeakMap(); // el -> { version, mids, clicks: [{oid, text, group}], value, words }
  let stateVersion = 0;
  // Page text inside a description is a JSON string: a quote in it cannot end
  // the description early. Kept well under the backend's 320 characters.
  const quote = (text, max = 280) => {
    let s = text.length > 200 ? `${text.slice(0, 199)}…` : text;
    while (JSON.stringify(s).length > max) s = s.slice(0, -10);
    return JSON.stringify(s);
  };
  // An option that opens a group of options rather than being an answer.
  const isGroup = (o) => {
    const popup = o.getAttribute("aria-haspopup");
    return (Boolean(popup) && popup !== "false") || o.hasAttribute("aria-expanded")
      || (o.getAttribute("role") === "treeitem" && o.querySelector('[role="group"]') !== null);
  };
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
  // The options a click move may name: never a placeholder row, never a
  // never-fill one, never an item a multi widget already holds (a click would
  // un-pick it).
  const clickable = (el, shape, pop, consentForms) => {
    const multi = Boolean(shape.multi?.(el));
    return b().optionsOf(pop).filter((o) => isAnswerRow(o) && !blockedText(o.text, consentForms)
      && !(multi && (isHeld(o) || holds(el, shape, o.text))));
  };
  // At most MAX_CLICKS of them, nearest what the list shows now: from the
  // first one in view (filled up from before it at the end of the list).
  // Oids keep numbering the FULL list.
  const windowOf = (options, scroller) => {
    if (options.length <= MAX_CLICKS || !scroller) return options.slice(0, MAX_CLICKS);
    const top = scroller.getBoundingClientRect().top;
    const first = options.findIndex((o) => o.el.getBoundingClientRect().bottom > top + 1);
    const start = Math.max(0, Math.min(first < 0 ? options.length : first, options.length - MAX_CLICKS));
    return options.slice(start, start + MAX_CLICKS);
  };
  const offered = (el, shape, pop, consentForms) => windowOf(clickable(el, shape, pop, consentForms), scrollerOf(pop))
    .map((o) => ({ ...o, group: isGroup(o.el), where: pathOf(o.el, pop), place: placeOf(o.el, pop) }));
  const ids = (options) => options.map(({ oid, text, group, where }) => ({ oid, text, group, where }));
  // A click move's words. The same text under more than one category path
  // names its place, so the two moves read differently: `Click the option
  // "Other" (under "Job Board")` — choose never guesses between them.
  const describeClick = (o, shared) => {
    const verb = o.group ? "Open the group" : "Click the option";
    return shared && o.place ? `${verb} ${quote(o.text, 180)} (under ${quote(o.place, 100)})` : `${verb} ${quote(o.text)}`;
  };
  // Whether a scroll can show an option not already offered: the list is not
  // at its end, and it holds options past the window — or rows it has not
  // rendered yet (a virtualized list's scroll area reaches past its last row).
  const canScroll = (scroller, all, clicks, window) => {
    if (!scroller || scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 4) return false;
    if (clicks.length && window.at(-1) !== clicks.at(-1)) return true;
    const lastRow = all.at(-1)?.el.getBoundingClientRect();
    if (!lastRow) return false;
    const reach = lastRow.bottom - scroller.getBoundingClientRect().top + scroller.scrollTop;
    return reach < scroller.scrollHeight - Math.max(8, lastRow.height);
  };

  async function stepState(el, shape, { value, consentForms } = {}, t) {
    b().check(t);
    const version = (stateVersion += 1);
    // Passive shapes and text have no popup to explore: nothing but give_up.
    const adaptive = shape.kind === "choice" && !shape.passive;
    const held = adaptive ? heldPopup(el) : null;
    const all = held ? b().optionsOf(held.pop) : [];
    const scroller = held ? scrollerOf(held.pop) : null;
    const clicksAll = held ? clickable(el, shape, held.pop, consentForms) : [];
    const clicks = held ? offered(el, shape, held.pop, consentForms) : [];
    const box = adaptive ? searchBoxOf(el, shape, held?.pop) : null;
    const whole = String(value ?? "").trim();
    const words = box ? wordsOf(whole) : [];
    const more = held ? canScroll(scroller, all, clicksAll, windowOf(clicksAll, scroller)) : false;
    // No `close`: give_up closes. (move() still takes `close` for cleanup.)
    // Texts shown under more than one category path in the offered window.
    const shared = new Set(clicks.filter((o) => clicks.some((x) => x.text === o.text && x.where !== o.where)).map((o) => o.text));
    const candidates = adaptive ? [
      ...clicks.map((o) => ({ mid: `click:${o.oid}`, describe: describeClick(o, shared.has(o.text)) })),
      ...(box && whole ? [{ mid: "search:value", describe: "Type the applicant value into the search box" }] : []),
      ...words.map((w, i) => ({ mid: `search:word:${i}`, describe: `Type ${quote(w)} into the search box` })),
      ...(held ? [] : [{ mid: "open", describe: "Open the dropdown" }]),
      ...(more ? [{ mid: "scroll", describe: "Scroll the list to see more options" }] : []),
      GIVE_UP,
    ] : [GIVE_UP];
    lastState.set(el, { version, mids: new Set(candidates.map((c) => c.mid)), clicks: ids(clicks), value: whole, words });
    // Complete = every option is in view: not capped, nothing to scroll, and
    // not a filtered search result (a search widget's list always is one).
    const complete = Boolean(held) && shape.open !== "search" && !searched.has(el)
      && all.length <= MAX_CLICKS && !scroller;
    // The options around the offered window (never-fill ones flagged, not dropped).
    const lo = clicks.length ? all.findIndex((o) => o.oid === clicks[0].oid) : 0;
    const hi = clicks.length ? all.findIndex((o) => o.oid === clicks.at(-1).oid) + 1 : MAX_CLICKS;
    const shown = all.length <= MAX_CLICKS ? all : all.slice(lo, hi);
    return {
      version, complete, committed: shape.read(el), invalid: b().invalid(el), popupOpen: Boolean(held),
      options: flag(shown.map((o) => ({ ...o, selected: isHeld(o) })), consentForms), candidates,
    };
  }

  // One move against the state it was chosen from (`version`). A click is an
  // answer unless it opens a group (sent `as: "progress"`): a group click that
  // reveals options progressed, one that commits a value is group_committed —
  // never verified. `as: "progress"` on an option not described as a group is
  // refused unclicked (not_a_group). Outcomes:
  // verified (a click committed), progressed (the page moved on: a popup
  // opened, a search listed results, a category showed its children, the list
  // scrolled), unconfirmed (the click shows but its proof did not move),
  // closed, stale, unexpected (with a reason), blocked.
  async function move(el, shape, { mid, version, as = "answer", consentForms } = {}, t) {
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
      const w = watch(el, shape);
      try {
        const o = await open(el, shape, undefined, t, w);
        if (o.committed) return { outcome: "unexpected", reason: "committed_while_opening" };
        if (!o.pop) {
          await tidy(el, t);
          return { outcome: "unexpected", ...w.reason("no_popup") };
        }
        leftOpen.set(el, { pop: o.pop, before: o.before });
        return { outcome: "progressed" };
      } finally {
        w.stop();
      }
    }
    if (mid === "scroll") {
      const box = held && scrollerOf(held.pop);
      if (!box) return { outcome: "stale" };
      // Bring the first option past the offered window to the top, so the
      // next state's window starts there; at least one page down.
      const all = b().optionsOf(held.pop);
      const seen = new Set(last.clicks.map((c) => c.oid));
      const next = all[all.findLastIndex((o) => seen.has(o.oid)) + 1];
      const top = box.scrollTop;
      const to = next ? top + next.el.getBoundingClientRect().top - box.getBoundingClientRect().top : 0;
      b().check(t);
      box.scrollTop = Math.max(to, top + box.clientHeight);
      await b().settle(t, 120);
      return box.scrollTop === top ? { outcome: "unexpected", reason: "list_end" } : { outcome: "progressed" };
    }
    if (mid.startsWith("search:")) {
      const box = searchBoxOf(el, shape, held?.pop);
      const term = mid === "search:value" ? last.value : last.words[Number(mid.slice("search:word:".length))];
      if (!box || !term) return { outcome: "unexpected", reason: "no_search_box" };
      const before = held?.before ?? b().popups();
      if (!held) opened.set(el, before);
      const snap = snapshot(el, shape);
      // The search sequence, pressing the box only when no list is up yet.
      const { pop, unsettled } = await search(el, shape, box, term, before, t, null, { press: !held && box === el });
      searched.add(el);
      // The Enter committed a hit on its own (notes §2 rule 5). The value
      // itself is an answer; anything else is the page's pick, left for the
      // loop to name (`search_committed`), never called filled.
      if (moved(el, shape, snap)) {
        const [text] = added(el, shape, snap);
        await tidy(el, t);
        if (text && b().equivalent(text, last.value) && verify(el, shape, text, { before: snap.evidence }) === "verified") {
          return { outcome: "verified", text };
        }
        return { outcome: "unexpected", reason: "search_committed" };
      }
      if (!pop) { // nothing opened, or nothing settled: the query the engine typed is taken back
        await tidy(el, t);
        return { outcome: "unexpected", reason: unsettled ? "unsettled" : "no_popup" };
      }
      leftOpen.set(el, { pop, before });
      return b().optionsOf(pop).length ? { outcome: "progressed" } : { outcome: "unexpected", reason: "no_results" };
    }
    if (mid.startsWith("click:")) {
      // The popup must still show the list the decision was made on.
      const now = held ? offered(el, shape, held.pop, consentForms) : [];
      if (!held || !same(ids(now), last.clicks)) return { outcome: "stale" };
      const hit = now.find((o) => `click:${o.oid}` === mid);
      if (as === "progress" && !hit.group) return { outcome: "unexpected", reason: "not_a_group" };
      // A placeholder row is never an answer (only the engine's undo chooses it).
      if (!hit.group && ns.isPlaceholderText(hit.text)) return { outcome: "unexpected", reason: "placeholder" };
      const before = shape.evidence(el);
      // Brought into view, a virtualized list redraws and may reuse the row
      // for another option (notes §2 rules 3, 6): the row must still show the
      // option the decision named, in the same place, or the move is stale.
      hit.el.scrollIntoView?.({ block: "nearest" });
      await redrawn(t);
      const still = b().optionsOf(held.pop).find((o) => o.el === hit.el);
      if (!still || still.text !== hit.text || pathOf(hit.el, held.pop) !== hit.where) return { outcome: "stale" };
      const shown = b().optionsOf(held.pop).map((o) => o.text).join("\n");
      const w = watch(el, shape);
      try {
        for (const gesture of gesturesFor(hit.el)) {
          gesture(hit.el, t);
          await afterClick(el, shape, hit.el, hit.text, t);
          w.saw("pointer");
          const after = own(el, held.before) ?? (b().visible(held.pop) ? held.pop : null);
          const next = after ? b().optionsOf(after).map((o) => o.text).join("\n") : "";
          const unchanged = same(shape.read(el), before.display);
          if (next && next !== shown && unchanged) { // a category: its children are the next state
            leftOpen.set(el, { pop: after, before: held.before });
            return { outcome: "progressed" };
          }
          // Only a click that changed nothing at all gets the second gesture.
          if (!unchanged || next !== shown || !hit.el.isConnected) break;
        }
        if (hit.group) {
          // Not an answer: one that committed a value is reported, never verified.
          const committed = !same(shape.read(el), before.display);
          await tidy(el, t);
          return { outcome: "unexpected", ...(committed ? { reason: "group_committed" } : w.reason("not_committed")) };
        }
        if (queryIsValue(el, shape, hit.text)) typed.delete(el);
        await tidy(el, t);
        const got = verify(el, shape, hit.text, { before });
        if (got === "verified" || got === "unconfirmed") return { outcome: got, text: hit.text };
        return { outcome: "unexpected", ...w.reason("not_committed") };
      } finally {
        w.stop();
      }
    }
    return { outcome: "unexpected", reason: "unknown_move" };
  }

  ns.fillCore = {
    write, explore, choose, set, recommit, verify, tidy, open, readAll, own, leftOpen, stepState, move,
    snapshot, moved, takeBack,
  };
})();
