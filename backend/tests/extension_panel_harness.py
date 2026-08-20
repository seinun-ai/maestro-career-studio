"""The side panel's test apparatus: one document driver, shared by every stage.

WHY THIS MODULE EXISTS, and it is the thing the split it enabled could not do
without. `test_extension_panel.py` forecast its own cut three times before
taking it, and what blocked it every time was not the sections — those are
cleanly separated and always were — but the APPARATUS underneath them: a faked
`chrome`, a faked document tree, the four DOM readers that recover what was
painted, and the two constants every driver's spec starts from. A per-stage
split that duplicated any of that would be five copies of a fake that has to
agree with panel.js about what a render leaves behind, and the interesting
failure is precisely the copies disagreeing — silently, with every file green.

So the seam is a MODULE, decided before the cut rather than during it. What
lives here is what more than one stage file calls; what lives in a stage file
is what only that stage does. A helper that grows a second caller moves here;
one that loses its second caller moves back.

WHAT IS IN HERE, in four groups:

- THE SOURCES. `PANEL_SCRIPT_SRCS` is read off `panel.html` and `PANEL_SOURCE`
  is every script it names, concatenated in the DOCUMENT's order — which is the
  point rather than a convenience: since Task 15's split the panel is a family
  of files, and "which files, in which order" is a fact the document owns. A
  hand-kept list beside it would be a second copy, and a module added to the
  tests but not to the document is a feature that passes here and opens blank
  in a browser.
- THE FAKES. `_PANEL_FAKES_JS` is a `chrome` that records what it was asked and
  replays what the spec says, plus a document tree that remembers what was put
  in it. Neither decides anything the panel should decide. They exist because
  the panel is a DOCUMENT that talks to `chrome` — neither is optional at load
  — and because the shared node harness's own fake DOM models a FORM
  (`querySelector` answers `[data-rt-qid]` and little else) rather than a tree
  you can append regions to.
- THE READERS. `_walk`/`_by_class`/`_text`/`_jump_label`/`_rail_rows`/`_rows`
  recover what was painted from that tree. They assert nothing; a test that
  wants a claim makes it.
- THE SPEC STARTERS. `SETTINGS_REPLY`, the two job rows, the base-resume
  library and the score rows that every stage's driver builds its `api` map
  from — and `_load`, the plain boot that four of the five files use.

`_PANEL_FAKES_JS`'S OWN CONTRACT is written inside it, at the top of the
string. Read that before adding a message type to the fake: the rule is that a
message the panel sends and the fake does not know about must be VISIBLE
(recorded in `sent`) rather than quietly answered.
"""

import re

from tests.extension_fixtures import POSTING_URL, entry
from tests.extension_harness import ROOT, js_code, run_node


EXTENSION = ROOT / "extension"
DECISIONS_JS = (EXTENSION / "shared" / "decisions.js").read_text(encoding="utf-8")

PANEL_HTML = (EXTENSION / "panel" / "panel.html").read_text(encoding="utf-8")
# Read for ONE assertion, and only because the DOM cannot carry it: whether a
# disabled control LOOKS disabled is a stylesheet question, and this panel's own
# rules are what decide it (see the fork's busy test).
PANEL_CSS = (EXTENSION / "panel" / "panel.css").read_text(encoding="utf-8")
PANEL_JS = (EXTENSION / "panel" / "panel.js").read_text(encoding="utf-8")
PANEL_CODE = js_code(PANEL_JS)


def _panel_script_srcs() -> list[str]:
    """Every script panel.html loads, in the DOCUMENT's order.

    Read off the markup rather than listed here, and that is the point: since
    Task 15's split the panel is a family of files — five shared modules, a
    `stages/*.js` per rail stage and an `actions/*.js` per concern, each family
    gathered by a tiny roster, then the controller — each reading what the ones
    before it published. "Which files, in which order" is therefore a fact the
    DOCUMENT owns, and a hand-kept list beside it would be a second copy. The
    interesting failure is precisely the two disagreeing: a module added to the
    tests but not to the document is a feature that passes here and opens blank
    in a browser, and dropping a tag from the document would otherwise leave
    every test green.
    """
    srcs = re.findall(r'<script src="([^"]+)"></script>', PANEL_HTML)
    assert srcs, "panel.html loads no scripts — the pattern moved"
    return srcs


