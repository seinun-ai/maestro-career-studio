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
    """`extract_job_posting` lives in the top document, so the panel needs a
    door page_broadcast deliberately does not open. That door names a frame,
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
      { type: "api", path: "/api/applications/app-1" },
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


def test_the_broadcast_allow_list_is_five_types_and_not_the_harmless_ones():
    """`page_broadcast`'s allow-list, beside the `panel_frame0` one it is
    deliberately NOT merged with (see that handler's own note: this list may
    not name a frame, the other one may).

    EXPLOIT THIS PIN EXISTS FOR: adding `"extract_job_posting"` to
    BROADCASTABLE left the suite green. `panel_frame0`'s list is pinned by a
    driven test three sections up; this one had its only pin in
    `test_extension_widget.py`. A type added here is a message fanned out to
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
    ]
    # …and the one that must never join it, named rather than left to the list
    # above: a posting's JSON-LD is in the top document, so broadcasting the
    # read would touch every subframe for nothing. It has `panel_frame0`.
    assert "extract_job_posting" not in listed.group(1)


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
