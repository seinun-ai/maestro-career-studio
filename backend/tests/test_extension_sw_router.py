"""The service worker's half of the side panel: who may aim what at which tab.

`extension/sw.js` is not a panel file and never joins the page namespace — it
has no IIFE and publishes nothing — so nothing here uses `loadModules()`. What
lives in this file is everything the panel's ARRIVAL changed about the service
worker, which is one subject with three parts:

1. the registration — who owns the toolbar click (the panel, via
   `openPanelOnActionClick`) and where the hotkey goes (the panel too, since
   R-C). Task 19 deleted the first side panel because those two fought over the
   same click;
2. `fanoutTab` — which tab a fan-out lands on, and the rule that a content
   script's named `msg.tabId` is IGNORED while the panel's is honoured;
3. the panel's two doors (`panel_prepare`, `panel_frame0`) driven through the
   REAL router, plus the `sender.id` check that this design promoted from
   redundant to sole defense;
4. the two rules that have no other home since R-C deleted
   `test_extension_widget.py` — the telemetry gate/scrub, and the
   `page_broadcast` allow-list beside its `panel_frame0` sibling. Both were
   pinned only in that file, and both were verified exploitable at a green
   suite before these tests existed.

The through-line, and the reason these belong together rather than beside the
panel's own tests: the panel is trusted BECAUSE it has no `sender.tab`. Every
test that separates a panel from a page is a test of that one discriminator.

The panel itself — its stages, its loads, its render loop and the Job stage's
action — is in `test_extension_panel.py`.
"""
import json
import re

import pytest

from tests.extension_harness import ROOT, js_code, run_node

EXTENSION = ROOT / "extension"
MANIFEST = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
SW_JS = (EXTENSION / "sw.js").read_text(encoding="utf-8")
# Comment lines dropped: sw.js narrates the deleted onClicked listener on
# purpose, so a raw-source pin here would assert the prose. See `js_code`.
SW_CODE = js_code(SW_JS)


# ---------- the registration: who owns the toolbar click ----------


def test_both_ways_in_open_the_one_panel():
    """Task 19 deleted the first side panel because `openPanelOnActionClick`
    and `action.onClicked` fight over the same click. The panel is back and the
    click goes to ONE owner. R-C pointed the SECOND way in — the keyboard
    shortcut, which used to summon the floating card — at the same place, so
    there is one surface and two doors to it rather than two surfaces.

    THE GATE IS ASSERTED, not just the call. `sidePanel.open()` needs Chrome
    116 while this extension's minimum is 114, so on two versions the method is
    simply absent; without the guard the shortcut throws a bare TypeError into
    a service worker nobody is watching. The command key keeps its old name on
    purpose — see `TOGGLE_COMMAND`'s note — so a name assertion here would pin
    the wrong thing, and the manifest DESCRIPTION is what a user reads.
    """
    assert MANIFEST["side_panel"] == {"default_path": "panel/panel.html"}
    assert "sidePanel" in MANIFEST["permissions"]
    assert "openPanelOnActionClick: true" in SW_CODE
    assert "chrome.action.onClicked.addListener" not in SW_CODE
    assert "chrome.sidePanel.open({ tabId: tab.id })" in SW_CODE
    assert 'typeof chrome.sidePanel?.open !== "function"' in SW_CODE
    assert "panel" in MANIFEST["commands"]["toggle-widget"]["description"].lower()
    # Nothing messages a card any more, on any route.
    assert "messageWidget" not in SW_CODE
    assert "widget_toggle" not in SW_CODE


# ---------- the service worker's half: who may aim the fan-out ----------
#
# `extract` rather than `loadModules` here, and that is the one place the
# plan's module-loader rule does not apply: `sw.js` never joins the page
# namespace — it has no IIFE and publishes nothing — so there is no module to
# load. Its slices are the reason `extract` still exists.

_FANOUT_DRIVER_JS = r"""
const frameKey = extract("frameKey", "\n// ---- end frameKey ----");
const fanoutTab = extract("fanoutTab", "\n// ---- end fanoutTab ----");
// `fanoutTab` reaches `parseFrameKey` as a FREE variable, and `extract`
// materializes its slice through `vm.runInThisContext` — which resolves free
// identifiers globally, never against this module's `const`s. A module-scoped
// binding therefore leaves every content-sender row failing with
// "parseFrameKey is not defined", which the two rows that expect a throw would
// have swallowed as a pass. Observed, then fixed the way
// test_extension_manifest.py's SW driver already does.
global.parseFrameKey = extract("parseFrameKey", "\n// ---- end parseFrameKey ----");
main(async () => {
  const out = {};
  for (const [name, c] of Object.entries(spec.cases)) {
    try { out[name] = { tab: fanoutTab(c.msg, frameKey(c.sender), c.sender) }; }
    catch (err) { out[name] = { error: String(err.message) }; }
  }
  emit(out);
});
"""


def test_fanout_tab_trusts_the_panel_and_never_a_named_tab_from_a_page(tmp_path):
    out = run_node(_FANOUT_DRIVER_JS, {"cases": {
        # Panel: no sender.tab; the tab it names is used.
        "panel": {"sender": {"id": "ext"}, "msg": {"tabId": 7}},
        "panel_no_tab": {"sender": {"id": "ext"}, "msg": {}},
        # Top-frame content script: its OWN tab, and a named tabId is IGNORED —
        # a page's frame must never aim the engine at another tab.
        "top_frame": {"sender": {"id": "ext", "tab": {"id": 3}, "frameId": 0},
                      "msg": {"tabId": 999}},
        "subframe": {"sender": {"id": "ext", "tab": {"id": 3}, "frameId": 4},
                     "msg": {"tabId": 3}},
    }}, tmp_path, source=SW_JS)
    assert out["panel"] == {"tab": 7}
    assert "error" in out["panel_no_tab"]
    assert out["top_frame"] == {"tab": 3}          # 999 ignored
    assert "error" in out["subframe"]


# ---------- the panel's two doors, driven through the real router ----------
#
# The WHOLE service worker runs here, not a slice, and it is the only driver in
# the repo that does. Two reasons, both about what a slice cannot see:
#
# * `panel_prepare`/`panel_frame0` are object methods, not `function`
#   declarations, so `extract` cannot reach them at all; and
# * what is actually under test is the ROUTER — `Object.hasOwn` on HANDLERS,
#   the sender check, and the one line that hands a handler `(msg,
#   frameKey(sender), sender)`. A driver that called the handler directly would
#   supply that third argument itself and prove nothing about whether the
#   router ever does. Drop `sender` from the invocation and every sender in the
#   browser reads as a panel; the `refuses_a_content_sender` rows below are
#   what fail when it happens.
#
# Only the recorders are fake. Nothing here decides anything the SW should.