def _panel_script(src: str) -> str:
    path = (EXTENSION / "panel" / src).resolve()
    # PANEL_SOURCE is built eagerly at import, so a tag left in panel.html for
    # a DELETED file would otherwise surface as a bare FileNotFoundError at
    # collection — the least legible failure shape, and R-C is a deletion
    # round, so it is the direction that will actually fire. Name the cause
    # and the remedy instead. (The tag/disk test asserts the same direction
    # for the day this build goes lazy.)
    if not path.is_file():
        raise AssertionError(
            f"panel.html tags {src!r} but no such file exists — a deleted "
            "panel module must take its <script> tag with it")
    return path.read_text(encoding="utf-8")


PANEL_SCRIPT_SRCS = _panel_script_srcs()
PANEL_SOURCE = "\n".join(_panel_script(src) for src in PANEL_SCRIPT_SRCS)
# The panel's OWN files, which is everything the document loads that is not one
# of the `../shared/` modules the content scripts also load.
PANEL_OWN_SRCS = [src for src in PANEL_SCRIPT_SRCS if not src.startswith("../")]

_PANEL_FAKES_JS = r"""
let onActivated = null;
let onUpdated = null;
const queries = [];
const listeners = [];
const sent = [];
const writes = [];
const removals = [];
const syncWrites = [];
const broadcasts = [];

// The SW's `api` handler, as a fixture. Keys are matched as SUBSTRINGS of
// `"<METHOD> <path>"`, so a test names `/api/base-resumes` — or the tenant slug
// inside an encoded `?url=` — rather than reproducing percent-encoding by hand.
//
// The METHOD joined the string when Task 7 added a POST to `/api/jobs`: no
// substring of that path tells it apart from `/api/jobs/match?url=…`, because
// every needle short enough to match the POST also matches the read. A test
// that means the POST says `"POST /api/jobs"`. Nothing else moved — every
// existing needle was already a substring of the tail.
const wireOf = (msg) => `${msg.init?.method ?? "GET"} ${msg.path}`;
//
// A needle may name a LIST of replies, consumed in order with the last one
// repeating. The panel re-reads the match after a save, and the whole point of
// a save is that the answer is different the second time — a fixture that
// answered identically would be claiming the world does not react to what this
// extension does to it.
// The autofill profile as STATE rather than as a canned reply, because the
// interesting question about it is a read-modify-write one: does a second
// learn's GET see the first learn's PUT? A canned GET answers "no" whatever the
// panel does, so a lost update would be indistinguishable from correct
// behaviour — the fixture would be asserting its own constant.
//
// Declared by `spec.profileStore`; absent, `/api/settings/autofill` falls
// through to the ordinary canned table like every other path.
let PROFILE = null;
const profileReply = (msg) => {
  if (msg.init?.method !== "PUT") {
    return { ok: true, data: { key: "autofill_profile", value: PROFILE } };
  }
  // WHOLE OBJECT, exactly as the route behaves: `set_profile` replaces the
  // stored JSON. Merging here would hide the very failure this models.
  PROFILE = JSON.parse(msg.init.body).value;
  return { ok: true, data: { key: "autofill_profile", value: PROFILE } };
};

const apiReply = (wire) => {
  for (const [needle, reply] of Object.entries(spec.api ?? {})) {
    if (!String(wire).includes(needle)) continue;
    if (!Array.isArray(reply)) return reply;
    return reply.length > 1 ? reply.shift() : reply[0];
  }
  return { ok: false, error: `the backend is unreachable` };
};
// Replies the driver holds back until it says so. This is the seam the race
// test needs and nothing else can provide: tab A's answer has to be able to
// land AFTER the user has already switched to tab B.
const held = [];
// OLDEST FIRST by default, which is what a test wants when exactly ONE round
// trip is outstanding.
//
// `release("newest")` is for the case with two, and it is the only ordering the
// browser will actually produce there: tab A's request has already been in
// flight when the user switches, and the load tab B starts AFTER the switch is
// issued last and answers first. Draining oldest-first in that shape lets tab
// B's own load land after tab A's late write and repair it — so a stale write
// is erased by the very load it is racing, no test can see it, and a deleted
// generation guard survives. That is a harness artefact, not a browser one.
const release = (order) => {
  const queue = held.splice(0);
  if (order === "newest") queue.reverse();
  for (const settleOne of queue) settleOne();
};

// What the frames of the bound tab answer, declared per inner message type.
// A type the fixture says nothing about answers like a page nobody reached —
// which is a real state (a tab whose scripts never loaded), not a broken
// harness, so it is the default rather than a throw.
const broadcastReply = (message) => {
  const canned = (spec.frames ?? {})[message.type];
  if (canned === undefined) return { ok: false, error: "no frame answered" };
  if (message.type !== "guided_write") return { ok: true, data: canned };
  // The engine answers PER PAIR, so the fixture declares outcomes BY QID and
  // the frame reports about exactly the pairs it was sent. A canned result
  // list would let a run that wrote the wrong pairs — or none — pass.
  const outcomes = canned === true ? {} : canned;
  return { ok: true, data: [{ frameId: 0, result: message.pairs.map((pair) => ({
    qid: pair.qid, outcome: outcomes[pair.qid] ?? "filled",
  })) }] };
};

// `fill_answers` answers with the qids that STUCK — not an outcome per pair, a
// membership list — so a control that refused the value is simply absent from
// it. `true` means every pair took; an array names the ones that did, which is
// how a select whose options do not match the typed answer is modelled.
const fillAnswersReply = (message) => {
  const canned = (spec.frames ?? {}).fill_answers;
  if (canned === undefined) return { ok: false, error: "no frame answered" };
  // "gone" is the frame the SW REACHED FOR and could not talk to — a wizard
  // step that navigated under the panel, a tab reloaded. `broadcastToFrames`
  // answers with a per-frame entry carrying an error and NO `result`, which is
  // a different shape from a frame that answered with nothing, and the panel
  // says two different sentences about them.
  if (canned === "gone") {
    return { ok: true, data: [{ frameId: 0, error: "Could not establish connection" }] };
  }
  const sent = message.pairs.map((pair) => pair.qid);
  const stuck = canned === true ? sent : sent.filter((qid) => canned.includes(qid));
  return { ok: true, data: [{ frameId: 0, result: stuck }] };
};

global.chrome = {
  tabs: {
    // `tabsThrow` is the one way to make BOOT itself fail, and it exists for
    // the one thing left in the fault slot: `bindActiveTab` is what binds this
    // panel to a tab at all, and a panel that never bound shows a rail nothing
    // will ever move. A real query can reject (no focused window, a profile
    // shutting down), and without a way to make it the surviving tenant of
    // `card.fault` would have no test at all.
    query: async (info) => {
      queries.push(info);
      if (spec.tabsThrow) throw new Error("no window is focused");
      return spec.tabs ?? [];
    },
    get: async (tabId) => ({ id: tabId, url: (spec.tabUrls ?? {})[tabId] ?? "" }),
    onActivated: { addListener: (fn) => { listeners.push("onActivated"); onActivated = fn; } },
    onUpdated: { addListener: (fn) => { listeners.push("onUpdated"); onUpdated = fn; } },
  },
  // The panel reads its remembered pick straight from storage and writes one
  // back. `writes` is the whole record of that — what was stored, under which
  // KEY — and `removals` is the record of the orphan sweep, which is a
  // DIFFERENT operation and has to be visible as one: a sweep that quietly
  // became a `set(key, null)` would leave the key present with a null value,
  // which reads the same to `writes` and not the same to `chrome.storage`.
  //
  // `get` takes BOTH shapes, because the panel uses both: an object of
  // defaults (`STORE_DEFAULTS`) and a bare array of key names (`ORPHAN_KEYS`).
  // Spreading an array into an object yields index keys and would make the
  // array form silently return junk — which the sweep would then read as
  // "nothing to remove", passing for the wrong reason.
  storage: {
    local: {
      get: async (query) => {
        if (spec.storageThrows) throw new Error("storage is unavailable");
        const stored = spec.stored ?? {};
        if (Array.isArray(query)) {
          const out = {};
          for (const key of query) {
            if (Object.hasOwn(stored, key)) out[key] = stored[key];
          }
          return out;
        }
        return { ...query, ...stored };
      },
      set: async (patch) => { writes.push(patch); },
      remove: async (keys) => { removals.push(keys); },
    },
    // The SETTINGS store, and a different list on purpose: `sync` follows the
    // profile to every browser the user signs into, `local` does not. A test
    // that could not tell them apart would let a session pick be written to
    // the wrong one and never say so.
    sync: {
      set: async (patch) => { syncWrites.push(patch); },
    },
  },
  runtime: {
    sendMessage: async (msg) => {
      sent.push(msg);
      if (msg.type === "api") {
        const wire = wireOf(msg);
        const reply = (spec.profileStore !== undefined
                       && msg.path === "/api/settings/autofill")
          ? profileReply(msg)
          : apiReply(wire);
        if ((spec.hold ?? []).some((needle) => wire.includes(needle))) {
          return new Promise((resolve) => held.push(() => resolve(reply)));
        }
        return reply;
      }
      // The page fan-out, answered by INNER type the way `panel_frame0` is: a
      // guided fill asks the page three different questions on one message
      // type, and one reply for all of them would make the interesting ones
      // unaskable.
      if (msg.type === "page_broadcast") {
        broadcasts.push(msg);
        const reply = msg.message.type === "fill_answers"
          ? fillAnswersReply(msg.message)
          : broadcastReply(msg.message);
        // HELD like an api reply, and named the same way: `page_broadcast:` +
        // the inner type. A fan-out is a round trip the user can walk away
        // from exactly as they can walk away from a POST, and the pause row's
        // whole write is one — so without this seam its race is unaskable.
        return (spec.hold ?? []).includes(`page_broadcast:${msg.message.type}`)
          ? new Promise((resolve) => held.push(() => resolve(reply)))
          : reply;
      }
      // ONE door, two questions: `detect_page` and `extract_job_posting` both
      // ride `panel_frame0`, so a fixture that has something to say about a
      // particular one keys on the INNER type. `replies` stays the fallback for
      // the tests that only care that the door answers at all.
      //
      // A needle may name a LIST of replies, consumed in order with the last
      // one repeating — the same shape `apiReply` uses. The picker race needs
      // it: tab A's apply page has a form, tab B's posting does not, and a
      // canned True for both would make the hasForm gate unaskable.
      if (msg.type === "panel_frame0" && (spec.page ?? {})[msg.message?.type]) {
        const canned = spec.page[msg.message.type];
        if (!Array.isArray(canned)) return canned;
        return canned.length > 1 ? canned.shift() : canned[0];
      }
      // The SW's own reply shape, including the failure one: a panel that only
      // ever sees `{ok: true}` in tests is a panel whose error path is fiction.
      return (spec.replies ?? {})[msg.type]
        ?? { ok: false, error: `the backend is unreachable` };
    },
  },
};

// The clipboard, which the panel may reach for DIRECTLY — it is an extension
// document with a real gesture behind every press, so there is no content-script
// relay to model. A list rather than a last-value, because "one press, one
// write" is a claim a test makes: a Copy that fired twice per click would be
// invisible to an assertion about the final contents.
//
// `spec.clipboardThrows` is the other half, and it is not decoration: a
// clipboard write CAN be refused (a document that lost focus is the ordinary
// way), and the panel says so in the note slot. Without a way to make it fail
// that sentence would be fiction.
//
// `defineProperty` and not an assignment: node ships its OWN `navigator` global
// (21+), read-only, so `global.navigator = …` fails silently and every test here
// would then drive node's — which has no clipboard, and reports that as a
// TypeError inside the panel rather than as a missing fake.
const copies = [];
Object.defineProperty(globalThis, "navigator", {
  configurable: true,
  value: {
    clipboard: {
      writeText: async (text) => {
        if (spec.clipboardThrows) throw new Error("document is not focused");
        copies.push(text);
      },
    },
  },
});

// WHAT THIS DOES NOT MODEL, so a test never reads more into it than is there:
// event bubbling, capture, propagation or default actions; event objects
// beyond `{target}`; `textContent` reading back the text of descendants
// (setting it clears children, reading it returns only this node's own text —
// use `_text` on the Python side to join a subtree); layout, visibility,
// selectors, or removal. Each is a seam that would have to be BUILT, not a
// browser behaviour that is silently half-present.
//
// FOCUS AND SCROLL ARE MODELLED, and this paragraph used to say they were not.
// They arrived with `withPlaceKept` — the render loop now CAPTURES both around
// the rail's rebuild and puts them back — and that is a claim no assertion
// could reach without them: a fake where `focus()` does nothing reports a
// perfect restore and a broken one identically. What is modelled is exactly
// what the panel uses and no more: `focus()` moves one pointer,
// `document.activeElement` reads it back, `scrollTop` is a plain number nobody
// but the panel writes, and `getElementById` can find a node the render loop
// BUILT rather than only the four regions panel.html ships. There is no focus
// order, no tab ring, no scroll clamping and no selection — a test that wants
// to claim any of those is claiming something this fake cannot know.
if (spec.profileStore !== undefined) PROFILE = spec.profileStore;

// Whichever node last had `focus()` called on it, and the whole of the fake's
// focus model. A single pointer rather than a per-node flag, because that is
// the property the panel reads (`document.activeElement`) and a second focused
// node is a state a browser does not have.
let ACTIVE = null;

let uid = 0;
class FakeNode {
  constructor(tag) {
    this.uid = (uid += 1);    // identity across renders; nothing in the DOM
    this.tagName = String(tag).toUpperCase();
    this.className = "";
    this.textContent = "";
    this.children = [];
    this.attrs = {};
    this.props = {};          // whatever style.setProperty wrote (the rings)
    this.handlers = new Map();
    this.dispatched = [];
    // Written by the render loop's place-keeping and by nothing else. Zero
    // rather than undefined so a restore that ran before anything scrolled
    // writes a number back rather than `undefined`.
    this.scrollTop = 0;
  }
  /** The panel calls this on a node it just found by id. It is the ONLY way
   * anything becomes active here — there is no click-focuses-the-button rule,
   * because the panel never relies on one.
   *
   * THE OPTIONS ARE KEPT, and that is the whole of what this fake can say about
   * scrolling on focus. A browser scrolls the nearest scrollable ancestor to
   * reveal a control it judges out of view — which silently overrides a
   * scrollTop the panel has just restored — and `preventScroll` is the request
   * not to. WHETHER it would scroll depends on layout, which this fake does not
   * have and must not pretend to; what it can record faithfully is the REQUEST
   * the panel made. A test that wants the guarantee asserts on this rather than
   * on a scroll position the fake would have had to invent.
   */
  focus(options) { ACTIVE = this; this.focusOptions = options ?? null; }
  get style() { return { setProperty: (n, v) => { this.props[n] = String(v); } }; }
  append(...kids) { for (const kid of kids) this.children.push(kid); }
  /** …and the SCROLL GOES WITH THEM, which is the one browser behaviour here
   * that had to be modelled rather than left out. Emptying an element collapses
   * its scroll height, so the browser puts `scrollTop` back to 0 and the new
   * children arrive at the top; that is precisely the cost `withPlaceKept`
   * exists to pay back. A fake that quietly KEPT the number would report a
   * panel with no restore at all as a perfect one — the assertion would be
   * reading its own setup. */
  replaceChildren(...kids) {
    this.children = [];
    this.textContent = "";
    this.scrollTop = 0;
    this.append(...kids);
  }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  getAttribute(name) { return this.attrs[name] ?? null; }
  addEventListener(type, fn) {
    if (!this.handlers.has(type)) this.handlers.set(type, []);
    this.handlers.get(type).push(fn);
  }
  /** Record what was fired, and REFUSE what nothing listens for — the same
   * rule the boot driver's `fire` follows one layer up. A `change` dispatched
   * at a control the panel never wired would otherwise do nothing and pass,
   * which is exactly how a wiring test goes green without a wiring. */
  dispatch(type, event = { target: this }) {
    this.dispatched.push(type);
    const handlers = this.handlers.get(type);
    if (!handlers) {
      throw new Error(`nothing listens for "${type}" on <${this.tagName.toLowerCase()}>`);
    }
    for (const fn of handlers) fn(event);
  }
  click() { this.dispatch("click"); }
}

// The document, mirroring panel.html: three regions, and inside the footer the
// two nodes the render loop addresses separately — the live note it writes
// through and the controls it rebuilds.
//
// `head` IS ABSENT because panel.html has no such region any more — the brand
// row was Chrome's own side-panel title said a second time, and it is deleted.
// This map is what makes that stick from the test side: it is the WHOLE of the
// document the panel is allowed to address, so a `region("head")` that came
// back would find nothing and throw here rather than render into a void.
const REGIONS = {
  identity: new FakeNode("div"),
  rail: new FakeNode("ol"), foot: new FakeNode("div"),
};
const NOTE = new FakeNode("div");
NOTE.className = "note";
NOTE.setAttribute("aria-live", "polite");
const CONTROLS = new FakeNode("div");
CONTROLS.className = "foot-controls";
REGIONS.foot.append(NOTE, CONTROLS);
const BY_ID = { ...REGIONS, note: NOTE, "foot-controls": CONTROLS };

/** A node the RENDER LOOP built, found by the id it assigned. The document's
 * own six are `BY_ID`; everything else is somewhere in one of their subtrees,
 * and searching for it is what makes the focus restore askable — a
 * `getElementById` that only knew panel.html's ids would answer `null` for
 * every control the panel actually restores focus to, and the restore would
 * test as a silent no-op. Depth-first, first match wins, which is the
 * document's own rule for a duplicated id. */
const findById = (node, id) => {
  if (node.id === id) return node;
  for (const kid of node.children) {
    const found = findById(kid, id);
    if (found) return found;
  }
  return null;
};

global.document = {
  getElementById: (id) => {
    if (BY_ID[id]) return BY_ID[id];
    for (const root of Object.values(REGIONS)) {
      const found = findById(root, id);
      if (found) return found;
    }
    return null;
  },
  createElement: (tag) => new FakeNode(tag),
  // A live read, like the real one: the panel captures it BEFORE a rebuild and
  // the node it names is thrown away by that rebuild, which is the whole
  // reason the restore has to travel as an id and not as a reference.
  get activeElement() { return ACTIVE; },
};

// `value`, `id` and `disabled` are plain properties the panel assigns — the
// fake models no accessor for them, and none is wanted. They are in the
// snapshot because since Task 7 the rail holds INPUTS, and what an input shows
// and whether a button can be pressed are the two things those tests read.
//
// `selected` IS THE FOURTH, and it arrived with the switcher's honesty fix. A
// browser DISPLAYS the first option of a `<select>` when no option is selected,
// so "which option is selected" and "which option the user sees named" are the
// same question — and it is a question no other field here can answer. Without
// it, a picker that displayed a draft nobody chose was indistinguishable from a
// correct one, which is exactly how that defect reached a screenshot. Read as
// `=== true` for the same reason `disabled` is: an option nobody touched has no
// such property at all.
const snapshot = (node) => ({
  uid: node.uid,
  tag: node.tagName, class: node.className, text: node.textContent,
  attrs: node.attrs, href: node.href ?? null, props: node.props,
  id: node.id ?? null, value: node.value ?? null, disabled: node.disabled === true,
  selected: node.selected === true,
  children: node.children.map(snapshot),
});
const regions = () => Object.fromEntries(
  Object.entries(REGIONS).map(([id, node]) => [id, snapshot(node)]));
const withClass = (node, cls) => [
  ...(node.className.split(" ").includes(cls) ? [node] : []),
  ...node.children.flatMap((kid) => withClass(kid, cls)),
];
// TIMERS ARE COLLAPSED, and the delays are RECORDED instead. The one timed
// thing in the panel is `loadHasForm`'s detection backoff, measured in whole
// seconds; a driver that actually slept through it would add its whole
// schedule to every test on this page and buy no assertion, because the claims
// are about the SEQUENCE and the COUNT, not the wall clock. `delays` is the
// half that keeps the bound askable: the schedule is still readable, so a test
// can pin "three retries, growing" rather than take the fake's word for it.
//
// `settle`'s own zero-delay ticks are not recorded — a zero is not a wait.
const delays = [];
const realSetTimeout = global.setTimeout;
global.setTimeout = (fn, ms, ...rest) => {
  if (ms) delays.push(ms);
  return realSetTimeout(fn, 0, ...rest);
};

// The panel's boot is a chain of awaited messages; nothing here is timed, so
// draining the microtask/macrotask queues a few times is enough to land it.
//
// THIRTY rather than ten since the detection backoff: each retry costs a
// macrotask of its own (a collapsed sleep) plus the round trip after it, and
// they run BESIDE the rest of the load rather than inside it. Ten ticks landed
// the boot and stopped in the middle of the retry schedule, which reads as
// "the late answer never came" — a fake settling too early is a false negative
// on every test the retry exists for.
const settle = async () => {
  for (let i = 0; i < 30; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
};
"""

