"""The manifest contract, the frame keys, and why the service worker exists.

Almost nothing in `extension/sw.js` can be tested from here. `chrome.*` does not
exist in Node, the harness models a PAGE rather than an extension runtime, and
faking the whole API surface would only test the fake. So this file tests four
things that are real:

1. **The manifest is a contract with the browser.** A `content_scripts` entry
   naming a file that is not on disk does not degrade — the whole entry fails to
   inject — and nothing in the repo would otherwise notice a renamed file.

2. **The migration state.** Task 8 ADDED the content-script path beside the side
   panel rather than replacing it, and `test_the_side_panel_path_is_still_live`
   was where "both live" was written down. Task 19 cut the panel and INVERTED
   that test into `test_the_side_panel_path_is_gone` — every present became an
   absent, in place, rather than a deletion. That is deliberate: the §13 row
   `extension-sidepanel-path` is now gone from SYSTEM.md (green rows are not
   left behind), so this test is the only surviving record that the panel
   existed and that removing it was the plan rather than an accident. A future
   `side_panel` key would be a regression, and nothing else in the repo would
   notice one.

3. **The CORS constraint that makes the service worker load-bearing.** Design
   §3.2 says a content script cannot call the backend directly, so every fetch
   is proxied through the SW. Half of that claim lives in this repo and is
   asserted below against the real app; the other half does not.

4. **The pure helpers the router is built from** — the frame key and the
   backend-path guard — run in node against `extension/sw.js` itself. They are
   the parts with edge cases: a key that cannot be addressed again, and a path
   that moves the host it is concatenated onto.

WHAT IS NOT COVERED, and what would settle it — recorded here rather than in a
report, because the next person to touch this file is the one who needs it:

- **Does a content script's fetch present the PAGE's origin?** That is the step
  that turns the CORS config below into a refusal. Chrome documents it; it was
  NOT executed here. Settle it by loading the extension unpacked, opening a
  Workday posting, and calling `fetch("http://localhost:8001/health")` from the
  content script's console — expect a CORS failure there and a success through
  the SW proxy.

- **Does `content -> chrome.runtime.sendMessage -> SW fetch` survive a strict
  page CSP?** Unverified. Same session, same page: `GET /api/jobs/match?url=`
  through the proxy on a page serving `connect-src` that excludes localhost.

- **Is `sender.id` set on a message from our own content script?** The router
  drops anything where it does not equal `chrome.runtime.id`, which is the
  documented idiom — but if it were ever unset for content scripts, that check
  would silently drop EVERY proxied call. It costs nothing to confirm on the
  first real round-trip, and nothing calls the router until Task 9.

- **Do the files in one `js` array share top-level scope?** Still unverified —
  a probe extension was written and Chrome 150 refused to load it
  ("--load-extension is not allowed in Google Chrome, ignoring"), which no
  command-line flag overrides in a branded build. Settle it by loading unpacked
  with developer mode on and evaluating `typeof detectPage` from `agent.js`.

  **Nothing depends on the answer any more.** Task 10 made each file publish
  what it exports onto `window.careerStudioCompanion` explicitly, which is
  correct under both readings: whatever scope a file body gets, the isolated
  world has one global object. `test_extension_widget.py` pins that, and the
  question above is now curiosity rather than a blocker.
"""

import base64
import hashlib
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.extension_harness import run_node


ROOT = Path(__file__).resolve().parents[2]
EXTENSION = ROOT / "extension"
MANIFEST = EXTENSION / "manifest.json"


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def content_script(manifest) -> dict:
    entries = manifest["content_scripts"]
    assert len(entries) == 1, "one entry: a second one would inject twice into every frame"
    return entries[0]


# ---------- the manifest is a contract with the browser ----------


def test_the_manifest_is_valid_json_and_still_v3(manifest):
    """MV2 is dead; a v2 manifest would not load at all."""
    assert manifest["manifest_version"] == 3