_PANEL_HANDLER_DRIVER_JS = r"""
let listener = null;
let injected = [];
let addressed = [];
let reply = null;

global.chrome = {
  runtime: {
    id: "maestro-cs-test",
    onMessage: { addListener: (callback) => { listener = callback; } },
    getManifest: () => ({ content_scripts: [{ js: ["content/agent.js"] }] }),
  },
  // Reached while sw.js evaluates, before any message: the hotkey route and
  // the panel-owns-the-click registration.
  commands: { onCommand: { addListener: () => {} } },
  sidePanel: { setPanelBehavior: async () => {} },
  scripting: {
    executeScript: async (options) => { injected.push(options); },
  },
  tabs: {
    sendMessage: async (tabId, message, options) => {
      addressed.push({ tabId, message, options });
      return reply;
    },
  },
};

// The real file, IIFE-less and namespace-less — sw.js publishes nothing, so
// `loadModules` has nothing to return and this runs it for its side effect:
// registering the listener above.
vm.runInThisContext(source);

const send = (msg, sender) => new Promise((resolve, rejectSend) => {
  const keptOpen = listener(msg, sender, resolve);
  if (!keptOpen) rejectSend(new Error(`the router declined ${msg.type}`));
});

main(async () => {
  const out = {};
  for (const [name, c] of Object.entries(spec.cases)) {
    injected = [];
    addressed = [];
    reply = c.reply ?? null;
    // `id` first so a case may override it: a sender that is not this
    // extension is refused by the router before any handler exists.
    const sender = { id: chrome.runtime.id, ...c.sender };
    try {
      out[name] = { reply: await send(c.msg, sender), injected, addressed };
    } catch (err) {
      // The listener returned false: no handler ran and the channel was
      // RELEASED, so the sender is not merely refused — it is never answered.
      out[name] = { declined: String(err.message), injected, addressed };
    }
  }
  emit(out);
});
"""

PANEL = {}                       # an extension page: no `tab` at all
TOP_FRAME = {"tab": {"id": 3}, "frameId": 0}
POSTING = {"type": "extract_job_posting"}
DETECT = {"type": "detect_page"}


@pytest.fixture(scope="module")
def panel_handlers(tmp_path_factory):
    cases = {
        # The tab a panel names is the tab it is bound to, and preparing it
        # is what closes the no-content-scripts gap on that tab.
        "prepare": {"sender": PANEL, "msg": {"type": "panel_prepare", "tabId": 7}},
        # No tab named: fanoutTab refuses rather than injecting into undefined.
        "prepare_no_tab": {"sender": PANEL, "msg": {"type": "panel_prepare"}},
        # A page's frame asking to inject scripts into a tab of its choosing —
        # strictly more than page_broadcast would ever let it do.
        "prepare_from_a_page": {"sender": TOP_FRAME,
                                "msg": {"type": "panel_prepare", "tabId": 9}},
        "frame0": {"sender": PANEL, "reply": {"ok": True, "data": {"title": "Data Scientist"}},
                   "msg": {"type": "panel_frame0", "tabId": 7, "message": POSTING}},
        # The second allowed type: the panel is in no page, so "does this tab
        # hold a form?" is a question only the page can answer.
        "frame0_detect": {"sender": PANEL,
                          "reply": {"ok": True, "data": {"tier": "B", "form": True,
                                                         "score": 2}},
                          "msg": {"type": "panel_frame0", "tabId": 7,
                                  "message": DETECT}},
        # Outside the allow-list: a fill aimed at the top document of any tab.
        "frame0_not_allowed": {"sender": PANEL, "reply": {"ok": True, "data": "filled"},
                               "msg": {"type": "panel_frame0", "tabId": 7,
                                       "message": {"type": "profile_fill"}}},
        # A page handler that is real, and reachable through page_broadcast, and
        # still refused HERE — the list is one type, not "the harmless ones".
        "frame0_questions": {"sender": PANEL, "reply": {"ok": True, "data": {"questions": []}},
                             "msg": {"type": "panel_frame0", "tabId": 7,
                                     "message": {"type": "collect_open_questions"}}},
        "frame0_from_a_page": {"sender": TOP_FRAME, "reply": {"ok": True, "data": {}},
                               "msg": {"type": "panel_frame0", "tabId": 9,
                                       "message": POSTING}},
        # agent.js's two failure shapes, which this must read the way
        # broadcastToFrames does.
        "frame0_silent": {"sender": PANEL, "reply": None,
                          "msg": {"type": "panel_frame0", "tabId": 7, "message": POSTING}},
        "frame0_page_failed": {"sender": PANEL,
                               "reply": {"ok": False, "error": "no JSON-LD here"},
                               "msg": {"type": "panel_frame0", "tabId": 7,
                                       "message": POSTING}},
        # Tab-less, like the panel, and asking for the panel's privilege — but
        # not us. See the test below for why this shape matters now.
        "foreign_extension": {"sender": {"id": "someone-else"},
                              "msg": {"type": "panel_prepare", "tabId": 7}},
    }
    return run_node(_PANEL_HANDLER_DRIVER_JS, {"cases": cases},
                    tmp_path_factory.mktemp("panel_handlers"), source=SW_JS)


def test_the_panel_can_put_the_content_scripts_into_the_tab_it_names(panel_handlers):
    """A tab open since before the extension was installed or reloaded has no
    content scripts, so every fill and every read fails there until something
    injects them, and since R-C this handler is the only thing that does —
    the summon ladder that used to inject on the card's behalf went with the
    card."""
    prepared = panel_handlers["prepare"]
    assert prepared["reply"] == {"ok": True, "data": {"injected": True}}
    # Every frame, not just the top one: the engine runs in whichever frame
    # holds the form, and on Greenhouse that is a subframe.
    assert prepared["injected"] == [{
        "target": {"tabId": 7, "allFrames": True},
        "files": ["content/agent.js"],
    }]
    # A panel that named no tab injects into nothing rather than into undefined.
    assert panel_handlers["prepare_no_tab"]["injected"] == []
    assert "panel named no tab" in panel_handlers["prepare_no_tab"]["reply"]["error"]


def test_the_panel_only_handlers_refuse_a_sender_that_carries_a_tab(panel_handlers):
    """The discriminator, asserted from the side that matters.

    Naming a tab is the panel's whole extra privilege, and these two handlers
    grant it — so a content script reaching either one would be a page's frame
    injecting scripts into, or reading the top document of, any tab it liked.
    `sender.tab === undefined` is what separates them, and it cannot be forged:
    a page cannot reach onMessage, and a content script cannot shed its tab.

    The REASON is asserted, not merely that it failed. Delete the guard and
    `panel_prepare` still refuses this sender — but only by accident, because
    it passes `null` for the frame key and `fanoutTab` then finds no addressable
    frame. That accident evaporates the day someone passes the real frame key,
    and a bare "it errored" assertion would have called that day green.
    """
    for name in ("prepare_from_a_page", "frame0_from_a_page"):
        refused = panel_handlers[name]
        assert refused["reply"] == {"ok": False, "error": "not a panel sender"}, name
        assert refused["injected"] == [], name
        assert refused["addressed"] == [], name