APPLY_URL = "https://acme.wd5.myworkdayjobs.com/en-US/careers/apply/applyManually"
OTHER_URL = "https://boards.other.test/somewhere"
APP_URL = "http://localhost:3000"
SETTINGS_REPLY = {"ok": True, "data": {
    "backendUrl": "http://localhost:8001", "appUrl": APP_URL,
    "telemetryEnabled": True, "eeoAutofillEnabled": False}}
# What Add job says when there is nothing on the page and nothing was typed.
NOTHING_TO_SAVE = "Nothing to save yet"

def _walk(node):
    yield node
    for kid in node["children"]:
        yield from _walk(kid)


def _by_class(node, cls):
    """Every node in this subtree carrying `cls`.

    THE EMPTY STRING IS A TEST BUG, not a query for "everything", and it
    raises here rather than answering. `"" in "a b".split()` is False for every
    node ever built, so `_by_class(node, "")` is ALWAYS `[]` — which means an
    assertion written over it passes whatever the panel rendered. Task 15
    shipped exactly that: the Track stage's single-writer pin read
    `[n for n in _by_class(body, "") if n["tag"] == "BUTTON"] == []`, and a
    planted unclassed "Mark applied" button wired to `setStatus` passed the
    whole suite. A query that can only ever be empty is not a narrow query, it
    is a broken one, and it must not be silently available.

    Walk with `_walk` when the question is about a TAG rather than a class.
    """
    if not cls:
        raise ValueError(
            "_by_class needs a class; the empty string matches nothing, ever — "
            "use _walk when the question is not about a class")
    return [found for found in _walk(node) if cls in found["class"].split()]