def test_the_pinned_key_still_hashes_to_the_id_the_backend_admits(manifest):
    """The manifest `key` and the CORS default are two halves of one fact.

    Chrome derives an unpacked extension's id from its public key: sha256 of the
    DER bytes, first 16 bytes, each hex nibble mapped 0-f onto a-p. Pinning the
    key is what makes the id knowable ahead of time, which is what lets
    `config.maestro_cs_extension_ids` default to it and deletes the old
    copy-the-id-into-.env-and-restart step.

    Both halves have to move together. Rotating the key without updating the
    default (or the reverse) fails CLOSED and nearly silently: the extension
    loads, the widget mounts, and every backend call is refused by CORS with
    nothing but a connection error on the card to say why. That symptom is
    indistinguishable from "the backend isn't running", which is why this is
    asserted here rather than left to be discovered in a browser.
    """
    from app.config import Settings

    key = manifest.get("key")
    assert key, (
        "extension/manifest.json lost its `key`. Without it Chrome generates an "
        "id per install, and the CORS default below can no longer match."
    )

    digest = hashlib.sha256(base64.b64decode(key)).hexdigest()[:32]
    derived_id = "".join(chr(ord("a") + int(nibble, 16)) for nibble in digest)

    # Read the field DEFAULT, not the live setting: conftest sets
    # MAESTRO_CS_EXTENSION_IDS for the CORS tests, so the environment here says
    # nothing about what a user who sets nothing would get.
    default_ids = Settings.model_fields["maestro_cs_extension_ids"].default
    assert derived_id in default_ids, (
        f"the pinned key hashes to {derived_id!r}, which is not in the backend's "
        f"default extension allowlist {default_ids!r}. Update "
        "app/config.py, .env.example and extension/README.md together."
    )


def test_every_file_the_manifest_names_exists(manifest, content_script):
    """A missing file is not a degraded feature; it breaks the load.

    Which symptom exactly — a refused install or an entry that silently fails
    to inject — was NOT reproduced here, because this environment cannot load
    an extension. It does not matter: nothing else in this repo reads these
    paths — no bundler, no import graph, no build step — so this assertion is
    the whole of the safety net either way.
    """
    named = [
        *content_script["js"],
        manifest["background"]["service_worker"],
    ]
    missing = [path for path in named if not (EXTENSION / path).is_file()]
    assert missing == [], f"manifest names files that do not exist: {missing}"


def test_the_content_script_is_the_split_modules_in_dependency_order(content_script):
    """Order is load order: shared modules before every consumer, then the UI.

    Pinned as a list rather than a set because Chrome injects the array in
    order, so this is the only place that ordering is stated.
    """
    assert content_script["js"] == [
        "content/job-posting.js",
        "content/policy.js",
        "content/eeo.js",
        "content/autofill.js",
        "content/open-questions.js",
        "content/detect.js",
        "content/agent.js",
        "content/widget.js",
    ]


def test_agent_is_only_the_page_rpc_front_door():
    """The split is defeated if a moved engine leaves a stale agent.js copy."""
    source = (EXTENSION / "content" / "agent.js").read_text(encoding="utf-8")
    assert len(source.splitlines()) < 700
    assert "function fillFormFromProfile" not in source
    assert "function collectOpenQuestions" not in source
    assert "function fillAnswersByQid" not in source
    assert "const findJobPosting =" not in source


def test_the_content_script_runs_in_every_frame(content_script):
    """`all_frames` is the entire reason this entry exists rather than an
    `executeScript` call on the active tab.

    Greenhouse and Lever put the application form in a subframe while the top
    frame is marketing and carries no form at all (design §3.1). A top-frame-only
    injection sees the marketing page on exactly the boards this tool is for.
    """
    assert content_script["all_frames"] is True
    # about:blank and srcdoc frames inherit their opener's origin; without these
    # two the entry skips them, and ATS wizards render steps into both.
    assert content_script["match_about_blank"] is True
    assert content_script["match_origin_as_fallback"] is True


def test_the_entry_and_the_host_permissions_cover_the_same_broad_surface(
    manifest, content_script
):
    """Broad on purpose, and the two lists have to agree.

    Workable, Greenhouse, Lever and Ashby all support custom customer domains
    and Workday URL components are not guessable, so a hostname allowlist has
    poor recall (design §3.4). `host_permissions` is what lets the SW fetch;
    `matches` is what injects the gate. A narrower `matches` would mean pages
    the extension may act on but never looks at.
    """
    assert set(content_script["matches"]) == {"https://*/*", "http://*/*"}
    assert set(manifest["host_permissions"]) == {"http://*/*", "https://*/*"}
    # The gate reads the DOM, so it cannot run before there is one. document_idle
    # is also the cheapest slot: it does not delay the page's own load.
    assert content_script["run_at"] == "document_idle"


