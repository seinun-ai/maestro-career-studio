/* Maestro CS Companion — service worker.
 *
 * Two jobs.
 *
 * 1. Reaching the widget: the toolbar icon and the keyboard shortcut both land
 *    here, because neither `chrome.action` nor `chrome.commands` is exposed to
 *    a content script. See "reaching the widget" below.
 *
 * 2. Every backend call the extension makes from a content script goes
 *    through here. That is not a convenience — see below.
 */

// ---------- settings ----------
//
// The one place a default lives. The side panel used to hold a second copy;
// both it and `setPanelBehavior` were deleted at Task 19.

const DEFAULTS = {
  backendUrl: "http://localhost:8001",
  appUrl: "http://localhost:3000",
  telemetryEnabled: true,
  // Legacy; fill decisions use backend eeo_consent.enabled instead.
  eeoAutofillEnabled: false,
};

async function getSettings() {
  const stored = await chrome.storage.sync.get(DEFAULTS);
  return { ...DEFAULTS, ...stored };
}

/* The only fetch site the extension has, and the only one a CONTENT SCRIPT
 * gets. Moved from the side panel's copy unchanged at Task 8; that copy is
 * gone.
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
    throw new Error(detail);
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
 * a sibling. The widget mounts only where `window.top === window.self`
 * (design §3.1), so a request to message another frame that comes FROM a
 * subframe is not the UI asking — on a Greenhouse posting it is an ad iframe.
 * The top frame may still address the application subframe, because that is
 * exactly what the widget is for. Fan-out ("fill every frame") is not this
 * function: the SW picks those targets itself, behind the explicit user click
 * design.md:125 requires, and never from a key a page's frame supplied.
 *
 * No caller until Task 9. */
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

/** Ask EVERY frame of one tab, and return `[{frameId, result, error?}]`.
 *
 * The array shape is the side panel's `callAllFrames`, deliberately: the
 * widget's aggregation — the flatMaps, the per-frame host map, the attach
 * reduce — is the same logic that was written against it, and a second shape
 * would mean a second set of reporting semantics to keep honest. The panel is
 * gone; this function inherited its contract and its tests.
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
      // `sendResponse` has no reject channel, so agent.js reports failure in
      // the payload. An absent reply means the listener returned without
      // answering — no content script in that frame.
      if (!reply) throw new Error("no reply from the page");
      if (!reply.ok) throw new Error(reply.error ?? "the page reported an error");
      return { frameId: frame.frameId, result: reply.data };
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

// ---------- reaching the widget (design §4.1 dismissal) ----------
//
// Both routes below exist so that dismissal is reversible. A tool that can be
// hidden and not brought back is worse than one that cannot be hidden: the
// research corpus's Jobscan failure is a message naming a control that does not
// exist, and this is the control.

const TOGGLE_COMMAND = "toggle-widget";

/** The content scripts, in the manifest's injection order.
 *
 * Read from the manifest rather than restated, because a list that has to be
 * kept in step with `content_scripts.js` by hand is a list that will not be:
 * the ordering is load-bearing (each file publishes onto the namespace the
 * next one reads) and a missing entry fails as "the widget cannot start".
 */
function contentScriptFiles() {
  const scripts = chrome.runtime.getManifest().content_scripts ?? [];
  return scripts.flatMap((entry) => entry.js ?? []);
}

/** Put the content scripts into a tab that does not have them.
 *
 * A content script enters a page when the PAGE loads, so a tab that was
 * already open when the extension was installed or reloaded has none — and
 * until now every route into the widget simply failed there. The user pressed
 * the toolbar button, nothing happened, and the only fix was to know that
 * reloading the tab was required.
 *
 * `chrome.scripting.executeScript` is the documented way to close that gap.
 * It is used ONLY on the explicit-request routes (the icon, the hotkey), never
 * on page load: injecting into a page nobody asked about is exactly the
 * always-on cost the detection gate exists to avoid.
 *
 * `allFrames`, because the engine runs in every frame and the fill fan-out
 * addresses them individually — injecting only the top frame would produce a
 * widget that mounts and then cannot reach a Greenhouse form in its iframe.
 * Re-injecting a frame that already has the scripts is harmless: every module
 * is an IIFE that re-publishes onto the same namespace.
 */
async function injectContentScripts(tabId) {
  await chrome.scripting.executeScript({
    target: { tabId, allFrames: true },
    files: contentScriptFiles(),
  });
}