def _text(node):
    parts = [node["text"], *(_text(kid) for kid in node["children"])]
    return " ".join(part for part in parts if part).strip()


def _jump_label(item):
    """One residue row's NAME — the jump button and the kind mark, without the
    affordances that hang off them.

    `_text` over the whole `<li>` folds the pause box's option list and its two
    button labels into the field's name, which reads as a passing assertion
    about a very strange field. The name is the row's first children; what is
    dropped is a sibling after them — the pause box (`needs`) and, since Task
    14, the essay row's handoff into the QnA drawer (`ask`). Both are things
    the row OFFERS rather than things it is called, and a test about the essay
    handoff should reach for that button by name rather than find it folded
    into a label.
    """
    skip = {"needs", "ask"}
    return " ".join(
        part for part in
        (_text(kid) for kid in item["children"] if kid["class"] not in skip)
        if part).strip()

def _rows(rail_rows):
    return {row["key"]: row for row in rail_rows}

LIGHTNING_JOB = {"id": "job-lightning", "company": "Lightning AI",
                 "title": "Research Engineer"}
ACME_JOB = {"id": "job-acme", "company": "Acme", "title": "Data Scientist"}
# ORDER MATTERS, and it is the opposite of the ranking on purpose. The library
# default is the FIRST row (`data_scientist`, 71.6) while the remembered pick in
# `_entry` is the OTHER one (`ai_ml_engineer`, 68.4) — so "the restored slug
# survived" and "the default/ranking won" produce different numbers on the
# Before ring. With the two aligned, three separate guards in panel.js were
# unobservable: the `!card.baseSlug` divergence, the `!card.baseSelected` rule,
# and setting `baseSelected` on restore at all.
BASE_RESUMES = [{"slug": "data_scientist", "display_name": "Data Scientist"},
                {"slug": "ai_ml_engineer", "display_name": "AI/ML Engineer"}]