def test_webnavigation_is_declared_and_has_no_consumer_yet(manifest):
    """Declared at Task 8, first used at Task 18 (the SPA route-change re-run:
    an ATS wizard changes step without a document load, so the gate has to be
    re-run on `history.pushState`).

    Pinned because a permission with no call site is exactly what a later
    cleanup deletes as dead — and its absence would not fail any other test,
    it would just make the re-run silently never fire.
    """
    assert "webNavigation" in manifest["permissions"]


def test_the_content_script_stays_out_of_the_page_world(content_script):
    """ISOLATED, not MAIN: the page must not be able to reach our functions.

    In MAIN the page shares our global, so any script on it could call the fill
    engine — with the user's profile behind it — or shadow a function we call.
    """
    assert content_script["world"] == "ISOLATED"


# ---------- migration state: the panel is gone ----------


def test_the_side_panel_path_is_gone(manifest):
    """The INVERSION of `test_the_side_panel_path_is_still_live`, in place.

    Between Task 8 and Task 19 both UIs shipped: the content-script path was
    ADDED beside the panel because the panel was the only working UI and the
    owner used it daily. That test asserted the panel's three permissions, its
    manifest key and its file were all present, and said in its own docstring
    that Task 19 would flip it. This is the flip.

    Kept rather than deleted, and the reason is the ledger rule in SYSTEM.md
    §13: a migration row is deleted once it goes green, so
    `extension-sidepanel-path` is no longer in that table. Nothing else in the
    repo records that the panel existed. A `side_panel` key reappearing, or a
    permission creeping back into the manifest, would otherwise pass unnoticed
    — there is no bundler and no import graph reading this file.

    `activeTab` goes with it, not after it.

    `scripting` ALSO went with it — Task 9 rewired the panel from
    `chrome.scripting.executeScript` to `chrome.tabs.sendMessage`, leaving the
    permission with no call site — and has since come BACK, for a reason that
    has nothing to do with the panel: the toolbar icon and the hotkey inject
    the content scripts into a tab that was already open when the extension
    last reloaded. That tab has no content script, every route into the widget
    failed there, and "the icon does nothing" was the reported symptom. So the
    rule this test enforces is the honest one — a permission is present only
    while `extension/` really calls it — rather than a fixed list.
    """
    assert "side_panel" not in manifest
    for permission in ("sidePanel", "activeTab"):
        assert permission not in manifest["permissions"], (
            f"{permission} was the side panel's; nothing left in extension/ "
            "uses it"
        )
    assert set(manifest["permissions"]) == {
        "storage", "tabs", "webNavigation", "scripting",
    }
    # The permission and its call site travel together, in both directions.
    sw = (EXTENSION / "sw.js").read_text(encoding="utf-8")
    uses_scripting = re.search(r"^(?!\s*(//|\*)).*chrome\.scripting\.", sw, re.M)
    assert bool(uses_scripting) == ("scripting" in manifest["permissions"]), (
        "scripting is declared with no live call site, or called without being "
        "declared"
    )
    for name in ("sidepanel.html", "sidepanel.css", "sidepanel.js"):
        assert not (EXTENSION / name).exists(), f"{name} came back"


def test_the_service_worker_replaced_background_js(manifest):
    """A manifest declares exactly ONE service worker, so `background.js` could
    not stay: its three lines moved into `sw.js` with the registration.

    What it carried over — `chrome.sidePanel.setPanelBehavior` — was deleted at
    Task 19 with the panel. What replaced it as the toolbar action's job is the
    `chrome.action.onClicked` listener, which messages the widget. Asserted as a
    source scan, which is all a text search can honestly claim; whether the
    listener fires is a browser question, and sw.js says so at the call site.
    """
    assert manifest["background"]["service_worker"] == "sw.js"
    assert not (EXTENSION / "background.js").exists(), "the old worker is a second registration"
    source = (EXTENSION / "sw.js").read_text(encoding="utf-8")
    assert "chrome.action.onClicked.addListener" in source
    # Comment lines dropped first, and not as a convenience: the comment above
    # that listener names the deleted `setPanelBehavior` call on purpose — it is
    # the record of what the icon used to do and of the one question removing it
    # was meant to settle. A bare substring search would find that forever and
    # assert nothing.
    code = [
        line for line in source.splitlines()
        if not line.lstrip().startswith(("//", "*", "/*"))
    ]
    assert [line for line in code if "sidePanel" in line] == []