/** Frame 0 of a tab, which is the only frame `content/widget.js` runs in.
 *
 * Retried ONCE behind an injection, because the common failure here is not
 * "this page has no widget" but "this page has no content script yet" — and
 * those are indistinguishable from the outside. A page the extension genuinely
 * cannot touch (chrome://, the Web Store, a PDF viewer) fails the injection
 * too, so it still ends in silence rather than in a false widget. */
function messageWidget(tabId, type) {
  if (!Number.isInteger(tabId) || tabId < 0) return;
  chrome.tabs.sendMessage(tabId, { type }, { frameId: 0 }).catch(async () => {
    try {
      await injectContentScripts(tabId);
      await chrome.tabs.sendMessage(tabId, { type }, { frameId: 0 });
    } catch (err) {
      // Now it really is a page this extension is not on: a chrome:// URL, the
      // Web Store, a PDF viewer, or a tab that has since navigated away. The
      // user pressed a key and nothing happened, which is the correct outcome
      // there — but the reason is kept, because "the icon does nothing" was
      // reported as a bug with nothing in the log to explain it.
      console.warn(`[maestro-cs] ${type} could not reach tab ${tabId}:`, err);
    }
  });
}

// Level 3: the global toggle. `content/widget.js` decides which direction —
// it is the side that knows whether a widget is currently on screen.
chrome.commands.onCommand.addListener((command, tab) => {
  if (command === TOGGLE_COMMAND) messageWidget(tab?.id, "widget_toggle");
});

// Un-dismissal by toolbar icon (design §4.1: "clicking the toolbar action
// re-mounts on the current page"). Task 19 made this the primary route.
//
// WHAT CHANGED, and it is only half of what was in doubt. Until Task 19 this
// listener sat beside `chrome.sidePanel.setPanelBehavior({
// openPanelOnActionClick: true })`, and whether `onClicked` fires at all while
// that is registered was never executed. That call and the `side_panel`
// manifest key are now deleted, so the one documented reason an action click
// does not reach `onClicked` — the action opening something itself — has no
// remaining source here: the manifest declares `action` with a title and
// nothing else, no `default_popup`.
//
// STILL UNVERIFIED, because it is the same environment: no extension has been
// loaded. Branded Chrome refuses `--load-extension` ("not allowed in Google
// Chrome, ignoring") and no flag overrides it, so removing the call is an
// argument, not an observation. Settle it in one minute by loading unpacked,
// hiding the widget on a job page ("Hide the widget on this site"), and
// clicking the icon: the widget should come back expanded.
//
// Until someone does that, the hotkey above remains the route with the
// stronger claim — it is why the card's footer prints the shortcut. Note the
// gap that leaves: when no shortcut is bound, that footer sends the user to
// chrome://extensions/shortcuts and never mentions the icon.
chrome.action.onClicked.addListener((tab) => messageWidget(tab?.id, "widget_show"));

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

/** Handlers by message type. Each gets `(msg, frame)` where `frame` is the
 * sender's frame key, and returns whatever the caller should receive. */