def test_frame_zero_reads_are_allow_listed_and_addressed_to_the_top_document(panel_handlers):
    """`extract_job_posting` is asked of the top document first, so the panel
    needs a door that names frame 0 (every frame is asked through
    page_broadcast only when frame 0 has no job description). That door names a frame,
    which is why its list is its own: a type added here can be aimed at the top
    document of any tab, and `profile_fill` is exactly the type that must not
    be.

    TWO types, and the list is exactly two — which is why
    `collect_open_questions` is tested as a refusal rather than left
    unmentioned. It is a real page handler and a perfectly good one to
    broadcast — so nothing but this test stops it drifting back into the list,
    where it would also be WRONG: open questions live in the frame holding the
    form, a subframe on Greenhouse and Lever, so a frame-0 collect answers "no
    questions" about a page full of them.

    `detect_page` earns its place for `extract_job_posting`'s reason: it reads
    the top document and returns nothing derived from the user. The panel needs
    it because detection is a page function and the panel is in no page.
    """
    read = panel_handlers["frame0"]
    assert read["reply"] == {"ok": True, "data": {"title": "Data Scientist"}}
    assert read["addressed"] == [{
        "tabId": 7, "message": POSTING, "options": {"frameId": 0},
    }]
    detected = panel_handlers["frame0_detect"]
    assert detected["reply"] == {"ok": True, "data": {"tier": "B", "form": True, "score": 2}}
    assert detected["addressed"] == [{
        "tabId": 7, "message": DETECT, "options": {"frameId": 0},
    }]

    for name, refused_type in (("frame0_not_allowed", "profile_fill"),
                               ("frame0_questions", "collect_open_questions")):
        refused = panel_handlers[name]
        assert refused["reply"] == {
            "ok": False, "error": f'not allowed at frame 0: "{refused_type}"'}, name
        # Refused BEFORE the page was touched, rather than after.
        assert refused["addressed"] == [], name


def test_a_sender_that_is_not_this_extension_never_reaches_a_handler(panel_handlers):
    """The router's `sender?.id !== chrome.runtime.id` check, which this change
    promoted from redundant to load-bearing — which is why it gets a test NOW,
    having gone untested since it was written.

    It used to be belt to `frameKey`'s braces. A tab-less sender that somehow
    reached the listener produced a null frame key, and every fan-out handler
    refused it on that basis: no tab, no frame, no fan-out. The id check was
    the second of two answers to the same question.

    Making the panel work inverted exactly that. Tab-less is now the shape that
    is TRUSTED — it is the discriminator, and it carries the privilege of
    naming any tab in the browser. So the id check is no longer a second
    answer; for a tab-less sender it is the only one. Nothing else in the SW
    would stop another extension's message (were `externally_connectable` ever
    declared) or any future tab-less surface from prepping and reading a tab it
    chose. `sw.js`'s own comment says the check exists so that adding such a
    thing is "a decision rather than an accident"; this is what makes that true.

    Refused BEFORE dispatch, so the recorders stay empty rather than catching
    it at the handler — and the channel is released rather than left open.
    """
    foreign = panel_handlers["foreign_extension"]
    assert "reply" not in foreign, (
        "a sender that is not this extension got an answer from a handler")
    assert foreign["declined"] == "the router declined panel_prepare"
    assert foreign["injected"] == []
    assert foreign["addressed"] == []


def test_a_single_frame_read_reports_a_silent_page_instead_of_inventing_data(panel_handlers):
    """The one place this differs from `broadcastToFrames`, and deliberately.

    A fan-out tolerates a frame that never answers — an ad iframe must not cost
    the user the form beside it — so it turns silence into an absent result. A
    read aimed at frame 0 has no sibling to fall back on: silence there means
    the panel has no idea what is on the page, and returning `undefined` would
    render as "no posting found" on a posting it simply never read. Both of
    agent.js's failure shapes therefore travel back as errors.
    """
    assert panel_handlers["frame0_silent"]["reply"] == {
        "ok": False, "error": "no reply from the page"}
    assert panel_handlers["frame0_page_failed"]["reply"] == {
        "ok": False, "error": "no JSON-LD here"}


# ---------- what a failure is ALLOWED to tell the panel ----------
#
# The backend's `api` handler, driven through the same real router, for the one
# question the panel cannot answer any other way: is this failure an ANSWER or a
# SILENCE? A deleted application and an unreachable backend arrive at the panel
# through the identical `{ok: false}` envelope, and until the ghost-binding
# round the only thing separating them was the `error` STRING — which is the
# backend's prose, free to be reworded, and absent entirely when a `fetch`
# rejects. The status is the structural half, and it is a field rather than a
# message type on purpose: `api()` hangs it on its Error and the router's catch
# copies it across the boundary an Error cannot cross.

_API_FAILURE_DRIVER_JS = r"""
let listener = null;

// The two failures the panel has to tell apart, modelled at the only place
// they differ: an HTTP answer that is not ok, and a fetch that never answered.
global.fetch = async () => {
  if (spec.reject) throw new TypeError("Failed to fetch");
  return {
    ok: false,
    status: spec.status,
    json: async () => ({ detail: spec.detail }),
  };
};

global.chrome = {
  runtime: {
    id: "maestro-cs-test",
    onMessage: { addListener: (callback) => { listener = callback; } },
    getManifest: () => ({ content_scripts: [{ js: ["content/agent.js"] }] }),
  },
  commands: { onCommand: { addListener: () => {} } },
  sidePanel: { setPanelBehavior: async () => {} },
  storage: { sync: { get: async (defaults) => ({ ...defaults }) } },
  tabs: { sendMessage: async () => null },
};

vm.runInThisContext(source);

main(async () => {
  const reply = await new Promise((resolve, rejectSend) => {
    const keptOpen = listener(
      spec.message ?? { type: "api", path: "/api/applications/app-1" },
      { id: chrome.runtime.id },
      resolve);
    if (!keptOpen) rejectSend(new Error("the router declined an api message"));
  });
  // ASKED OF THE OBJECT, not read off the emitted JSON: `JSON.stringify` drops
  // an `undefined` value, so a router that wrote `status: undefined` would
  // reach the Python side looking exactly like one that wrote nothing — and
  // the panel, which reads the live object, would see a field that is there.
  emit({ reply, carriedStatus: Object.hasOwn(reply, "status") });
});
"""


def _api_failure(tmp_path, **spec):
    spec.setdefault("detail", "Application not found")
    return run_node(_API_FAILURE_DRIVER_JS, spec, tmp_path, source=SW_JS)


def test_a_deleted_resource_and_an_unreachable_backend_are_different_failures(
        tmp_path):
    """THE DISCRIMINATION THE GHOST FIX RESTS ON, at the wire.

    404 travels as a NUMBER on the failure envelope beside the sentence. A
    `fetch` that rejected carries no status at all — and that absence is the
    load-bearing half: it is what tells the panel to keep a binding it cannot
    currently verify, which is the bridge's whole offline tolerance.

    THE MUTATION THIS DIES TO: dropping `err.status = res.status` in `api()`,
    or the conditional spread in the router's catch. Either one collapses the
    two rows below into the same shape, and the panel then either forgets a
    real application while offline or keeps a ghost forever — the same bug in
    both mirrors.
    """
    gone = _api_failure(tmp_path, status=404)
    assert gone["reply"]["ok"] is False
    assert gone["reply"]["status"] == 404
    # The sentence still travels; the status is beside it, not instead of it.
    assert gone["reply"]["error"] == "Application not found"

    offline = _api_failure(tmp_path, reject=True)
    assert offline["reply"]["ok"] is False
    assert offline["carriedStatus"] is False, (
        "a fetch that never answered claimed an HTTP status")