# ---------- the service worker owns the backend ----------


def test_no_content_script_calls_the_backend_directly():
    """Design §3.2, as a rule that outlives the task that wrote it.

    Every backend call goes content -> sendMessage -> SW. Today these files are
    nearly empty so this passes trivially; it earns its keep in Task 9, when the
    engine moves in carrying the resume-PDF download, which is the one call that
    will want to be a direct fetch.
    """
    offenders = []
    for path in sorted((EXTENSION / "content").glob("*.js")):
        source = path.read_text(encoding="utf-8")
        for pattern in (r"\bfetch\s*\(", r"\bXMLHttpRequest\b"):
            if re.search(pattern, source):
                offenders.append(f"{path.name}: {pattern}")
    assert offenders == [], (
        "a content script's fetch is documented to present the PAGE's origin — "
        "which backend CORS refuses, though that half is unverified here (see "
        f"the module docstring). Route it through the service worker: {offenders}"
    )


ATS_PAGE_ORIGIN = "https://acme.wd5.myworkdayjobs.com"
EXTENSION_ORIGIN = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"


@pytest.mark.parametrize(
    "origin, allowed",
    [
        (ATS_PAGE_ORIGIN, False),
        ("https://boards.greenhouse.io", False),
        ("null", False),  # a sandboxed iframe's opaque origin
        (EXTENSION_ORIGIN, True),
        ("http://localhost:3000", True),  # the web app
    ],
)
def test_backend_cors_admits_the_extension_and_no_ats_host(origin, allowed):
    """The constraint the service worker exists to satisfy.

    `api()` sends `Content-Type: application/json` on every call, which is not a
    CORS-safelisted value, so every call is preflighted — including the reads.
    A page origin gets 400 and no `Access-Control-Allow-Origin`; the extension
    origin gets 200 and the header back.

    If a later change widens `allow_origins` to make a direct content-script
    fetch work, this test fails, and that is the point: the design calls
    widening CORS the wrong trade (design §3.2).

    `EXTENSION_ORIGIN` passes only because conftest configures its id in
    `MAESTRO_CS_EXTENSION_IDS`. Extension origins are allow-listed one id at
    a time since 2026-08-04 — the old `chrome-extension://.*` regex trusted every
    extension the user had installed against a zero-auth API. That any OTHER
    extension id is refused is pinned in `test_security_boundaries.py`.
    """
    # No `with`: the lifespan (and its DB seeding) is not needed to answer a
    # preflight, and /health touches nothing.
    client = TestClient(app)
    response = client.options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    if allowed:
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == origin
    else:
        assert response.status_code == 400
        assert "access-control-allow-origin" not in response.headers


# ---------- frame keys ----------