SCORES = [
    {"target_type": "base_resume", "target_id": "ai_ml_engineer", "phase": "base",
     "composite": 68.4},
    {"target_type": "base_resume", "target_id": "data_scientist", "phase": "base",
     "composite": 71.6},
    {"target_type": "application", "target_id": "app-1", "phase": "tailored",
     "composite": 84.2},
]

def _reply(data):
    return {"ok": True, "data": data}


def _rail_rows(out):
    """The rail as `railModel` rows, recovered from what was rendered."""
    return [
        {"key": key,
         "state": row["class"].removeprefix("stg").strip(),
         # The NUMERAL as painted — "✓" or the step number. Recovered because
         # the tick and the state are two different facts since `railModel`
         # grew `ticked`: the terminal row is `active` AND ticked, so a reader
         # that only knew the class could not tell a finished rail from one
         # that had merely stopped on its last step.
         "numeral": _by_class(row, "stg-num")[0]["text"],
         "summary": _by_class(row, "stg-sum")[0]["text"]}
        for key, row in zip(["job", "score", "resume", "fill", "track"],
                            _by_class(out["regions"]["rail"], "stg"), strict=True)
    ]

_PANEL_LOAD_DRIVER_JS = _PANEL_FAKES_JS + r"""
loadModules();
main(async () => {
  await settle();
  // `writes` too, because a plain load is not always write-free: the restore
  // sweeps the key Task 8's split retired.
  emit({ regions: regions(), sent, writes, removals });
});
"""