def test_a_server_error_is_not_a_missing_resource(tmp_path):
    """The other side of the same line, and the reason the panel tests for 404
    rather than for "not 2xx": a 500 is the backend failing to answer a
    question about an application that may be perfectly alive. It carries its
    status honestly — the field is not a 404 flag — and every reader that acts
    on absence has to check the number.
    """
    out = _api_failure(tmp_path, status=500, detail="Internal Server Error")
    assert out["reply"]["status"] == 500


def test_a_pdf_the_backend_would_not_send_carries_its_status(tmp_path):
    """The attach's PDF read is the SW's own fetch, not `api()`, so it has to
    hang the status on its error itself. Without it a 404 for a PDF that is gone
    reaches the panel with no status, and the panel's note then says "Check
    that Maestro CS is running" about a backend that just answered.

    THE MUTATION THIS DIES TO: throwing a bare Error in `attach_pdf`."""
    out = _api_failure(tmp_path, status=404, message={
        "type": "attach_pdf", "tabId": 7, "path": "/api/applications/app-1/pdf",
        "filename": "resume.pdf", "expect": 1})
    assert out["reply"]["ok"] is False
    assert out["reply"]["status"] == 404



_ATTACH_FORWARD_DRIVER_JS = r"""
let listener = null;
const delivered = [];
global.fetch = async () => ({ ok: true, status: 200,
                              arrayBuffer: async () => new Uint8Array([37, 80, 68, 70]).buffer });
global.chrome = {
  runtime: {
    id: "maestro-cs-test",
    onMessage: { addListener: (callback) => { listener = callback; } },
    getManifest: () => ({ content_scripts: [{ js: ["content/agent.js"] }] }),
  },
  commands: { onCommand: { addListener: () => {} } },
  sidePanel: { setPanelBehavior: async () => {} },
  storage: { sync: { get: async (defaults) => ({ ...defaults }) } },
  webNavigation: { getAllFrames: async () => [{ frameId: 0 }] },
  tabs: { sendMessage: async (tabId, message) => { delivered.push(message); return { ok: true, data: 1 }; } },
};
vm.runInThisContext(source);
main(async () => {
  const reply = await new Promise((resolve) => {
    listener({ type: "attach_pdf", tabId: 7, path: "/api/applications/app-1/pdf",
               filename: "resume.pdf", expect: 1, ...spec.extra },
             { id: chrome.runtime.id }, resolve);
  });
  emit({ reply, delivered });
});
"""


@pytest.mark.parametrize("extra, forwarded", [
    ({"resumeOnly": True}, True),
    ({}, False),
    # Only a literal true: a malformed value must not become a looser write,
    # and it must not become Autofill's stricter one by accident either.
    ({"resumeOnly": "yes"}, False),
])
def test_autofills_resume_only_attach_reaches_the_frames(tmp_path, extra, forwarded):
    """`resumeOnly` is checked where it can hold, in each frame at write time
    (`attachResumePdf`), so the worker carries it through."""
    out = run_node(_ATTACH_FORWARD_DRIVER_JS, {"extra": extra}, tmp_path, source=SW_JS)
    [message] = out["delivered"]
    assert message["type"] == "attach_resume_pdf"
    assert message["resumeOnly"] is forwarded

@pytest.mark.parametrize("extra, forwarded", [
    ({"flowOrigin": "https://careers-acme.icims.com"}, "https://careers-acme.icims.com"),
    ({}, None),
    # A string or nothing: a coerced value is not a vouch.
    ({"flowOrigin": 1}, None),
])
def test_the_vouched_origin_rides_the_attach_to_the_frames(tmp_path, extra, forwarded):
    """The panel's vouch (`withFlowOrigin`) reaches an iCIMS frame on a later
    step through this route too, or the attach alone would be refused there."""
    out = run_node(_ATTACH_FORWARD_DRIVER_JS, {"extra": extra}, tmp_path, source=SW_JS)
    [message] = out["delivered"]
    assert message.get("flowOrigin") == forwarded


# ---------- what the widget's test file used to be the only home for --------
#
# THREE PINS THAT WERE ORPHANED BY THE DELETION, not three new ideas. R-C
# removed `test_extension_widget.py`, and with it the only coverage of rules
# that live in `sw.js` and never left. Each was verified exploitable against a
# GREEN suite before it was written — the mutation that proves it is named in
# the test, because a pin whose exploit nobody recorded is a pin nobody can
# tell is still working.

_TELEMETRY_DRIVER_JS = r"""
let listener = null;
let posted = [];

global.fetch = async (url, init) => {
  posted.push({ url, body: JSON.parse(init.body) });
  return { ok: true, status: 200, json: async () => ({}) };
};

global.chrome = {
  runtime: {
    id: "maestro-cs-test",
    onMessage: { addListener: (callback) => { listener = callback; } },
    getManifest: () => ({ content_scripts: [{ js: ["content/agent.js"] }] }),
  },
  commands: { onCommand: { addListener: () => {} } },
  sidePanel: { setPanelBehavior: async () => {} },
  // The ONE setting this handler reads, plus the backend url `api()` needs.
  storage: {
    sync: {
      get: async (defaults) => ({ ...defaults, ...spec.settings }),
    },
  },
  tabs: { sendMessage: async () => null },
};

vm.runInThisContext(source);

main(async () => {
  const reply = await new Promise((resolve, reject) => {
    const keptOpen = listener(
      { type: "telemetry", action: spec.action, page_host: spec.pageHost,
        observations: spec.observations },
      { id: chrome.runtime.id },
      resolve);
    if (!keptOpen) reject(new Error("the router declined telemetry"));
  });
  emit({ reply, posted });
});
"""


def _telemetry(tmp_path, observations, settings=None):
    return run_node(_TELEMETRY_DRIVER_JS, {
        "observations": observations,
        "settings": settings or {},
        "action": "profile_fill",
        "pageHost": "boards.greenhouse.io",
    }, tmp_path, source=SW_JS)


def test_telemetry_is_off_when_the_user_turned_it_off(tmp_path):
    """THE OPT-IN, and it is a gate rather than a filter: nothing is posted at
    all, not a scrubbed version of it.

    EXPLOIT THIS PIN EXISTS FOR: deleting
    `if (telemetryEnabled === false) return { posted: 0 };` left the suite
    green at 875 after R-C, because the only test that drove this handler with
    the setting off lived in `test_extension_widget.py`. A silently
    re-enabled telemetry path is the worst possible thing to lose coverage of,
    since nothing a user can see reports it.
    """
    out = _telemetry(tmp_path, [{"label": "First name", "outcome": "filled"}],
                     settings={"telemetryEnabled": False})
    assert out["reply"]["data"] == {"posted": 0}
    assert out["posted"] == [], "an opted-out user's batch reached the network"


