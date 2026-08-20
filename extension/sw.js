/* Maestro CS Companion — service worker.
 *
 * Two jobs.
 *
 * 1. Reaching the UI: the toolbar icon and the keyboard shortcut both open the
 *    side panel, which since R-C is the extension's only surface. Both land
 *    here, because neither `chrome.action`/`chrome.sidePanel` nor
 *    `chrome.commands` is exposed to a content script. See "reaching the UI"
 *    below.
 *
 * 2. Every backend call the extension makes from a content script goes
 *    through here. That is not a convenience — see below.
 */

// ---------- settings ----------
//
// The one place a default lives, and the rule any UI must not break: the panel
// asks for these over `read_settings` at boot rather than keeping a copy. An
// earlier panel kept one, which is why the rule is written down rather than
// assumed.

const DEFAULTS = {
  backendUrl: "http://localhost:8001",
  appUrl: "http://localhost:3000",
  telemetryEnabled: true,
  // Legacy; fill decisions use backend eeo_consent.enabled instead.
  eeoAutofillEnabled: false,
  // The panel's Fill stage: "assist" runs the /choose step, "rules" skips it
  // entirely (the runner's `aiAssist`). A DEFAULT here rather than in the panel
  // for this section's whole reason — a second copy is the one that drifts —
  // and it is `"assist"` because that is the pass that answers more of the
  // form; rules-only is the deliberate narrowing, which is a thing a user
  // chooses rather than a thing they are given.
  //
  // `sync` like every other setting here, so the choice follows the profile.
  // The panel READS it through `read_settings` and WRITES the key directly:
  // reads come through the SW so the defaults stay in one place, writes need
  // no defaults and land in the same store.
  fillMode: "assist",
};

async function getSettings() {
  const stored = await chrome.storage.sync.get(DEFAULTS);
  return { ...DEFAULTS, ...stored };
}

/* The only fetch site the extension has, and the only one a CONTENT SCRIPT
 * gets. Moved from the first side panel's copy unchanged at Task 8; that copy
 * is gone, and the panel at `extension/panel/` has not reintroduced one — a
 * panel is an extension page, so it CAN fetch directly, which is exactly why
 * the rule has to be stated rather than enforced by the environment. It
 * proxies through this router like everything else, and its own header
 * comment carries the same rule.
 *
 * Why it has to live here rather than in the content script that wants the
 * data: `backend/app/main.py:36-48` allows `http://localhost:3000`,
 * `http://127.0.0.1:3000` and the regex `chrome-extension://.*` — and nothing
 * else. Asked what it answers a preflight carrying
 * `https://acme.wd5.myworkdayjobs.com`, that app returns 400 with no
 * `Access-Control-Allow-Origin`; the same preflight from a `chrome-extension://`
 * origin returns 200 and the header back. Pinned by
 * `test_backend_cors_admits_the_extension_and_no_ats_host`. Every call below
 * sends `Content-Type: application/json`, which is not a CORS-safelisted value,
 * so each one is preflighted rather than only the writes.
 *
 * A fetch issued by a content script is documented to carry the PAGE's origin
 * rather than the extension's, which is what makes the difference load-bearing
 * — but that half is UNVERIFIED HERE (see the module note in
 * backend/tests/test_extension_manifest.py). The SW's own fetch presents the
 * chrome-extension:// origin the backend already allows either way, so routing
 * through here is correct under both readings. Widening backend CORS to admit
 * arbitrary ATS hosts is the trade this exists to avoid.
 */