_SW_HELPERS_DRIVER_JS = r"""
const frameKey = extract("frameKey", "\n// ---- end frameKey ----");
const parseFrameKey = extract("parseFrameKey", "\n// ---- end parseFrameKey ----");
const assertBackendPath = extract("assertBackendPath", "\n// ---- end assertBackendPath ----");
const proxyInit = extract("proxyInit", "\n// ---- end proxyInit ----");
const api = extract("api", "\n// ---- end api ----");
const sendToFrame = extract("sendToFrame", "\n// ---- end sendToFrame ----");

// The extracted functions reach these as free variables. Only the recorders
// are fake: what is under test is which address `sendToFrame` ends up calling
// and which init `api` ends up handing to fetch, so the fakes record and
// return, and never decide anything.
global.frameKey = frameKey;
global.parseFrameKey = parseFrameKey;
global.getSettings = async () => ({ backendUrl: "http://localhost:8001" });

let sent = [];
let fetched = [];
global.chrome = {
  tabs: {
    sendMessage: (tabId, message, options) => {
      sent.push({ tabId, message, options });
      return Promise.resolve("delivered");
    },
  },
};
global.fetch = (url, init) => {
  fetched.push({ url, init });
  return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
};

main(async () => {
  // What `${backendUrl}${path}` actually resolves to, asked of the URL parser
  // rather than assumed — the guard's whole justification is that some of
  // these strings move the host.
  const resolved = {};
  for (const [name, path] of Object.entries(spec.paths)) {
    let host;
    try { host = new URL("http://localhost:8001" + path).host; }
    catch (_) { host = "invalid-url"; }
    let allowed = true;
    try { assertBackendPath(path); } catch (_) { allowed = false; }
    resolved[name] = { host, allowed };
  }

  const keys = {};
  for (const [name, sender] of Object.entries(spec.senders)) {
    keys[name] = frameKey(sender);
  }
  const parsed = {};
  for (const [name, key] of Object.entries(spec.keys)) {
    parsed[name] = parseFrameKey(key);
  }
  // Every key the SW can MINT has to be one it can also address, or a fill
  // dispatch aims at nothing.
  const roundTrip = Object.fromEntries(
    Object.entries(keys)
      .filter(([, key]) => key !== null)
      .map(([name, key]) => [name, parseFrameKey(key)])
  );
  // Who may address whom. Recorded as "did chrome.tabs.sendMessage happen at
  // all, and with what address" rather than "did it throw", because the
  // hazard is a fill arriving somewhere nobody asked for.
  const dispatch = {};
  for (const [name, attempt] of Object.entries(spec.dispatches)) {
    sent = [];
    let error = null;
    try {
      await sendToFrame(attempt.sender, attempt.target, { type: "fill" });
    } catch (e) {
      error = String(e.message);
    }
    dispatch[name] = { error, sent };
  }

  // What actually reaches fetch. `guarded` is the composition HANDLERS.api
  // uses; `unguarded` is the same call without the filter, and it is here to
  // show the leak is real rather than theoretical.
  const hostile = {
    method: "DELETE",
    body: "{}",
    headers: { Authorization: "Bearer stolen" },
    credentials: "include",
  };
  fetched = [];
  await api(assertBackendPath("/api/jobs/1"), proxyInit(hostile));
  const guarded = fetched[0];
  fetched = [];
  await api("/api/jobs/1", hostile);
  const unguarded = fetched[0];

  emit({ keys, parsed, roundTrip, resolved, dispatch, guarded, unguarded });
});
"""


@pytest.fixture(scope="module")
def sw_helpers(tmp_path_factory) -> dict:
    """`sw.js` is not in EXTENSION_SOURCES — it never runs in a page — so the
    source is passed explicitly."""
    return run_node(
        _SW_HELPERS_DRIVER_JS,
        {
            "senders": {
                "top": {"tab": {"id": 7}, "frameId": 0},
                "subframe": {"tab": {"id": 7}, "frameId": 3},
                "otherTab": {"tab": {"id": 12}, "frameId": 3},
                # Any extension page (the panel was one): no tab at all.
                "extensionPage": {"frameId": 0},
                # Chrome's TAB_ID_NONE. A number, and addressable by nothing.
                "noTab": {"tab": {"id": -1}, "frameId": 0},
                # A sender that somehow lost its frame: must not become the top
                # frame by default.
                "noFrameId": {"tab": {"id": 7}},
            },
            "dispatches": {
                # The widget, in the top frame, addressing the application
                # subframe. The one case that must work.
                "widgetToFormFrame": {
                    "sender": {"tab": {"id": 7}, "frameId": 0},
                    "target": "7:3",
                },
                # An ad iframe on a Greenhouse posting, naming its sibling.
                "adFrameToSibling": {
                    "sender": {"tab": {"id": 7}, "frameId": 9},
                    "target": "7:3",
                },
                # …and naming the top frame.
                "adFrameToTop": {
                    "sender": {"tab": {"id": 7}, "frameId": 9},
                    "target": "7:0",
                },
                # A top frame reaching into somebody else's tab.
                "crossTab": {
                    "sender": {"tab": {"id": 7}, "frameId": 0},
                    "target": "12:0",
                },
                # An extension page: no tab, so no frame to speak from.
                "noTabSender": {
                    "sender": {"frameId": 0},
                    "target": "7:0",
                },
                "junkTarget": {
                    "sender": {"tab": {"id": 7}, "frameId": 0},
                    "target": "7",
                },
            },
            "paths": {
                "route": "/api/jobs/match?url=https://acme.test/job/1",
                "atSignInPath": "/questions/1@2",
                "userinfo": "@evil.test/steal",
                "userinfoDotted": ".@evil.test/x",
                "absolute": "https://evil.test/x",
                "protocolRelative": "//evil.test/x",
                "relative": "api/jobs",
            },
            "keys": {
                "top": "7:0",
                "subframe": "7:3",
                "empty": "",
                "oneHalf": "7",
                "threeParts": "7:3:1",
                "negative": "-1:0",
                "notNumbers": "tab:frame",
                "trailingSpace": "7:0 ",
                # JS `$` without /m is strict end-of-input, unlike Python's,
                # which accepts a trailing newline. Pinned because the next
                # reader of that regex works in Python all day.
                "trailingNewline": "7:0\n",
            },
        },
        tmp_path_factory.mktemp("frame-keys"),
        source=(EXTENSION / "sw.js").read_text(encoding="utf-8"),
    )