def test_telemetry_carries_no_value_a_user_typed(tmp_path):
    """THE STANDING RULE — "telemetry is value-free" — pinned at the one place
    that can enforce it: this is the only context that can fetch, so an
    observation is scrubbed HERE or not at all.

    EXPLOIT THIS PIN EXISTS FOR: adding `"value"` to `TELEMETRY_KEYS` left the
    suite green. The engine constructs observations carrying a `value` on some
    paths, so the allow-list is not belt-and-braces — it is the thing standing
    between a user's phone number and our backend.

    The allow-list is a WHITELIST and this drives it as one: the observation
    below carries three keys that must survive and four that must not, and the
    four are the shapes that actually turn up (a raw value, an answer, an
    email, a free-text note).
    """
    out = _telemetry(tmp_path, [{
        "label": "Phone", "kind": "tel", "outcome": "filled",
        "value": "+1 555 0143", "answer": "yes I am authorised",
        "email": "someone@example.com", "note": "typed by hand",
    }])
    [batch] = out["posted"]
    [observation] = batch["body"]["observations"]
    assert observation == {"label": "Phone", "kind": "tel", "outcome": "filled"}
    # Belt and braces, and cheap: the whole serialized body, so a value smuggled
    # into `page_host` or `action` fails here too.
    for leaked in ("555 0143", "authorised", "someone@example.com", "by hand"):
        assert leaked not in json.dumps(batch["body"]), leaked


def test_a_label_is_truncated_and_the_options_list_is_bounded(tmp_path):
    """The two bounds on what a scrubbed observation may still be. A label is
    page-authored text and an options list is page-authored and unbounded, so
    both are cut here rather than trusted — the backend's own schema is the
    second line, not the first.
    """
    out = _telemetry(tmp_path, [{
        "label": "L" * 400, "outcome": "no_rule",
        "options": [f"option {n}" for n in range(80)],
    }])
    [observation] = out["posted"][0]["body"]["observations"]
    assert len(observation["label"]) == 160
    assert len(observation["options"]) == 30


def test_an_empty_batch_is_not_a_round_trip(tmp_path):
    """Nothing to say, nothing sent. The engine calls this after every fill,
    including the ones that touched nothing."""
    out = _telemetry(tmp_path, [])
    assert out["reply"]["data"] == {"posted": 0}
    assert out["posted"] == []


# ---------- the run trace: gated, scrubbed to the schema's keys, then posted ----
#
# `fill_trace` is telemetry's sibling (one value-free record per RUN rather than
# per field), so it gets the same three pins: the switch, the whitelist, and the
# bounds. A fourth ties the whitelist to the backend's schema, since an odd key
# the schema forbids would 422 a whole run and lose it silently.

_TRACE_DRIVER_JS = _TELEMETRY_DRIVER_JS.replace(
    '{ type: "telemetry", action: spec.action, page_host: spec.pageHost,\n        observations: spec.observations }',
    'spec.message')
assert _TRACE_DRIVER_JS != _TELEMETRY_DRIVER_JS, "the telemetry driver's message moved"


def _post_trace(tmp_path, trace, settings=None, missing=False):
    message = {"type": "fill_trace"} if missing else {"type": "fill_trace", "trace": trace}
    out = run_node(_TRACE_DRIVER_JS, {"message": message, "settings": settings or {}},
                   tmp_path, source=SW_JS)
    return out


def _step(**over):
    return {"op": "map", "ms": 12, "route": "slot", "slot": "personal.first_name", **over}


def _trace_field(fid="f1", **over):
    return {"fid": fid, "label": "First name", "label_source": "aria-label", "shape": "text",
            "section": "About you", "required": True, "options": ["Yes", "No"], "option_count": 2,
            "family": "f:ab12", "steps": [_step()], "outcome": "verified", "round": 1, **over}


def _run_trace(**over):
    return {"run_id": "run-0001-abcd", "host": "boards.greenhouse.io",
            "started_at": "2026-10-03T10:00:00.000Z", "ended_at": "2026-10-03T10:00:09.000Z",
            "mode": "assist", "halted": "timeout", "rounds": 2, "fields": [_trace_field()], **over}


def _posted_trace(tmp_path, trace, **kw):
    out = _post_trace(tmp_path, trace, **kw)
    [posted] = out["posted"]
    assert posted["url"].endswith("/api/autofill/runs")
    return posted["body"]


def test_a_trace_is_not_posted_when_the_user_turned_telemetry_off(tmp_path):
    """The same switch as telemetry's, read the same way. A gate, not a filter."""
    out = _post_trace(tmp_path, _run_trace(), settings={"telemetryEnabled": False})
    assert out["reply"]["data"] == {"posted": 0}
    assert out["posted"] == [], "an opted-out user's run reached the network"


@pytest.mark.parametrize("trace, missing", [(None, False), (None, True), ([], False), ("x", False)],
                         ids=["null", "missing", "array", "string"])
def test_no_trace_posts_nothing(tmp_path, trace, missing):
    """The loop answers null when it could not build one."""
    out = _post_trace(tmp_path, trace, missing=missing)
    assert out["reply"]["data"] == {"posted": 0}
    assert out["posted"] == []


def test_a_posted_trace_reports_one_run(tmp_path):
    out = _post_trace(tmp_path, _run_trace())
    assert out["reply"]["data"] == {"posted": 1}


def test_a_trace_carries_none_of_the_keys_injected_at_any_level(tmp_path):
    """The whitelist, driven at run, field and step level with the shapes that
    would carry a value: a typed value, an AI answer, what a write landed and a
    prompt. The sentinels are made up; none may be on the wire."""
    sentinels = {"value": "SENTINEL-VALUE-1", "answer": "SENTINEL-ANSWER-2",
                 "wrote": "SENTINEL-WROTE-3", "prompt": "SENTINEL-PROMPT-4"}
    trace = _run_trace(**sentinels, fields=[_trace_field(
        **{k: v + "-F" for k, v in sentinels.items()},
        steps=[_step(**{k: v + "-S" for k, v in sentinels.items()})])])
    body = _posted_trace(tmp_path, trace)
    wire = json.dumps(body)
    assert "SENTINEL" not in wire
    [field] = body["fields"]
    assert not set(sentinels) & (set(body) | set(field) | set(field["steps"][0]))