async function api(path, opts = {}) {
  const { backendUrl } = await getSettings();
  const res = await fetch(`${backendUrl}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch (_) { /* keep status */ }
    const err = new Error(detail);
    // THE STATUS RIDES THE ERROR, and it is the only thing that can tell a
    // caller "this resource is gone" from "we could not ask". Everything else
    // about a failure here is a SENTENCE — the backend's `detail` when it sent
    // one, the bare status when it did not — and a caller that had to read
    // meaning out of it would be matching on prose the backend is free to
    // rewrite. A `fetch` that rejects (no network, the SW asleep, a backend
    // that is not running) never reaches this line at all, so a status on the
    // error means an HTTP answer was received and read; its ABSENCE is the
    // other half of the same fact and is equally load-bearing. The panel's
    // ghost-binding unbind turns on exactly this discrimination — see
    // `ask` in panel.js, which puts the field back on the far side of the
    // message boundary, and the router's catch below, which carries it there.
    err.status = res.status;
    throw err;
  }
  return res.status === 204 ? null : res.json();
}
// ---- end api ----

// ---------- frames ----------
//
// Content scripts run in EVERY frame (`all_frames`), so a tab id does not
// identify a sender and the SW is the only context that can tell the frames
// apart — `sender.frameId` is added by the browser and cannot be forged by
// page script. Greenhouse and Lever put the whole application form in a
// subframe while the top frame is marketing, which is why the fill side has to
// address one frame rather than one tab (design §3.1).

/** `${tabId}:${frameId}` for a message sender, or null if it is not an
 * addressable frame. `frameId` 0 is the top frame.
 *
 * Null covers any extension page: such a sender carries no `sender.tab`, and
 * "undefined:0" would collide all of them onto one key. It also covers
 * `tab.id === -1`, which is Chrome's "no tab" — a real number that would key
 * and then address nothing.
 *
 * Neither half is defaulted. A missing `frameId` filled in as 0 would name the
 * TOP frame, so a fill aimed at a subframe would land somewhere else; refusing
 * to produce a key fails loudly instead. */
function frameKey(sender) {
  const tabId = sender?.tab?.id;
  const frameId = sender?.frameId;
  // Number.isInteger, not `typeof === "number"`: NaN, Infinity, 7.5 and 1e21
  // all pass a typeof check and all mint a key that `parseFrameKey` then
  // refuses — a key that cannot be addressed again is worse than no key.
  if (!Number.isInteger(tabId) || tabId < 0) return null;
  if (!Number.isInteger(frameId) || frameId < 0) return null;
  return `${tabId}:${frameId}`;
}
// ---- end frameKey ----

/** The inverse. Numbers, because `chrome.tabs.sendMessage` takes numbers and a
 * string tab id silently addresses nothing. */
function parseFrameKey(key) {
  const match = /^(\d+):(\d+)$/.exec(String(key));
  if (!match) return null;
  return { tabId: Number(match[1]), frameId: Number(match[2]) };
}
// ---- end parseFrameKey ----

/** The tab a fan-out lands on, resolved from WHO is asking.
 *
 * Two sender shapes, trusted differently — and since R-C only ONE of them has
 * a caller in this repo. A top-frame content script fans out to ITS OWN tab,
 * full stop: `msg.tabId` is ignored for it, because a page's frame must never
 * aim the engine at another tab (the sendToFrame rules, restated for
 * broadcast), and a subframe may not fan out at all — a broadcast request
 * arriving from a subframe of a Greenhouse posting is an ad iframe, not a UI.
 *
 * THAT BRANCH IS KEPT DELIBERATELY NOW THAT NOTHING TAKES IT. The floating
 * card was its one caller and R-C deleted it, so every fan-out in the shipped
 * extension is the panel's. Deleting the branch would not tighten anything the
 * `sender.tab === undefined` discriminator below does not already decide — it
 * would only move the refusal from a named error to an unreadable one, and it
 * would delete the written rule for the next content-script caller, which is
 * the thing worth keeping. Read it as: if a content script ever fans out
 * again, these are its terms, already decided.
 *
 * The side panel is our own UI with no tab at all, so it names the tab it is
 * bound to — it is an extension page and the tab it renders for is a fact only
 * it holds. `sender.tab === undefined` is the discriminator, and it is not
 * fakeable from a page: a page cannot reach `onMessage` in the first place (no
 * `externally_connectable`, and the listener drops anything not sent by this
 * extension), and a content script cannot shed the `tab` the browser attaches
 * — the same reason `sender.frameId` is trusted above. Note what that leaves
 * to the id check at the top of `onMessage`: tab-less is now the TRUSTED
 * shape, so for a tab-less sender that check is the only thing establishing
 * the message came from us at all, rather than a second opinion behind this
 * one.
 *
 * WHERE THIS STOPS. It answers WHO may name a tab; WHICH tab is named is the
 * panel's own to get right, and the SW cannot check it — a tab id is valid or
 * it is not, and "the tab the user is actually looking at" is not a fact
 * reachable from here. So a panel that let its binding go stale across a tab
 * switch would aim a fill or a PDF at the wrong tab and this function would
 * pass it. The guard is the panel's binding discipline, not this.
 *
 * What this does NOT relax: which frames may RECEIVE user data. That gate is
 * `frameMayReceiveUserData` in the content scripts, on the receiving side of
 * every message this resolves a tab for, and nothing here touches it. */
function fanoutTab(msg, frame, sender) {
  if (sender?.tab === undefined) {
    const tabId = msg?.tabId;
    // Rejects the wild shapes — undefined, null, NaN, -1, a string. It needs no
    // round trip the way frameKey's rule did: an integer naming no real tab
    // dies at sendMessage as a dead message, not as a message somewhere else.
    if (!Number.isInteger(tabId) || tabId < 0) throw new Error(`panel named no tab: ${tabId}`);
    return tabId;
  }
  const from = parseFrameKey(frame);
  if (!from) throw new Error("sender is not an addressable frame");
  if (from.frameId !== 0) throw new Error(`only the top frame may fan out (from ${frame})`);
  return from.tabId;
}
// ---- end fanoutTab ----

/** Dispatch to one frame on behalf of the frame that asked. The `frameId`
 * option is the whole point: without it the message goes to every frame.
 *
 * `key` arrives in a MESSAGE, from a content script running on a page we do
 * not trust, and the recipient is our own fill engine. A bare
 * `sendToFrame(msg.frame, …)` would therefore let any frame aim that engine at
 * any other frame — so the sender comes first, and two rules apply.
 *
 * SAME TAB. Without it a frame on one posting could drive a fill in a
 * completely different tab, which no user gesture anywhere would have asked
 * for.
 *
 * TOP FRAME ONLY, which is the sibling question answered: a frame may not name
 * a sibling. A request to message another frame that comes FROM a subframe is
 * not a UI asking — on a Greenhouse posting it is an ad iframe. The top frame
 * may still address the application subframe, because reaching a form in an
 * iframe is the whole job. Fan-out ("fill every frame") is not this function:
 * the SW picks those targets itself, behind the explicit user click
 * design.md:125 requires, and never from a key a page's frame supplied.
 *
 * Like `fanoutTab`'s content-script branch, this is a rule with no caller in
 * the tree since R-C removed the in-page UI. It is the decided answer for the
 * next one, not dead weight. */
async function sendToFrame(sender, key, message) {
  const from = parseFrameKey(frameKey(sender));
  if (!from) throw new Error("sender is not an addressable frame");
  if (from.frameId !== 0) {
    throw new Error(`only the top frame may name a target (from ${from.tabId}:${from.frameId})`);
  }
  const target = parseFrameKey(key);
  if (!target) throw new Error(`not a frame key: ${key}`);
  if (target.tabId !== from.tabId) throw new Error(`cross-tab target ${key} from tab ${from.tabId}`);
  return chrome.tabs.sendMessage(target.tabId, message, { frameId: target.frameId });
}
// ---- end sendToFrame ----

/** agent.js's answer, unwrapped — or a throw carrying the reason.
 *
 * `sendResponse` has no reject channel, so the page reports failure IN the
 * payload (`{ok: false, error}`), and a listener that returned without
 * answering resolves as undefined — no content script in that frame. Three
 * shapes, one of which is a value and two of which are reasons.
 *
 * The two callers dispose of the throw differently and that difference is
 * theirs to make, not this function's: `broadcastToFrames` catches it per
 * frame, `panel_frame0` lets it travel. What is shared is the READING, which
 * is a contract with agent.js — so it is written once rather than in two
 * places that could drift apart while both look right. */
function unwrapPageReply(reply) {
  if (!reply) throw new Error("no reply from the page");
  if (!reply.ok) throw new Error(reply.error ?? "the page reported an error");
  return reply.data;
}
// ---- end unwrapPageReply ----

/** Ask EVERY frame of one tab, and return `[{frameId, result, error?}]`.
 *
 * The array shape is the FIRST side panel's `callAllFrames`, deliberately, and
 * it has now outlived two consumers: that panel (deleted at Task 19, this
 * function inherited its contract and its tests) and the floating card (R-C).
 * The panel at `extension/panel/` reads the same array back unchanged — the
 * aggregation on top of it, the flatMaps and the per-frame host map and the
 * attach reduce, was written against this shape and never had to move. That is
 * the whole return on never having altered it.
 *
 * A frame that cannot be reached or that throws contributes `result:
 * undefined` rather than aborting: an ATS page carries ad and analytics
 * iframes that will never answer, and one of them must not cost the user the
 * application form. The REASON is kept — "unreachable frame", "message type
 * nothing handles" and "the engine threw" are three different bugs that
 * otherwise arrive as one silent empty result.
 *
 * UNVERIFIED, and the same gap `callAllFrames` documents: that
 * `chrome.webNavigation.getAllFrames` answers with a promise when given no
 * callback. It is the MV3 form and every other API here is used that way, but
 * that is one API's evidence for another's. The `?? []` is what keeps the
 * failure a "nobody answered" rather than a TypeError. */
async function broadcastToFrames(tabId, message) {
  const frames = (await chrome.webNavigation.getAllFrames({ tabId })) ?? [];
  return Promise.all(frames.map(async (frame) => {
    try {
      const reply = await chrome.tabs.sendMessage(tabId, message, { frameId: frame.frameId });
      // Swallowed below rather than allowed to abort the fan-out: an ATS page
      // carries ad and analytics iframes that will never answer.
      return { frameId: frame.frameId, result: unwrapPageReply(reply) };
    } catch (err) {
      const error = String(err?.message ?? err);
      console.warn(`frame ${frame.frameId} did not answer ${message?.type}:`, error);
      return { frameId: frame.frameId, result: undefined, error };
    }
  }));
}
// ---- end broadcastToFrames ----

/** Defense in depth, at the only place an observation can leave the browser.
 *
 * Whatever future code puts on an observation, only the contract keys are
 * posted — a stray `value`, `was` or `answer` can never leak. The backend's
 * two models are `extra="forbid"` as well, so this is the second of three
 * gates; it exists because the first one is code somebody will edit. */
function scrubObservation(observation) {
  const TELEMETRY_KEYS = ["label", "kind", "rule_id", "options", "outcome", "host"];
  const out = {};
  for (const key of TELEMETRY_KEYS) {
    if (observation?.[key] !== undefined) out[key] = observation[key];
  }
  out.label = String(out.label ?? "").slice(0, 160);
  if (Array.isArray(out.options)) {
    out.options = out.options.slice(0, 30).map((text) => String(text).slice(0, 160));
  } else {
    delete out.options;
  }
  return out;
}
// ---- end scrubObservation ----

// ---------- reaching the UI ----------
//
// ONE surface, two routes to it: the toolbar icon (via `setPanelBehavior` at
// the bottom of this section) and the keyboard shortcut. Both open the side
// panel; neither can be reached from a content script, which is why they live
// here.
//
// THE COMMAND KEY IS `toggle-widget` AND STAYS THAT WAY, which is a lie about
// this extension's UI and the cheaper of the two lies available. Chrome keys a
// user's rebinding at chrome://extensions/shortcuts by the command NAME, so
// renaming this silently discards every custom binding anyone has made and
// hands them the suggested key back — a settings loss, for a string no user
// ever sees. What they DO see is the manifest's `description`, and that says
// "Open the Maestro CS panel on this page". Same reasoning as the
// `widget.session` storage key: an identifier holding user state keeps its
// historical name; the name is documentation's problem, not the user's.
const TOGGLE_COMMAND = "toggle-widget";

/** The content scripts, in the manifest's injection order.
 *
 * Read from the manifest rather than restated, because a list that has to be
 * kept in step with `content_scripts.js` by hand is a list that will not be:
 * the ordering is load-bearing (each file publishes onto the namespace the
 * next one reads) and a missing entry fails as "the panel's page work finds
 * no handler in the tab".
 */
function contentScriptFiles() {
  const scripts = chrome.runtime.getManifest().content_scripts ?? [];
  return scripts.flatMap((entry) => entry.js ?? []);
}

/** Put the content scripts into a tab that does not have them.
 *
 * A content script enters a page when the PAGE loads, so a tab that was
 * already open when the extension was installed or reloaded has none — and
 * until this existed every route into that tab simply failed there. The user
 * pressed a button, nothing happened, and the only fix was to know that
 * reloading the tab was required.
 *
 * `chrome.scripting.executeScript` is the documented way to close that gap. It
 * has ONE door — `panel_prepare` — and never runs on page load, because
 * injecting into a page nobody asked about is exactly the always-on cost the
 * detection gate exists to avoid.
 *
 * THREE SENDERS GO THROUGH THAT DOOR, not one: "Start fill" and "Attach
 * resume" (both `panel/actions/fill.js`, both behind a click) and
 * `preparePage` (`panel/panel.js`), which spends one injection per page AFTER
 * a silent posting read rather than before an ask. The last is the one to know
 * about — it is not user-initiated in the same sense, and it exists because an
 * extension reload orphans the scripts in every open tab, which is a state a
 * user lands in routinely and cannot diagnose.
 *
 * `allFrames`, because the engine runs in every frame and the fill fan-out
 * addresses them individually — injecting only the top frame would leave the
 * panel unable to reach a Greenhouse form in its iframe. Re-injecting a frame
 * that already has the scripts is harmless: every module is an IIFE that
 * re-publishes onto the same namespace.
 */
async function injectContentScripts(tabId) {
  await chrome.scripting.executeScript({
    target: { tabId, allFrames: true },
    files: contentScriptFiles(),
  });
}

// The hotkey OPENS the panel. It cannot close it: `chrome.sidePanel` has an
// `open` and no counterpart, so a "toggle" is not a thing this API can express
// — the panel's own close affordance is the browser's, and that is the whole
// of the story now. No injection rides this route: opening an extension page
// needs nothing in the tab, which is why the summon ladder that used to live
// here (message frame 0, inject on no-ack, retry once) went with the card.
//
// A COMMAND IS A USER GESTURE, which is the one precondition `sidePanel.open`
// has; a call from anywhere else rejects. Awaiting it is pointless and the
// `.catch` is not: this is a promise nobody holds, so an unhandled rejection
// would be the only trace of a failure the user experiences as "my shortcut
// does nothing" — already reported once, against a different route, with an
// empty log.
//
// GATED ON THE METHOD EXISTING, honestly rather than hopefully. `sidePanel`
// arrived in Chrome 114 (this extension's `minimum_chrome_version`) but
// `sidePanel.open()` did not land until 116, so on 114-115 the API object is
// there and this method is not. The minimum stays at 114 because everything
// else — including the toolbar click, which opens the panel through
// `setPanelBehavior` — works there; raising it would lock out a browser whose
// only missing piece is this shortcut. The `typeof` check is what keeps the
// gap from failing as a bare TypeError with no explanation.
chrome.commands.onCommand.addListener((command, tab) => {
  if (command !== TOGGLE_COMMAND) return;
  if (!Number.isInteger(tab?.id) || tab.id < 0) return;
  if (typeof chrome.sidePanel?.open !== "function") {
    console.warn(
      "[maestro-cs] this Chrome cannot open the side panel from a shortcut "
      + "(sidePanel.open needs Chrome 116+); use the toolbar icon.");
    return;
  }
  chrome.sidePanel.open({ tabId: tab.id })
    .catch((err) => console.warn("[maestro-cs] sidePanel.open failed:", err));
});

// The action click belongs to the side panel too. This is exactly the pairing
// Task 19 deleted — `openPanelOnActionClick` swallows the click before
// `onClicked` — so the onClicked listener is GONE rather than left as dead
// code someone debugs.
//
// Registered at the top level rather than inside `onInstalled`, which is the
// documented idiom and needs no browser to justify: the setter is idempotent,
// so running it on every service-worker wake is correct whether or not the
// setting survives a teardown — while `onInstalled` is only correct under the
// stronger of those two readings. The `.catch` is because this is a promise
// nobody awaits — an unhandled rejection here would be the only trace, and
// "the icon does nothing" was already reported once with an empty log.
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true })
  .catch((err) => console.warn("[maestro-cs] setPanelBehavior failed:", err));

// ---------- message router ----------

/** Keeps a proxied call on the configured backend HOST.
 *
 * The leading slash is the whole guard, and it is not cosmetic. `api()` builds
 * its URL by concatenation, and a URL's authority ends at the first `/` — so
 * `"@evil.test/steal"` concatenates to `http://localhost:8001@evil.test/steal`,
 * which parses with host `evil.test` and `localhost:8001` demoted to userinfo.
 * Checked in node: that string and `".@evil.test/x"` both re-host, while
 * `"/x@y"` stays on localhost. Two slashes are NOT an escape (`//evil.test/x`
 * resolves to a path on localhost), but no route here starts with two, and the
 * narrow rule is the one that stays obviously correct.
 *
 * WHAT IT DOES NOT DO, because the next author to add a handler will read this
 * comment and needs the honest version: it constrains WHERE ON THE HOST a call
 * lands, and nothing else. It does not limit which route, and `proxyInit`
 * below does not limit which method — a caller can still ask for any of the
 * backend's mutating routes, against a backend with no auth. What stands
 * between a hostile page and that is not this function: it is that a page
 * cannot reach `onMessage` at all (no `externally_connectable`, and the
 * listener drops anything not sent by this extension), so the only thing that
 * can call it is content-script code we wrote. Keep it that way. */
function assertBackendPath(path) {
  if (typeof path !== "string" || !path.startsWith("/") || path.startsWith("//")) {
    throw new Error(`not a backend path: ${JSON.stringify(path)}`);
  }
  return path;
}
// ---- end assertBackendPath ----

/** The only `fetch` init keys a message may set.
 *
 * An allowlist rather than a filter of known-bad keys, because `api()` spreads
 * `...opts` AFTER its own `headers`, so a caller-supplied `headers` REPLACES
 * the default rather than merging with it — checked in node: the built object
 * keeps `Authorization` and loses `Content-Type` entirely. That is how a
 * message would set arbitrary request headers, and it is why the headers are
 * built SW-side and cannot be named here. No `api()` caller in the extension
 * passes headers today, so nothing is given up.
 *
 * `signal`, `credentials`, `mode` and the rest are absent for the same reason:
 * they are not needed, and every key admitted is a key someone has to reason
 * about later. */
function proxyInit(init) {
  // Inline rather than a module const so the list travels with the function
  // the tests extract — a separate constant would let the test assert its own
  // copy of the allowlist while this one grew.
  const allowed = ["method", "body"];
  const out = {};
  for (const key of allowed) {
    if (init?.[key] !== undefined) out[key] = init[key];
  }
  return out;
}
// ---- end proxyInit ----

/** Handlers by message type. Each gets `(msg, frame, sender)` where `frame` is
 * the sender's frame key, and returns whatever the caller should receive.
 *
 * `sender` is the raw one Chrome supplied, and it is passed because `frame`
 * cannot answer the question the panel raises: an extension page has no tab, so
 * its frame key is null — the same null a malformed content-script sender
 * produces. Only the sender itself tells those two apart (`sender.tab ===
 * undefined`), which is what `fanoutTab` reads. Handlers that never fan out
 * ignore the third argument. */
const HANDLERS = {
  async api(msg) {
    return api(assertBackendPath(msg.path), proxyInit(msg.init));
  },

  /** The settings the panel renders and toggles.
   *
   * RENAMED FROM `widget_settings` AT R-C, and the rename was free where the
   * command key's was not: this is an internal message type between two
   * halves of one extension that ship together, so nothing outside the repo
   * knows the string and no user setting is keyed by it.
   *
   * Asked for rather than read from `chrome.storage.sync` by the caller so
   * that DEFAULTS above stays the one place a default lives — a second copy
   * would be the one most likely to drift out of sight. WRITES go the other
   * way: the panel sets the key directly, which needs no defaults and lands in
   * the same store this reads.
   *
   * EEO standing consent is backend-owned (`/api/settings/eeo-consent` /
   * `eeo_consent` on `/api/autofill/context`); `eeoAutofillEnabled` remains in
   * storage for migration only and is not authoritative for fill. */
  async read_settings() {
    const { backendUrl, appUrl, telemetryEnabled, eeoAutofillEnabled, fillMode } =
      await getSettings();
    return { backendUrl, appUrl, telemetryEnabled, eeoAutofillEnabled, fillMode };
  },

  /** Autofill telemetry, gated and scrubbed in one place.
   *
   * The opt-in check is HERE rather than at the caller for the same reason the
   * scrub is: this is the only context that can fetch, so a future caller that
   * forgets either cannot post anyway. Returns nothing the caller waits on —
   * telemetry may never surface an error or delay a fill.
   *
   * The batch itself only ever exists on a page the user pointed the panel at
   * (design §8.9): the fill engine is the only thing that constructs an
   * observation, and nothing runs it without a click. */
  async telemetry(msg) {
    const { telemetryEnabled } = await getSettings();
    if (telemetryEnabled === false) return { posted: 0 };
    const observations = (msg.observations ?? []).map(scrubObservation);
    if (!observations.length) return { posted: 0 };
    await api("/api/autofill/telemetry", {
      method: "POST",
      body: JSON.stringify({
        page_host: String(msg.page_host ?? "").slice(0, 255),
        action: msg.action,
        observations,
      }),
    });
    return { posted: observations.length };
  },

  /** Fetch a resume PDF and hand it to every frame of the sender's tab.
   *
   * The bytes never travel through the UI: a Blob does not survive a
   * message boundary in either direction — both ends serialize, and this one
   * is JSON — so base64 is the shape that is known to work. Doing the fetch
   * AND the fan-out here means the encoded PDF crosses one boundary instead of
   * two.
   *
   * 0x8000 bytes at a time because spreading a whole PDF into
   * `String.fromCharCode` is an argument list long enough to blow the call
   * stack. Checked in node: `String.fromCharCode(...new Uint8Array(200000))`
   * throws RangeError, and the chunked loop returns 200000. */
  async attach_pdf(msg, frame, sender) {
    const tabId = fanoutTab(msg, frame, sender);
    const { backendUrl } = await getSettings();
    const res = await fetch(`${backendUrl}${assertBackendPath(msg.path)}`);
    if (!res.ok) throw new Error(`PDF fetch failed (${res.status})`);
    const bytes = new Uint8Array(await res.arrayBuffer());
    let binary = "";
    for (let i = 0; i < bytes.length; i += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    }
    return broadcastToFrames(tabId, {
      type: "attach_resume_pdf",
      b64: btoa(binary),
      filename: String(msg.filename ?? "resume.pdf"),
      // The caller's refusal, carried through unread — see `attachResumePdf`
      // (content/agent.js), which is the only place it can be checked: a count
      // is a fact about a FRAME at the moment of the write, and this worker
      // runs in no page. Forwarded only when it is an integer, and the panel
      // ALWAYS sends one (`actions/fill.js` passes `facts.fileInputs`, the
      // count its own offer was made from). The conditional is therefore about
      // a MALFORMED value rather than an absent one: `expect: null` or
      // `expect: "1"` must not quietly become "no check", which is the shape
      // that turns a refusal into an unguarded write.
      expect: Number.isInteger(msg.expect) ? msg.expect : undefined,
    });
  },

  /** The UI's fan-out to the engine. Greenhouse and Lever put the whole
   * application form in a subframe while the top frame is marketing, so a fill
   * that only reached the sender would miss the form it exists for.
   *
   * WHICH TAB is `fanoutTab`'s question and this handler goes through it —
   * the panel has no tab of its own, so it names the one it is bound to. The
   * rule that used to be written out here is written out there instead — one
   * copy, because `attach_pdf` asks the same question.
   *
   * The type is allow-listed, not merely checked for existence in
   * PAGE_HANDLERS. `extract_job_posting` is deliberately absent: a posting's
   * JSON-LD is in the top document, so broadcasting it would read every
   * subframe on the page for nothing. The panel, which runs in no page,
   * reaches that one through `panel_frame0` rather than by widening this list.
   *
   * `scroll_to_field` is the fifth and it is the cheapest thing on the list:
   * the panel's residue rows are jumps to controls the fill could not answer,
   * and the control can be in any frame — on Greenhouse it is in the one the
   * form lives in — so frame 0 is the wrong door and a fan-out is the right
   * one. It carries a QID and nothing else, which is the property that makes it
   * safe to broadcast: a qid is OUR token, stamped by our own collector on a
   * frame that already passed `frameMayReceiveUserData`, so a frame that never
   * answered a collect holds none and scrolls nothing. Keep it that way — a
   * label, a value or an answer added to this message would be user data
   * travelling to every frame of the tab, which is what the fan-out gate on
   * the receiving side exists to prevent. */
  async page_broadcast(msg, frame, sender) {
    const BROADCASTABLE = ["profile_fill", "collect_open_questions", "fill_answers",
      "guided_write", "scroll_to_field"];
    const tabId = fanoutTab(msg, frame, sender);
    if (!BROADCASTABLE.includes(msg.message?.type)) {
      throw new Error(`not broadcastable: ${JSON.stringify(msg.message?.type)}`);
    }
    return broadcastToFrames(tabId, msg.message);
  },

  /** Make sure the content scripts exist in the panel's tab before a fill or
   * extract. A tab open since before the extension was installed or reloaded
   * has none, and every route into it simply fails there — this is the only
   * thing that closes that gap now. Idempotent, because every content module
   * is an IIFE that re-publishes onto the same namespace.
   *
   * Panel-only, and the guard comes FIRST — before any field of `msg` is read
   * — because the whole of the panel's extra reach is "it may name a tab". A
   * content script that reached this would be a page's frame injecting scripts
   * into a tab of its choosing, which is strictly more than `page_broadcast`
   * would ever let it do. It has no reason to call this: its own presence in
   * the tab is the proof the scripts are already there. */
  async panel_prepare(msg, _frame, sender) {
    if (sender?.tab !== undefined) throw new Error("not a panel sender");
    await injectContentScripts(fanoutTab(msg, null, sender));
    return { injected: true };
  },

  /** Frame 0 only, for reads that live in the top document (a posting's
   * JSON-LD). The panel runs in no page at all, so this is its door to
   * handlers that a content script would simply call.
   *
   * Allow-listed for the same reason `page_broadcast`'s types are, and the two
   * lists are deliberately not one: this one may name a frame, so a type added
   * here is a type that can be aimed at the top document of any tab. Panel-only
   * guard first, as in `panel_prepare`.
   *
   * TWO types, and both answer the same question — "what does the top document
   * say about itself?". `extract_job_posting` reads the posting's JSON-LD;
   * `detect_page` returns `detectPage()`'s verdict, which is how the panel
   * learns whether the tab holds a form at all (it runs in no page, so it
   * cannot detect for itself). Neither returns anything derived from the user,
   * which is the property that makes a type safe to aim at any tab's top
   * document.
   *
   * `collect_open_questions` was here and is deliberately gone: open questions
   * live in the frame that holds the FORM, which on Greenhouse and Lever is a
   * subframe, so asking frame 0 for them returns an empty list that reads as
   * "no questions on this page". Every questions path goes through
   * `page_broadcast`, which asks every frame.
   *
   * `unwrapPageReply` throws here rather than being caught, and that is the
   * point of a single-frame call: a fan-out tolerates a silent frame because an
   * ad iframe must not cost the user the form beside it, while a read aimed at
   * frame 0 has no sibling to spare — silence means the panel never read the
   * page, and it must not render that as a fact about the page. */
  async panel_frame0(msg, _frame, sender) {
    if (sender?.tab !== undefined) throw new Error("not a panel sender");
    const ALLOWED = ["extract_job_posting", "detect_page"];
    if (!ALLOWED.includes(msg.message?.type)) {
      throw new Error(`not allowed at frame 0: ${JSON.stringify(msg.message?.type)}`);
    }
    const tabId = fanoutTab(msg, null, sender);
    return unwrapPageReply(
      await chrome.tabs.sendMessage(tabId, msg.message, { frameId: 0 }));
  },
};

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  // Only our own content scripts and pages. No `externally_connectable` is
  // declared, so today nothing else can reach this listener anyway; the check
  // is here so that adding one later is a decision rather than an accident.
  //
  // BEFORE WEAKENING THIS, read `fanoutTab`'s WHERE THIS STOPS. It trusts a
  // sender with no `tab` as the side panel and lets it name any tab in the
  // browser — so for a tab-less sender this line is not a second opinion
  // behind the frame rules, it is the whole of provenance. It used to be
  // belt-and-braces; the panel made it structural.
  if (sender?.id !== chrome.runtime.id) return false;
  // hasOwn, not a bare lookup: `HANDLERS["toString"]` finds a function on
  // Object.prototype, and the type comes from the message.
  if (!Object.hasOwn(HANDLERS, msg?.type ?? "")) return false;
  const handler = HANDLERS[msg.type];

  (async () => {
    try {
      sendResponse({ ok: true, data: await handler(msg, frameKey(sender), sender) });
    } catch (err) {
      // Errors travel as data: sendResponse has no reject channel, and what an
      // Error object looks like on the far side of the message boundary is not
      // worth depending on. Callers branch on `ok`.
      //
      // AND THE HTTP STATUS TRAVELS WITH THEM, on the same envelope rather than
      // on a message type of its own. `api()` above hangs it on the Error it
      // throws; an Error does not survive this boundary, so without this line
      // every failure reaches the panel as one indistinguishable sentence and
      // "the draft was deleted" reads exactly like "the backend is not
      // running". CONDITIONAL, because the absence is a fact too: a rejected
      // `fetch` and a handler that threw for its own reasons carry no status,
      // and a `status: undefined` written here would be a field the far side
      // has to know is a lie. `ask` in panel.js is the only reader.
      sendResponse({
        ok: false,
        error: String(err?.message ?? err),
        ...(Number.isInteger(err?.status) ? { status: err.status } : {}),
      });
    }
  })();
  // Documented contract: `true` keeps the message channel open so the async
  // sendResponse above is still delivered. Returning false for an unhandled
  // type (above) matters for the same reason in reverse — it releases the
  // channel instead of leaving the sender waiting.
  return true;
});