def test_a_frame_key_names_a_frame_not_a_tab(sw_helpers):
    """`all_frames` means one tab sends many messages, so the tab id alone is
    not an identity — which is the reason the SW keys on the pair at all."""
    keys = sw_helpers["keys"]
    assert keys["top"] == "7:0"
    assert keys["subframe"] == "7:3"
    assert keys["top"] != keys["subframe"]
    assert keys["subframe"] != keys["otherTab"]


def test_a_sender_that_is_not_an_addressable_frame_gets_no_key(sw_helpers):
    """Three ways to have no frame, all of which used to be spellable as a key.

    `noFrameId` is the one that matters: defaulted to 0 it would silently name
    the TOP frame, so a fill meant for the application subframe would run
    against the marketing page.
    """
    keys = sw_helpers["keys"]
    assert keys["extensionPage"] is None
    assert keys["noTab"] is None
    assert keys["noFrameId"] is None


def test_a_minted_key_can_always_be_addressed_again(sw_helpers):
    """Round-trip, as numbers: `chrome.tabs.sendMessage` takes a numeric tab id
    and a string one silently addresses nothing."""
    assert sw_helpers["roundTrip"] == {
        "top": {"tabId": 7, "frameId": 0},
        "subframe": {"tabId": 7, "frameId": 3},
        "otherTab": {"tabId": 12, "frameId": 3},
    }


# ---------- who may address whom ----------


def test_only_the_top_frame_may_aim_the_fill_engine(sw_helpers):
    """A frame key arrives in a MESSAGE, and the recipient is our fill engine.

    The widget mounts only in the top frame (design §3.1), so a request to
    message another frame that comes from a subframe is not the UI — on a
    Greenhouse posting it is an ad iframe naming the frame that holds the
    application form. Asserted as "nothing was dispatched", not "it threw":
    what matters is that no fill arrived anywhere.
    """
    dispatch = sw_helpers["dispatch"]

    legitimate = dispatch["widgetToFormFrame"]
    assert legitimate["error"] is None
    assert legitimate["sent"] == [
        {"tabId": 7, "message": {"type": "fill"}, "options": {"frameId": 3}}
    ], "the frameId option is the point: without it every frame gets the message"

    for name in ("adFrameToSibling", "adFrameToTop"):
        assert dispatch[name]["sent"] == [], f"{name} reached a frame"
        assert "top frame" in dispatch[name]["error"]


def test_a_frame_cannot_reach_into_another_tab(sw_helpers):
    """Nothing a user did in one tab authorises a fill in a different one."""
    crossed = sw_helpers["dispatch"]["crossTab"]
    assert crossed["sent"] == []
    assert "cross-tab" in crossed["error"]


def test_a_dispatch_needs_a_real_sender_and_a_real_target(sw_helpers):
    dispatch = sw_helpers["dispatch"]
    assert dispatch["noTabSender"]["sent"] == []
    assert dispatch["junkTarget"]["sent"] == []


# ---------- the proxy's one input ----------


def test_a_message_cannot_set_request_headers(sw_helpers):
    """`api()` spreads `...opts` AFTER its own `headers`, so a caller-supplied
    `headers` REPLACES the default instead of merging with it.

    `unguarded` runs the same call without the filter and is the demonstration:
    the leak is real, so the allowlist is load-bearing rather than decorative.
    """
    unguarded = sw_helpers["unguarded"]["init"]
    assert unguarded["headers"] == {"Authorization": "Bearer stolen"}
    assert "Content-Type" not in unguarded["headers"]

    guarded = sw_helpers["guarded"]["init"]
    assert guarded["headers"] == {"Content-Type": "application/json"}
    assert "credentials" not in guarded
    # method and body are the two keys a proxied call legitimately sets.
    assert guarded["method"] == "DELETE"
    assert guarded["body"] == "{}"
    assert sw_helpers["guarded"]["url"] == "http://localhost:8001/api/jobs/1"