def test_a_trace_keeps_exactly_the_schemas_keys_at_each_level(tmp_path):
    from app.schemas.autofill_trace import RunTrace, TraceField, TraceStep

    full_step = {"op": "step", "ms": 5, "effect": "progress", "word": "ok", "route": "slot",
                 "slot": "a.b", "why": "unclear_job", "engine": "jev", "p": 0.9, "floor": 0.5,
                 "second": "decided", "first_p": 0.4, "first_same": True, "chose_none": False,
                 "way": "same", "option": 3, "reason": "matched", "move": "click:o3"}
    body = _posted_trace(tmp_path, _run_trace(fields=[_trace_field(steps=[full_step])]))
    [field] = body["fields"]
    assert set(body) == set(RunTrace.model_fields)
    assert set(field) == set(TraceField.model_fields)
    assert set(field["steps"][0]) == set(TraceStep.model_fields)
    assert field["steps"][0] == full_step
    RunTrace.model_validate(body)


def test_a_bare_op_and_ms_step_is_kept(tmp_path):
    """A /map, /pick or /step call that failed or timed out leaves only these."""
    body = _posted_trace(tmp_path, _run_trace(fields=[_trace_field(steps=[{"op": "pick", "ms": 8000}])]))
    assert body["fields"][0]["steps"] == [{"op": "pick", "ms": 8000}]


def test_a_field_with_a_bad_fid_is_dropped_and_the_rest_post(tmp_path):
    fields = [_trace_field("ok-1"), _trace_field("bad fid!"), _trace_field(""),
              _trace_field(None), _trace_field("x" * 65), "junk", _trace_field("ok_2", outcome="Bad Outcome"),
              _trace_field("ok-3")]
    body = _posted_trace(tmp_path, _run_trace(fields=fields))
    assert [f["fid"] for f in body["fields"]] == ["ok-1", "ok-3"]


@pytest.mark.parametrize("over", [
    {"run_id": "short"}, {"run_id": "UPPER-CASE-RUN-ID"}, {"run_id": "bad id!"}, {"run_id": None}, {"run_id": 12345678},
    {"host": "not a host"}, {"host": ""}, {"started_at": "yesterday"}, {"started_at": None},
    {"ended_at": "2026-10-03T10:00:09"},  # no zone: the schema wants an aware time
    {"fields": None}, {"fields": "x"},
])
def test_a_trace_with_a_bad_run_key_posts_nothing(tmp_path, over):
    """One bad required key would 422 the run, so nothing goes."""
    out = _post_trace(tmp_path, _run_trace(**over))
    assert out["reply"]["data"] == {"posted": 0}
    assert out["posted"] == []


def test_a_run_missing_a_required_key_posts_nothing(tmp_path):
    for key in ("run_id", "host", "started_at", "ended_at"):
        trace = _run_trace()
        del trace[key]
        out = _post_trace(tmp_path, trace)
        assert out["posted"] == [], key


def test_the_run_level_keys_are_coerced_not_forwarded(tmp_path):
    body = _posted_trace(tmp_path, _run_trace(
        host="Boards.Greenhouse.IO:8443", mode="other", halted="crashed", rounds=99))
    assert body["host"] == "boards.greenhouse.io:8443"
    assert "mode" not in body and "halted" not in body
    assert body["rounds"] == 10
    assert "halted" not in _posted_trace(tmp_path, _run_trace(halted=None))
    assert _posted_trace(tmp_path, _run_trace(halted="stopped"))["halted"] == "stopped"


def test_a_trace_is_bounded_rather_than_rejected(tmp_path):
    """More than 200 fields, 40 steps, 30 options or 200 characters is cut here."""
    long_field = _trace_field("big", label="L" * 400, section="S" * 400,
                              options=["O" * 400] * 50, option_count=50, steps=[_step()] * 60)
    fields = [long_field] + [_trace_field(f"f{n}") for n in range(250)]
    body = _posted_trace(tmp_path, _run_trace(fields=fields))
    assert len(body["fields"]) == 200
    big = body["fields"][0]
    assert (len(big["label"]), len(big["section"])) == (200, 200)
    assert len(big["options"]) == 30 and {len(o) for o in big["options"]} == {200}
    assert big["option_count"] == 50
    assert len(big["steps"]) == 40


def test_the_pages_own_option_texts_are_kept(tmp_path):
    """Owner decision, 2026-10-03: option texts and the chosen index, EEO included."""
    field = _trace_field(options=["Decline to self-identify", "Yes", "No"], steps=[{"op": "pick", "ms": 3, "option": 0}])
    body = _posted_trace(tmp_path, _run_trace(fields=[field]))
    assert body["fields"][0]["options"] == ["Decline to self-identify", "Yes", "No"]
    assert body["fields"][0]["steps"][0]["option"] == 0


def test_step_numbers_are_coerced_and_odd_ones_dropped(tmp_path):
    steps = [
        {"op": "set", "ms": 12.6, "option": 249, "p": "0.5", "floor": 1.5, "first_p": -0.1},
        {"op": "set", "ms": -4, "option": 250},
        {"op": "set", "ms": 9_999_999, "option": -1},
        {"op": "set", "ms": "abc", "option": 1.5, "p": None},
        {"op": "set", "ms": None, "option": "2", "p": True, "first_same": "yes", "chose_none": 0},
        {"op": "set", "ms": "", "word": ""},
    ]
    got = _posted_trace(tmp_path, _run_trace(fields=[_trace_field(steps=steps)]))["fields"][0]["steps"]
    assert got == [
        {"op": "set", "ms": 13, "option": 249, "p": 0.5},
        {"op": "set", "ms": 0},
        {"op": "set", "ms": 600000},
        {"op": "set"},
        {"op": "set", "option": 2},
        {"op": "set"},
    ]


def test_a_step_with_an_unknown_op_is_dropped_and_odd_words_are_not_forwarded(tmp_path):
    steps = [
        {"op": "teleport", "ms": 1}, {"ms": 1}, "junk", None,
        _step(slot="Personal.First Name", move="click:ox", word="Has Caps", effect="exploded",
              route="made_up", why="other", engine="gpt", second="maybe", way="sideways", reason="vibes"),
        {"op": "move", "move": "click:o12", "word": "no_effect", "slot": "work_auth.us"},
        {"op": "write", "slot": "x" * 121},
    ]
    got = _posted_trace(tmp_path, _run_trace(fields=[_trace_field(steps=steps)]))["fields"][0]["steps"]
    assert got == [
        {"op": "map", "ms": 12},
        {"op": "move", "move": "click:o12", "word": "no_effect", "slot": "work_auth.us"},
        {"op": "write"},
    ]


def test_odd_field_level_strings_are_not_forwarded(tmp_path):
    field = _trace_field(label_source="Aria Label", family="F:XYZ", shape="carousel", section=None,
                         options=None, required="yes", option_count=-3, round=99)
    got = _posted_trace(tmp_path, _run_trace(fields=[field]))["fields"][0]
    assert "label_source" not in got and "family" not in got
    assert got["shape"] == "unknown"
    assert "section" not in got and "options" not in got and "required" not in got
    assert "option_count" not in got
    assert got["round"] == 10