def _load(tmp_path, **spec):
    """Boot the real panel on one tab and report what it painted."""
    spec.setdefault("tabs", [{"id": 7, "url": POSTING_URL}])
    spec.setdefault("replies", {"read_settings": SETTINGS_REPLY})
    return run_node(_PANEL_LOAD_DRIVER_JS, spec, tmp_path,
                    source=PANEL_SOURCE)

def _armed_entry():
    """A base-as-is arming (Task 9 writes these): no application at all, so the
    only thing it restores is that the user chose to fill from their base."""
    return entry(applicationId=None, baseArmed=True, pdfReady=False,
                  jobId=None, company=None, title=None)


# A SECOND library, whose own order is deliberately NOT its ranked order.
# `BASE_RESUMES`/`SCORES` above cannot arm a ranking test: there
# `data_scientist` is both the first row AND the better score, so "ranked" and
# "as the library listed them" produce the same list. Here the unscored resume
# is first and the best one is last, so an implementation that skipped
# `rankBaseResumes` renders visibly.
#
# HERE rather than in the Score file because three files spend it — the Score
# stage ranks it, the Resume stage tailors from a pick made against it, and the
# shell's retired-key sweep reads a ring off it. A second copy would be three
# libraries that agree today.
SCORE_RESUMES = [
    {"slug": "swe_backend", "display_name": "Backend Engineer"},
    {"slug": "data_scientist", "display_name": "Data Scientist"},
    {"slug": "ai_ml_engineer", "display_name": "AI/ML Engineer"},
]
SCORE_ROWS = [
    {"target_type": "base_resume", "target_id": "data_scientist", "phase": "base",
     "composite": 63.6, "engine_version": "ats-2.3.0"},
    {"target_type": "base_resume", "target_id": "ai_ml_engineer", "phase": "base",
     "composite": 71.8, "engine_version": "ats-2.3.0"},
]


def _posts(out):
    """Every backend POST the panel sent, in order.

    The `api` message carries its method in `init`, so a POST is not tellable
    from the read beside it by path alone — `/api/jobs` and
    `/api/jobs/match?url=…` share every needle short enough to match the write.
    """
    return [msg for msg in out["sent"]
            if msg["type"] == "api" and (msg.get("init") or {}).get("method") == "POST"]