const HANDLERS = {
  async api(msg) {
    return api(assertBackendPath(msg.path), proxyInit(msg.init));
  },

  /** The shortcut currently bound to the widget toggle, or "" if none is.
   *
   * `chrome.commands` is not exposed to content scripts, and the widget needs
   * this to tell the user how to bring it back after "Hide here" — the whole
   * point of design §4.1's un-dismissal rule. It is asked rather than hard-
   * coded because the manifest only SUGGESTS a key: the user can rebind it at
   * chrome://extensions/shortcuts, and Chrome silently drops a suggested key
   * another extension already claimed, which would leave us printing a shortcut
   * that does nothing. */
  async widget_hotkey() {
    const commands = await chrome.commands.getAll();
    return { shortcut: commands.find((c) => c.name === TOGGLE_COMMAND)?.shortcut ?? "" };
  },

  /** The settings the widget renders and toggles.
   *
   * Asked for rather than read from `chrome.storage.sync` in the content
   * script so that DEFAULTS above stays the one place a default lives — a
   * content-script copy would be a third, and the one most likely to drift out
   * of sight. WRITES go the other way: the widget sets the key directly, which
   * needs no defaults and lands in the same store this reads.
   *
   * EEO standing consent is backend-owned (`/api/settings/eeo-consent` /
   * `eeo_consent` on `/api/autofill/context`); `eeoAutofillEnabled` remains in
   * storage for migration only and is not authoritative for fill. */
  async widget_settings() {
    const { backendUrl, appUrl, telemetryEnabled, eeoAutofillEnabled } = await getSettings();
    return { backendUrl, appUrl, telemetryEnabled, eeoAutofillEnabled };
  },

  /** Autofill telemetry, gated and scrubbed in one place.
   *
   * The opt-in check is HERE rather than at the caller for the same reason the
   * scrub is: this is the only context that can fetch, so a future caller that
   * forgets either cannot post anyway. Returns nothing the caller waits on —
   * telemetry may never surface an error or delay a fill.
   *
   * The batch itself only ever exists on a page that passed detection (design
   * §8.9): the widget mounts on nothing else, and the fill engine is the only
   * thing that constructs an observation. */
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
   * The bytes never travel through the widget: a Blob does not survive a
   * message boundary in either direction — both ends serialize, and this one
   * is JSON — so base64 is the shape that is known to work. Doing the fetch
   * AND the fan-out here means the encoded PDF crosses one boundary instead of
   * two.
   *
   * 0x8000 bytes at a time because spreading a whole PDF into
   * `String.fromCharCode` is an argument list long enough to blow the call
   * stack. Checked in node: `String.fromCharCode(...new Uint8Array(200000))`
   * throws RangeError, and the chunked loop returns 200000. */
  async attach_pdf(msg, frame) {
    const from = parseFrameKey(frame);
    if (!from) throw new Error("sender is not an addressable frame");
    if (from.frameId !== 0) throw new Error(`only the top frame may attach (from ${frame})`);
    const { backendUrl } = await getSettings();
    const res = await fetch(`${backendUrl}${assertBackendPath(msg.path)}`);
    if (!res.ok) throw new Error(`PDF fetch failed (${res.status})`);
    const bytes = new Uint8Array(await res.arrayBuffer());
    let binary = "";
    for (let i = 0; i < bytes.length; i += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    }
    return broadcastToFrames(from.tabId, {
      type: "attach_resume_pdf",
      b64: btoa(binary),
      filename: String(msg.filename ?? "resume.pdf"),
    });
  },

  /** The widget's fan-out to the engine. Greenhouse and Lever put the whole
   * application form in a subframe while the top frame is marketing, so a fill
   * that only reached the sender would miss the form it exists for.
   *
   * TOP FRAME ONLY, the same rule `sendToFrame` enforces and for the same
   * reason: the widget mounts only where `window.top === window.self`, so a
   * broadcast request arriving FROM a subframe is not the UI asking — on a
   * Greenhouse posting it is an ad iframe. Same tab comes free, because the
   * tab id is taken from the SENDER and never from the message.
   *
   * The type is allow-listed, not merely checked for existence in
   * PAGE_HANDLERS. `extract_job_posting` is deliberately absent: a posting's
   * JSON-LD is in the top document, the widget runs there and calls it
   * directly, and broadcasting it would read every subframe on the page for
   * nothing. */
  async page_broadcast(msg, frame) {
    const BROADCASTABLE = ["profile_fill", "collect_open_questions", "fill_answers"];
    const from = parseFrameKey(frame);
    if (!from) throw new Error("sender is not an addressable frame");
    if (from.frameId !== 0) throw new Error(`only the top frame may broadcast (from ${frame})`);
    if (!BROADCASTABLE.includes(msg.message?.type)) {
      throw new Error(`not broadcastable: ${JSON.stringify(msg.message?.type)}`);
    }
    return broadcastToFrames(from.tabId, msg.message);
  },
};

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  // Only our own content scripts and pages. No `externally_connectable` is
  // declared, so today nothing else can reach this listener anyway; the check
  // is here so that adding one later is a decision rather than an accident.
  if (sender?.id !== chrome.runtime.id) return false;
  // hasOwn, not a bare lookup: `HANDLERS["toString"]` finds a function on
  // Object.prototype, and the type comes from the message.
  if (!Object.hasOwn(HANDLERS, msg?.type ?? "")) return false;
  const handler = HANDLERS[msg.type];

  (async () => {
    try {
      sendResponse({ ok: true, data: await handler(msg, frameKey(sender)) });
    } catch (err) {
      // Errors travel as data: sendResponse has no reject channel, and what an
      // Error object looks like on the far side of the message boundary is not
      // worth depending on. Callers branch on `ok`.
      sendResponse({ ok: false, error: String(err?.message ?? err) });
    }
  })();
  // Documented contract: `true` keeps the message channel open so the async
  // sendResponse above is still delivered. Returning false for an unhandled
  // type (above) matters for the same reason in reverse — it releases the
  // channel instead of leaving the sender waiting.
  return true;
});