def test_a_messy_trace_is_scrubbed_into_one_the_backend_accepts(tmp_path):
    """The scrub's whole job: whatever the loop (or a bug in it) hands over, the
    body that leaves validates against `RunTrace`, or nothing leaves."""
    from app.schemas.autofill_trace import RunTrace

    messy_steps = [
        {"op": "map", "ms": 1.5e9, "route": "slot", "slot": "UPPER.case", "p": 3, "value": "SENTINEL"},
        {"op": "pick", "ms": "7", "option": 9999, "reason": "nope"},
        {"op": "nope"}, {"op": "write", "word": "Has Caps"}, {"op": "move", "move": "click:o"},
    ] * 20
    fields = [
        _trace_field("a", label=None, options=[1, None, "x" * 999] * 20, steps=messy_steps, round="3"),
        _trace_field("b d"), {"label": "no fid"},
        _trace_field("c", shape={"x": 1}, outcome="verified", label_source="-", family=7),
    ]
    trace = _run_trace(run_id="run-messy-0001", host="Example.COM", rounds="2", mode="assist",
                       halted="stopped", fields=fields, extra={"answer": "SENTINEL"})
    body = _posted_trace(tmp_path, trace)
    RunTrace.model_validate(body)
    assert "SENTINEL" not in json.dumps(body)
    assert [f["fid"] for f in body["fields"]] == ["a", "c"]


def _sw_block(name, shape):
    block = re.search(shape.format(name=name), SW_CODE, re.S)
    assert block, f"sw.js no longer defines {name}"
    return block.group(1)


def _sw_keys(name):
    return set(re.findall(r"^  ([a-z_]+):", _sw_block(name, r"const {name} = \{{(.*?)\n\}};"), re.M))


def _sw_vocab(name):
    return set(re.findall(r'"([^"]+)"', _sw_block(name, r"const {name} = new Set\(\[(.*?)\]\);")))


def _sw_const(name):
    return _sw_block(name, r"const {name} = ([^\n]*?);(?: *//[^\n]*)?\n")


def _sw_regex(name):
    return re.fullmatch(r"/(.*)/", _sw_const(name)).group(1)


def _meta(model, field, attr):
    return next(getattr(m, attr) for m in model.model_fields[field].metadata
                if getattr(m, attr, None) is not None)


def test_the_trace_whitelist_mirrors_the_backends_schema():
    """The sw's keys, caps, patterns and vocabularies ARE the schema's (the
    schema is the contract; this file's whitelist only narrows what is sent).
    A name that drifts here is a key dropped or a run that 422s, silently."""
    from typing import get_args

    from app.schemas import autofill_fill as F
    from app.schemas import autofill_trace as T

    assert _sw_keys("TRACE_RUN") == set(T.RunTrace.model_fields)
    assert _sw_keys("TRACE_FIELD") == set(T.TraceField.model_fields)
    assert _sw_keys("TRACE_STEP") == set(T.TraceStep.model_fields)
    # A step also carries what the decision models say (/map, /pick, /step, polarity).
    assert set(F.DecisionTrace.model_fields) | set(F.PolarityTrace.model_fields) <= _sw_keys("TRACE_STEP")
    for name, literal in [("TRACE_OPS", T.Op), ("TRACE_EFFECTS", T.Effect), ("TRACE_SHAPES", F.Shape),
                          ("TRACE_ROUTES", F.Route), ("TRACE_WHYS", F.Why), ("TRACE_ENGINES", F.Engine),
                          ("TRACE_SECONDS", F.Second), ("TRACE_WAYS", F.PolarityWay),
                          ("TRACE_REASONS", F.StepReason)]:
        assert _sw_vocab(name) == set(get_args(literal)), name


def test_the_trace_whitelist_limits_and_patterns_mirror_the_backends_schema():
    from app.schemas import autofill_fill as F
    from app.schemas import autofill_trace as T

    assert [_sw_regex(n) for n in ("TRACE_WORD", "TRACE_SLOT", "TRACE_MOVE", "TRACE_FID", "TRACE_HOST",
                                   "TRACE_FAMILY", "TRACE_SOURCE", "TRACE_RUN_ID")] == [
        T.WORD, T.SLOT, F.MOVE_ID, F.FID, _meta(T.RunTrace, "host", "pattern"),
        _meta(T.TraceField, "family", "pattern"), _meta(T.TraceField, "label_source", "pattern"),
        _meta(T.RunTrace, "run_id", "pattern")]
    names = ("TRACE_FIELDS", "TRACE_STEPS", "TRACE_OPTIONS", "TRACE_TEXT", "TRACE_ROUNDS", "TRACE_MS",
             "TRACE_PICKS", "TRACE_SLOT_MAX")
    assert [int(_sw_const(n)) for n in names] == [
        T.MAX_RUN_FIELDS, T.MAX_FIELD_STEPS, _meta(T.TraceField, "options", "max_length"), T.LABEL_MAX,
        _meta(T.TraceField, "round", "le"), _meta(T.TraceStep, "ms", "le"), F.MAX_PICK_OPTIONS,
        _meta(T.TraceStep, "slot", "max_length")]
    assert _meta(T.RunTrace, "rounds", "le") == int(_sw_const("TRACE_ROUNDS"))


def _literal_args(model, field):
    from typing import get_args

    return {arg for part in get_args(model.model_fields[field].annotation) if part is not type(None)
            for arg in (get_args(part) or (part,))}


def test_the_trace_whitelists_remaining_literals_mirror_the_backends_schema():
    """The caps and enums written inline in the schema's Field() calls and not
    reachable from a pattern: each is a 422 if the sw's copy runs wider."""
    from app.schemas import autofill_fill as F
    from app.schemas import autofill_trace as T

    assert [int(_sw_const(n)) for n in ("TRACE_SOURCE_MAX", "TRACE_FAMILY_MAX", "TRACE_MOVE_MAX")] == [
        _meta(T.TraceField, "label_source", "max_length"), _meta(T.TraceField, "family", "max_length"),
        _meta(T.TraceStep, "move", "max_length")] == [40, 32, 40]
    assert _meta(F.StepCandidate, "mid", "max_length") == int(_sw_const("TRACE_MOVE_MAX"))
    assert _sw_vocab("TRACE_MODES") == _literal_args(T.RunTrace, "mode") == {"assist"}
    assert _sw_vocab("TRACE_HALTS") == _literal_args(T.RunTrace, "halted") == {"stopped", "timeout"}


def test_a_move_longer_than_the_schema_allows_is_dropped(tmp_path):
    """`click:o` plus digits matches the pattern at any length; the schema caps it at 40."""
    steps = [{"op": "move", "move": "click:o" + "1" * 33}, {"op": "move", "move": "click:o" + "1" * 34}]
    got = _posted_trace(tmp_path, _run_trace(fields=[_trace_field(steps=steps)]))["fields"][0]["steps"]
    assert got == [{"op": "move", "move": "click:o" + "1" * 33}, {"op": "move"}]