def test_the_proxy_handler_applies_both_guards():
    """A source assertion, and it says so.

    The test above runs `assertBackendPath` + `proxyInit` in the composition
    the handler is supposed to use; this is what catches the handler being
    changed to skip one of them.
    """
    source = (EXTENSION / "sw.js").read_text(encoding="utf-8")
    assert "api(assertBackendPath(msg.path), proxyInit(msg.init))" in source


def test_a_proxied_path_cannot_move_the_backend_host(sw_helpers):
    """The router is reachable from a content script running on a hostile page,
    and `api()` builds its URL by concatenation.

    `resolved` is what the URL parser makes of `http://localhost:8001` + each
    path, so the danger is demonstrated rather than asserted: two of these
    strings really do relocate the host, because a URL's authority ends at the
    first `/` and everything before it becomes userinfo.
    """
    resolved = sw_helpers["resolved"]

    # Demonstrated first: these are the escapes, and the guard refuses them.
    assert resolved["userinfo"]["host"] == "evil.test"
    assert resolved["userinfoDotted"]["host"] == "evil.test"
    assert resolved["userinfo"]["allowed"] is False
    assert resolved["userinfoDotted"]["allowed"] is False

    # A leading slash keeps the host, `@` inside the path and all.
    assert resolved["route"]["host"] == "localhost:8001"
    assert resolved["atSignInPath"]["host"] == "localhost:8001"
    assert resolved["route"]["allowed"] is True
    assert resolved["atSignInPath"]["allowed"] is True

    # Not escapes, still refused: an absolute URL does not even parse after
    # concatenation, and `//` stays on localhost. Neither is a real route, and
    # the narrow rule is the one that stays obviously correct.
    assert resolved["absolute"]["host"] == "invalid-url"
    assert resolved["relative"]["host"] == "invalid-url"
    assert resolved["protocolRelative"]["host"] == "localhost:8001"
    for name in ("absolute", "relative", "protocolRelative"):
        assert resolved[name]["allowed"] is False


def test_a_key_that_is_not_two_numbers_is_rejected(sw_helpers):
    """Rejected rather than coerced. `parseInt("7:3:1")` is 7, which is a real
    tab and the wrong frame — a wrong address is worse than no address."""
    parsed = sw_helpers["parsed"]
    assert parsed["top"] == {"tabId": 7, "frameId": 0}
    assert parsed["subframe"] == {"tabId": 7, "frameId": 3}
    for junk in (
        "empty", "oneHalf", "threeParts", "negative",
        "notNumbers", "trailingSpace", "trailingNewline",
    ):
        assert parsed[junk] is None, f"{junk} parsed to something"


def test_the_explicit_routes_inject_before_giving_up(manifest):
    """"The icon does nothing" — the reported bug, and its real cause.

    A content script enters a page when the PAGE loads, so a tab that was
    already open when the extension was installed or reloaded has none. Every
    route into the widget then fails there, and the only remedy was knowing
    that the tab had to be reloaded. The toolbar icon and the hotkey now inject
    the scripts and retry once.

    Injection belongs to those two routes ONLY. Page load must never reach it:
    injecting into a page nobody asked about is exactly the always-on cost the
    detection gate exists to avoid, and it would run on every tab on the web.
    """
    sw = (EXTENSION / "sw.js").read_text(encoding="utf-8")
    assert "chrome.scripting.executeScript" in sw
    # Read from the manifest, never restated: the injection order is
    # load-bearing (each module publishes onto the namespace the next reads).
    assert "chrome.runtime.getManifest()" in sw
    assert re.search(r"files:\s*contentScriptFiles\(\)", sw)
    # Every frame, or the widget mounts and cannot reach a Greenhouse form in
    # its iframe.
    assert re.search(r"allFrames:\s*true", sw)
    # The retry is behind the two explicit routes, which both go through
    # messageWidget — and nothing else calls the injector.
    callers = re.findall(r"injectContentScripts\(", sw)
    assert len(callers) == 2, "the injector grew a caller outside messageWidget"