@pytest.mark.parametrize("stamp", [
    "2026-02-30T10:00:00Z", "2026-13-01T10:00:00Z", "2026-10-03T24:00:00Z", "2026-10-03T10:60:00Z",
    "2026-10-03T10:00:60Z", "2026-10-03T10:00:00+24:00", "2026-10-03T10:00:00+05:60", "0000-01-01T00:00:00Z",
    "2026-10-03 10:00:00Z", "2026-10-03T10:00:00",
])
def test_a_time_pydantic_would_refuse_posts_nothing(tmp_path, stamp):
    """A Date rolls 02-30 into March and 24:00 into tomorrow, so `Date.parse` alone
    would pass what an AwareDatetime refuses; the whole run would 422 and be lost."""
    assert _post_trace(tmp_path, _run_trace(started_at=stamp))["posted"] == []


@pytest.mark.parametrize("stamp", ["2026-02-28T23:59:59Z", "2024-02-29T00:00:00.123456Z",
                                   "2026-10-03T10:00:00+05:30", "2026-10-03T10:00:00-23:59"])
def test_a_time_pydantic_accepts_is_kept(tmp_path, stamp):
    from app.schemas.autofill_trace import RunTrace

    body = _posted_trace(tmp_path, _run_trace(started_at=stamp))
    assert body["started_at"] == stamp
    RunTrace.model_validate(body)


def test_the_broadcast_allow_list_is_pinned_and_not_the_harmless_ones():
    """`page_broadcast`'s allow-list, beside the `panel_frame0` one it is
    deliberately NOT merged with (see that handler's own note: this list may
    not name a frame, the other one may).

    EXPLOIT THIS PIN EXISTS FOR: a type added to BROADCASTABLE once left the
    suite green. `panel_frame0`'s list is pinned by a driven test three
    sections up; this one had its only pin in `test_extension_widget.py`.
    A type added here is a message fanned out to
    EVERY frame of a tab — including the ad and analytics iframes a job page
    carries — so the list growing quietly is exactly the failure
    `frameMayReceiveUserData` exists to catch on the other side.

    A SOURCE PIN rather than a driven one, and the reason is the sibling: the
    driven `panel_frame0` cases already prove the router refuses an
    unlisted type, so what is unwatched is the CONTENT of this constant, which
    is a literal.
    """
    listed = re.search(
        r"const BROADCASTABLE = \[(.*?)\];", SW_CODE, re.S)
    assert listed, "BROADCASTABLE is not where this test expects it"
    assert re.findall(r'"([a-z_]+)"', listed.group(1)) == [
        "profile_fill", "collect_open_questions", "fill_answers",
        "guided_write", "scroll_to_field",
        # The fill engine's page operations: a field can be in any frame, and
        # each is gated on the receiving side (fill_cancel aside, which carries
        # nothing) — see test_extension_frame_gate.
        "fill_inventory", "fill_explore", "fill_apply", "fill_step_state", "fill_sweep", "fill_focus", "fill_cancel",
        "fill_sections", "fill_add",
        # The form verdict, asked of every frame when frame 0 has none: an
        # embedded cross-origin form (Greenhouse on block.xyz) is in a
        # subframe. It carries and returns no user data.
        "detect_page",
        # The posting, asked of every frame when frame 0's answer is not a job
        # description: iCIMS renders the posting in a same-origin iframe
        # (`#icims_content_iframe`). It carries nothing and returns only the
        # frame's own page text, the public posting.
        "extract_job_posting",
    ]


_HOTKEY_DRIVER_JS = r"""
let onCommand = null;
let warnings = [];
let opened = [];

global.console = { ...console, warn: (...args) => warnings.push(args.map(String).join(" ")) };

global.chrome = {
  runtime: {
    id: "maestro-cs-test",
    onMessage: { addListener: () => {} },
    getManifest: () => ({ content_scripts: [{ js: ["content/agent.js"] }] }),
  },
  commands: { onCommand: { addListener: (callback) => { onCommand = callback; } } },
  // `open` is present only when the spec says so: it landed in Chrome 116 and
  // this extension's minimum is 114, so ABSENT is a real browser and not a
  // hypothetical one.
  sidePanel: {
    setPanelBehavior: async () => {},
    ...(spec.canOpen ? { open: async (options) => { opened.push(options); } } : {}),
  },
  scripting: { executeScript: async () => {} },
  tabs: { sendMessage: async () => null },
};

vm.runInThisContext(source);

main(async () => {
  // Thrown synchronously out of the listener is the failure mode that matters:
  // a service worker has nobody to catch it.
  let threw = null;
  try {
    onCommand(spec.command, spec.tab);
  } catch (err) {
    threw = String(err.message ?? err);
  }
  // `settle()` is the PANEL harness's; this driver runs on the base prelude.
  // One macrotask turn is all that is needed — `sidePanel.open` is awaited by
  // nobody, so its `.catch` has to be given a chance to run before we look.
  await new Promise((resolve) => setTimeout(resolve, 0));
  emit({ threw, opened, warnings });
});
"""


def _hotkey(tmp_path, command="toggle-widget", tab=None, can_open=True):
    return run_node(_HOTKEY_DRIVER_JS,
                    {"command": command, "tab": tab, "canOpen": can_open},
                    tmp_path, source=SW_JS)


def test_the_hotkey_opens_the_panel_on_the_tab_it_fired_on(tmp_path):
    out = _hotkey(tmp_path, tab={"id": 7})
    assert out["threw"] is None
    assert out["opened"] == [{"tabId": 7}]
    assert out["warnings"] == []


def test_the_hotkey_on_a_tab_chrome_did_not_name_does_nothing(tmp_path):
    """`chrome.commands` hands the listener a `tab` that can be undefined, and
    a devtools window or a detached popup is where that happens.

    EXPLOIT THIS PIN EXISTS FOR: deleting the
    `if (!Number.isInteger(tab?.id) || tab.id < 0) return;` guard left the
    suite green — `sidePanel.open({tabId: undefined})` then rejects inside a
    service worker with nobody watching, and the user's shortcut silently does
    nothing with no way to find out why. Silence is the CORRECT outcome here;
    what is not correct is a throw or a rejected promise.
    """
    for tab in (None, {}, {"id": -1}, {"id": "7"}):
        out = _hotkey(tmp_path, tab=tab)
        assert out["threw"] is None, (tab, out)
        assert out["opened"] == [], (tab, out)


def test_a_chrome_without_side_panel_open_says_why_instead_of_throwing(tmp_path):
    """114 and 115: the `sidePanel` API is there and `open()` is not.

    The honest outcome is a log naming the version and the working alternative,
    because a TypeError out of a service worker reaches nobody at all. The
    toolbar icon still opens the panel on those versions, which is why the
    minimum stays at 114 rather than being raised to 116.
    """
    out = _hotkey(tmp_path, tab={"id": 7}, can_open=False)
    assert out["threw"] is None
    assert out["opened"] == []
    [warning] = out["warnings"]
    assert "116" in warning and "toolbar" in warning


def test_another_command_is_not_the_panel_command(tmp_path):
    """The listener is keyed on the command name, so a second command added to
    the manifest later does not inherit this behaviour by accident."""
    out = _hotkey(tmp_path, command="some-other-command", tab={"id": 7})
    assert out["opened"] == []
    assert out["warnings"] == []
