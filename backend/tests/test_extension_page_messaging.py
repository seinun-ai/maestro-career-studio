"""The caller/page message boundary: the fan-out, and the wire contract.

Task 9 moved the five page functions into `extension/content/agent.js`; phase 2
then moved the profile and open-question engines into shared content modules
without changing how the caller reaches them: `chrome.scripting.executeScript`
targeted every frame in ONE call and handed back an array of per-frame results,
while `chrome.tabs.sendMessage` addresses ONE frame. So the caller enumerates
the frames itself and rebuilds that array.

**WHERE the caller lives has moved three times; what it does has not.** The
first side panel's `callFrame`/`callAllFrames`/`noFrameAnswered` went with that
panel; the floating card that replaced it went at R-C. The fan-out itself is
`broadcastToFrames` in `extension/sw.js` and always was — a caller that runs in
a page cannot hold the `tabs` permission, and an extension page has no tab, so
either way the service worker does it. The "did anybody answer" half is
`reconcileFill().reached` plus the inline `frame.result !== undefined` checks at
the remaining call sites, which now live in `extension/panel/` and
`extension/shared/guided-run.js`. This file follows the BEHAVIOUR rather than
the file, which is why the assertions barely moved while the sources did.

**The fan-out.** Everything downstream of it is unchanged engine-era code —
`frames.flatMap((f) => f.result?.filled ?? [])`, the `frameId -> host` Map, the
attach `reduce`. That code reads `f.result` optionally because a frame that
could not run contributed nothing, so a frame which cannot answer must still
contribute nothing rather than throwing: an ATS page carries ad and analytics
iframes that will never answer, and one of them must not cost the user their
application. The functions are extracted and driven with a fake `chrome`. Only
the recorders are fake — what is under test is which frames get asked, what
comes back, and which failures are swallowed.

**The wire contract**, which no other test can reach. Every engine test calls
`fillFormFromProfile` DIRECTLY with positional arguments, so not one of them
traverses the single line in `PAGE_HANDLERS` that turns a message back into
those four positions. Swapping `msg.profile` and `msg.employment` there writes
one application's values into another's fields and stays green everywhere else.
Same for a typo in a `PAGE_HANDLERS` key or a `type:` string, which kills a
feature silently. These are source assertions rather than behavioural ones, in
the same spirit as the duplicate-copy pins in `test_extension_policy_blocked.py`.

WHAT IS NOT COVERED HERE. Whether `chrome.webNavigation.getAllFrames` and
`chrome.tabs.sendMessage` behave in a real browser the way these fakes do was
NOT executed: the extension is not loaded in any Chrome on this machine. In
particular the promise (no-callback) form of `getAllFrames` is assumed. Settle
it by loading the extension unpacked and clicking Autofill on a Greenhouse
posting, whose form is in a subframe — a fill that reports fields is the whole
chain working end to end.
"""

import re

import pytest

from tests.extension_harness import (
    ROOT,
    js_code,
    page_runtime_source,
    run_node,
)

AGENT_JS = (ROOT / "extension" / "content" / "agent.js").read_text(encoding="utf-8")
AUTOFILL_JS = (ROOT / "extension" / "content" / "autofill.js").read_text(encoding="utf-8")
SW_JS = (ROOT / "extension" / "sw.js").read_text(encoding="utf-8")
# THE CALLER IS THE SIDE PANEL, and since R-C deleted the floating card it is
# the only one. Every file of the panel document is read, not a chosen few: the
# reachability scan below is over CALLERS, and half a caller is a handler that
# reads as dead code because the file naming it was left out of the scan. That
# is not hypothetical — the per-concern split moved `profile_fill` into
# `actions/fill.js` and `fill_answers` into `actions/pause.js`, so a scan of
# `panel.js` alone would now report both as dead.
PANEL_JS = "\n".join(
    path.read_text(encoding="utf-8")
    for path in sorted((ROOT / "extension" / "panel").rglob("*.js")))
# `reconcileFill` lives in the module the panel and the content scripts share.
DECISIONS_JS = (ROOT / "extension" / "shared" / "decisions.js").read_text(encoding="utf-8")
# Round B Task 11: the guided runner is the second caller, and the one that
# took two fan-outs with it — `collect_open_questions` and `guided_write` are
# sent from here, from a module loaded by both worlds. A scan over callers
# that does not read it reports two live page handlers as dead code.
GUIDED_RUN_JS = (ROOT / "extension" / "shared" / "guided-run.js").read_text(encoding="utf-8")

# `sw.js` is not in EXTENSION_SOURCES' job — it never runs in a page — and is
# read here on its own so `extract` can slice the fan-out out of it. decisions.js
# is deliberately NOT here: it is a loadable module, so it is driven with
# `loadModules` in its own run (see `_REACHED_DRIVER_JS`) rather than sliced.
_FANOUT_SOURCE = SW_JS


_PAGE_RUNTIME_DRIVER_JS = r"""
let listener = null;
global.chrome = {
  runtime: {
    id: "maestro-cs-test",
    onMessage: { addListener: (callback) => { listener = callback; } },
  },
};

const ns = loadModules();
const send = (message) => new Promise((resolve, reject) => {
  const keptOpen = listener(
    message,
    { id: chrome.runtime.id },
    (reply) => resolve(reply),
  );
  if (!keptOpen) reject(new Error(`agent declined ${message.type}`));
});

main(async () => {
  const profile = await send({
    type: "profile_fill",
    profile: {},
    employment: [],
    eeoEnabled: false,
    skills: [],
  });
  const questions = await send({ type: "collect_open_questions" });
  const answers = await send({ type: "fill_answers", pairs: [] });
  emit({
    exports: Object.keys(ns).sort(),
    profile,
    questions,
    answers,
  });
});
"""


def test_real_split_modules_dispatch_through_the_agent_message_boundary(tmp_path):
    """Execute production IIFEs in manifest order, including agent.js.

    Direct engine tests do not prove that independently loaded modules share a
    namespace or that PAGE_HANDLERS awaits and envelopes their results. This
    test crosses that exact production boundary without loading widget.js,
    whose job is the caller rather than the page runtime.
    """
    out = run_node(
        _PAGE_RUNTIME_DRIVER_JS,
        {},
        tmp_path,
        source=page_runtime_source(),
    )

    assert out["profile"]["ok"] is True
    assert out["profile"]["data"]["filled"] == []
    assert out["questions"] == {
        "ok": True,
        "data": {
            "questions": [],
            "excluded": [],
            "retryables": [],
            "host": "jobs.example.test",
        },
    }
    assert out["answers"] == {"ok": True, "data": []}
    assert {
        "fillFormFromProfile",
        "collectOpenQuestions",
        "fillAnswersByQid",
        "pageHandlers",
    } <= set(out["exports"])


_FANOUT_DRIVER_JS = r"""
const broadcastToFrames = extract(
  "broadcastToFrames", "\n// ---- end broadcastToFrames ----");
// The reading of agent.js's `{ok, data}` / `{ok: false, error}` envelope moved
// into `unwrapPageReply`, shared with `panel_frame0` so one contract with the
// page has one implementation. The slice reaches it as a free variable, so it
// binds on `global` — see the same note in test_extension_panel.py's fanout
// driver. Worth knowing how this fails if it is ever forgotten: the
// ReferenceError lands INSIDE broadcastToFrames' per-frame catch, so every
// frame reports "unwrapPageReply is not defined" and the fan-out returns
// nothing — loud, but as a wall of frame errors rather than a missing symbol.
global.unwrapPageReply = extract(
  "unwrapPageReply", "\n// ---- end unwrapPageReply ----");
// broadcastToFrames warns on a frame that did not answer. Recorded rather than
// silenced: the warning is the diagnostic that tells three different failures
// apart during a browser check, so it is part of what this file pins.
let warnings = [];
global.console = { ...console, warn: (...args) => warnings.push(args.map(String).join(" ")) };

let addressed = [];
global.chrome = {
  webNavigation: {
    getAllFrames: async ({ tabId }) => (spec.frames === null
      ? null
      : spec.frames.map((f) => ({ frameId: f.frameId, tabId }))),
  },
  tabs: {
    // One reply per frame, declared by the spec. `throws` models a frame with
    // no content script in it (Chrome rejects with "Could not establish
    // connection"); `reply` models one that answered.
    sendMessage: async (tabId, message, options) => {
      addressed.push({ tabId, message, options });
      const frame = spec.frames.find((f) => f.frameId === options.frameId);
      if (frame.throws) throw new Error(frame.throws);
      return frame.reply;
    },
  },
};

main(async () => {
  const frames = await broadcastToFrames(spec.tabId, { type: "profile_fill" });

  // The aggregation the widget actually performs, run here rather than
  // asserted in Python: the point is that THIS expression still works against
  // what broadcastToFrames returns.
  const filled = frames.flatMap((f) => f.result?.filled ?? []);
  const hosts = frames.map((f) => [f.frameId, f.result?.host]);

  // Per-frame, which is what the four failure shapes below are about: one
  // frame's reply becomes either a `result` or an `error`, never both.
  const perFrame = Object.fromEntries(frames.map((f) => [
    f.frameId,
    { data: f.result === undefined ? null : f.result, error: f.error ?? null },
  ]));

  emit({ frames, filled, hosts, perFrame, addressed, warnings });
});
"""

# The widget's half of the pair. `reached` is the successor to the panel's
# `noFrameAnswered`, and it is read off what broadcastToFrames ACTUALLY
# returned — the `frames` the driver above emitted — rather than off a
# hand-written array, which is what keeps the seam between the two files
# honest. A frame that could not answer carries no `result` key at all, and
# JSON drops the key rather than inventing one, so `result === undefined`
# survives the hand-off intact.
_REACHED_DRIVER_JS = r"""
const { reconcileFill } = loadModules().decisions;

main(async () => {
  emit({ reachedNobody: !reconcileFill(spec.frames).reached });
});
"""


def run_fanout(tmp_path, frames, tab_id=7) -> dict:
    out = run_node(
        _FANOUT_DRIVER_JS,
        {"tabId": tab_id, "frames": frames},
        tmp_path,
        source=_FANOUT_SOURCE,
    )
    # `reconcileFill` moved into extension/shared/decisions.js, which is a real
    # loadable module — so it is RUN (`loadModules` evaluates the file, its
    # namespace join and its publication) instead of being sliced out of the
    # text. That needs its own node run: this driver's source is sw.js plus
    # widget.js and neither is executable in this harness.
    out["reachedNobody"] = run_node(
        _REACHED_DRIVER_JS,
        {"frames": out["frames"]},
        tmp_path,
        source=DECISIONS_JS,
    )["reachedNobody"]
    return out


# A Greenhouse-shaped tab: a marketing top frame that matches nothing, the
# application form in a subframe, and an ad iframe with no content script.
_GREENHOUSE = [
    {"frameId": 0, "reply": {"ok": True, "data": {"filled": [], "host": "acme.com"}}},
    {"frameId": 3, "reply": {"ok": True, "data": {
        "filled": [{"label": "First name", "value": "Jordan"}], "host": "boards.greenhouse.io"}}},
    {"frameId": 9, "throws": "Could not establish connection. Receiving end does not exist."},
]


def test_every_frame_of_the_tab_is_asked(tmp_path):
    """`executeScript({allFrames: true})` was one call; this is a loop, and the
    loop has to cover the same set or a subframe form is silently skipped."""
    out = run_fanout(tmp_path, _GREENHOUSE)

    assert [f["frameId"] for f in out["frames"]] == [0, 3, 9]


def test_a_frame_with_no_content_script_is_skipped_not_fatal(tmp_path):
    """The failure this file exists for.

    Under `executeScript` a frame that could not run contributed no result and
    the aggregation moved on. Under messaging that frame REJECTS, and an
    unhandled rejection here would abort the whole fill — so an ad iframe on a
    Greenhouse posting would cost the user the application form beside it.
    """
    out = run_fanout(tmp_path, _GREENHOUSE)

    assert out["frames"][2]["frameId"] == 9
    assert "result" not in out["frames"][2]  # `undefined` drops out of JSON
    assert out["filled"] == [{"label": "First name", "value": "Jordan"}]


def test_a_frame_that_reports_an_error_is_also_skipped(tmp_path):
    """The other half: the frame answered, and what it said was "I failed".
    `{ok: false}` is agent.js's error channel — `sendResponse` has no reject
    path — so it has to be treated the same as an unreachable frame."""
    frames = [
        {"frameId": 0, "reply": {"ok": False, "error": "profile is not an object"}},
        {"frameId": 3, "reply": {"ok": True, "data": {"filled": [{"label": "Email"}]}}},
    ]
    out = run_fanout(tmp_path, frames)

    assert out["frames"][0]["frameId"] == 0
    assert "result" not in out["frames"][0]
    assert out["filled"] == [{"label": "Email"}]


def test_each_frame_is_addressed_by_id_and_not_broadcast(tmp_path):
    """`chrome.tabs.sendMessage` with no `frameId` goes to EVERY frame and
    returns whichever answers first. Filling a form is not idempotent, so a
    broadcast would run the engine an unknown number of times and report one."""
    out = run_fanout(tmp_path, _GREENHOUSE)

    assert [send["options"] for send in out["addressed"]] == [
        {"frameId": 0}, {"frameId": 3}, {"frameId": 9},
    ]
    assert {send["tabId"] for send in out["addressed"]} == {7}


def test_the_frame_id_travels_with_the_result(tmp_path):
    """The AI path tags each question with the frame it was found in and writes
    the answer back to that same frame. A result that lost its frameId would
    send answers to the wrong form."""
    out = run_fanout(tmp_path, _GREENHOUSE)

    assert out["hosts"] == [[0, "acme.com"], [3, "boards.greenhouse.io"], [9, None]]


def test_a_tab_that_no_longer_exists_yields_no_frames(tmp_path):
    """`getAllFrames` resolves null for a tab that has gone away. Reading
    `.map` off that would throw where the old code reported nothing filled."""
    out = run_fanout(tmp_path, None)

    assert out["frames"] == []
    assert out["filled"] == []


# ---------- telling one failure from another ----------


def test_the_reason_a_frame_failed_is_kept_and_logged(tmp_path):
    """Swallowing the failure is right. Discarding the REASON was not.

    Every way this can break — a frame with no content script, a message type
    nothing handles, an engine throw — arrives at the caller as the same empty
    result. Without the reason, diagnosing a failed fill in a browser means
    guessing between three unrelated bugs. It costs one field and one warn.
    """
    out = run_fanout(tmp_path, _GREENHOUSE)

    assert out["frames"][2]["error"] == (
        "Could not establish connection. Receiving end does not exist.")
    assert out["warnings"] == [
        "frame 9 did not answer profile_fill: "
        "Could not establish connection. Receiving end does not exist."
    ]
    # The frames that worked stay clean — an `error` key on every record would
    # make the field useless as a signal.
    assert "error" not in out["frames"][0]


def test_reaching_nobody_is_distinguishable_from_a_page_with_nothing_on_it(tmp_path):
    """The discriminator behind "Can't reach this page".

    `result === undefined` can ONLY mean unreached-or-threw, because every
    handler that actually runs returns a defined value. So a page where every
    frame answered "no fields" is a finding, and a page where nothing answered
    is not — and the panel used to report both as "No matching fields found on
    this page", asserting a fact about a page it had never read.
    """
    out = run_fanout(tmp_path, _GREENHOUSE)
    assert out["reachedNobody"] is False  # frame 9 died, but 0 and 3 answered

    nobody = run_fanout(tmp_path, [
        {"frameId": 0, "throws": "Could not establish connection."},
        {"frameId": 3, "throws": "Could not establish connection."},
    ])
    assert nobody["reachedNobody"] is True


def test_a_page_where_every_frame_answered_nothing_is_still_a_finding(tmp_path):
    """The other direction, and the one that must not regress into a false
    "can't reach": a form the rules genuinely do not cover answers with empty
    lists, and the user is owed "nothing matched" rather than "reload the tab"."""
    out = run_fanout(tmp_path, [
        {"frameId": 0, "reply": {"ok": True, "data": {"filled": []}}},
    ])

    assert out["reachedNobody"] is False


def test_an_empty_frame_list_reaches_nobody(tmp_path):
    """`[].filter(…)` is empty, so the tab-is-gone case and the
    `getAllFrames`-answered-nothing case both land on "can't reach" instead of
    on a confident claim about a page. That is also the honest report if the
    promise form of `getAllFrames` turns out to be wrong."""
    out = run_fanout(tmp_path, None)

    assert out["reachedNobody"] is True


def test_every_consumer_of_the_fan_out_asks_whether_it_reached_anybody():
    """A source rule, because the consumers are click handlers and cannot be
    extracted.

    Each of the reporting ones ends in a sentence about the page — "No matching
    fields found", "No open questions found", "No PDF-accepting file inputs
    found", "N could not be written" — and each is a lie when nothing answered.
    So the rule is: every fan-out call site consults reachedness.

    FIVE consumers, every one reporting. (The applied-detection watcher was
    the sixth, the one that reported nothing; it is retired, and every fan-out
    left ends in a sentence a dead page would make false.)

    `scroll_to_field` is deliberately NOT one of them, and the pattern below
    excludes it by shape rather than by name: it travels inside a
    `page_broadcast` envelope instead of through the `broadcast(...)` door, and
    it is the one fan-out that reports NOTHING — a jump to a control, whose
    failure is a `console.warn` and no sentence to the user. There is nothing
    for it to lie about, so there is no reachedness for it to consult.

    THE SCAN IS OVER CALL SITES, NOT FILES, which is why it reads the whole
    panel document plus the shared runner. The call sites have moved three
    times without the rule changing: out of the first side panel, out of the
    floating card R-C deleted, and across the panel's own per-concern split.
    Naming files here rather than the rule is how this ends up asserting a
    subset of itself, blind to whichever guard moved last.
    """
    # `\s*` spans newlines without re.S, which is what makes one pattern cover
    # both the one-line and the multi-line message literals. Through `js_code`
    # because this counts CODE: a comment naming `!result.reached` next to a
    # call site would otherwise be counted as an extra guard.
    callers = js_code(PANEL_JS + GUIDED_RUN_JS)
    fanned = set(re.findall(r'broadcast\(\{\s*type: "([a-z_]+)"', callers))
    fanned |= set(re.findall(r'ask\("(attach_pdf)"', callers))
    assert fanned == {
        "profile_fill", "collect_open_questions", "fill_answers", "attach_pdf",
        "guided_write",
    }, f"a fan-out consumer was renamed or removed: {sorted(fanned)}"

    # One guard per REPORTING consumer. profile_fill's is `!result.reached` —
    # `reconcileFill` computes it — and the others are written inline at
    # the call site. reconcileFill's own `frame.result !== undefined` lives in
    # decisions.js, which is not in `callers`, so what is counted here is
    # exactly the call sites.
    reported = len(fanned)
    guards = (
        len(re.findall(r"!result\.reached", callers))
        + len(re.findall(r"frame\.result !== undefined", callers))
    )
    # …and the thing `!result.reached` reads still exists, in the module it
    # moved to. Without this the count above would stay satisfied by a
    # `reached` that nobody computes.
    assert len(re.findall(r"frame\.result !== undefined", DECISIONS_JS)) == 1, (
        "reconcileFill no longer decides reachedness from the per-frame array")
    assert guards == reported, (
        f"{reported} reporting fan-out consumers but {guards} reachedness "
        "checks — a fan-out result is being reported as a finding about the "
        "page without asking whether the page was read")


# ---------- the wire contract ----------
#
# Source assertions. The one line that turns a message back into
# `fillFormFromProfile`'s four positional arguments is not reachable from any
# behavioural test in this repo, because every engine test calls that function
# directly.


def _page_handler_keys() -> list[str]:
    block = re.search(r"const PAGE_HANDLERS = \{(.*?)\n  \};", AGENT_JS, re.S)
    assert block, "PAGE_HANDLERS is not where this test expects it in agent.js"
    return re.findall(r"^    ([a-z_]+):", block.group(1), re.M)


def test_every_type_a_caller_sends_is_a_type_the_page_handles():
    """A typo on either side is a feature that is simply dead: `sendMessage`
    resolves, `Object.hasOwn` says no, the listener returns false, and the
    caller sees "no reply from the page" with nothing naming the cause.

    Both lists, not a subset check in one direction — a handler with no sender
    is dead code and a sender with no handler is a dead button.

    EVERY HANDLER TRAVELS AS A MESSAGE NOW, which is new at R-C and is the
    reason this test lost a whole half. `ns.pageHandlers.X()` used to be a
    second route: the floating card ran in the top document, so it called
    `extract_job_posting` directly rather than sending it anywhere, and a scan
    for `type:` strings alone reported that handler as dead code while it was
    the whole of the Save Job button. The card is gone and the panel runs in no
    page at all, so it reaches the same handler through `panel_frame0` like
    everything else — one route, and the in-frame-call scan has nothing left to
    find. Kept as an assertion rather than deleted: `called` being EMPTY is now
    the claim, and a new in-page caller should have to come and change it.

    The scan reads every caller: both the panel's files and
    `shared/guided-run.js`, which is where two of these messages are sent from.
    A typo in any `type:` string is a feature that is silently dead.
    """
    sent = set(re.findall(
        r'\btype:\s*"([a-z_]+)"', SW_JS + PANEL_JS + GUIDED_RUN_JS))
    called = set(re.findall(r"ns\.pageHandlers\.([a-z_]+)\(", PANEL_JS + GUIDED_RUN_JS))
    handled = set(_page_handler_keys())

    reachable = sent | called
    assert reachable & handled == handled, (
        f"page handlers nobody reaches: {sorted(handled - reachable)}")
    assert handled == {
        "extract_job_posting", "detect_page", "profile_fill",
        "collect_open_questions", "fill_answers", "guided_write",
        "attach_resume_pdf",
        # R-B Task 12. The panel's residue rows are jumps, and the panel runs in
        # no page — so the scroll is a message, fanned out because the control
        # can be in the application's subframe.
        "scroll_to_field",
    }
    assert called == set(), (
        "something calls a page handler in-frame again — see this test's "
        f"docstring before widening the roster: {sorted(called)}")


def test_the_profile_fill_arguments_keep_their_identity_across_the_wire():
    """The dangerous one.

    `fillFormFromProfile(profile, employment, eeoEnabled, skills)` is positional
    and the message is keyed, so exactly one line converts between them. Swap
    `msg.profile` and `msg.employment` there and the engine writes a resume's
    employment history into the profile's fields — into a live application, on
    a real ATS — while every engine test stays green, because every one of
    them calls the function directly.

    Checked in both directions: the sender writes keys named after the
    parameters, and the handler reads them back in the declared order. The
    sender is `panel/actions/fill.js` — the rule pass's own fan-out, which is
    where the message literal landed when R-C deleted the card's copy of it.
    """
    declared = re.search(r"async function fillFormFromProfile\(([^)]*)\)", AUTOFILL_JS)
    assert declared, "fillFormFromProfile's signature is not where this test expects it"
    params = [p.split("=")[0].strip() for p in declared.group(1).split(",")]
    # `consentForms` joined the tail in the consent round. Appending rather
    # than inserting is not a style choice: every existing caller passes four
    # positional arguments, and a new parameter anywhere but the end would
    # silently re-bind theirs.
    assert params == ["profile", "employment", "eeoEnabled", "skills", "consentForms"]

    # Anchored on the CALL rather than on the handler's arrow form: the handler
    # became a conditional when the frame gate landed (2026-08-04), and this
    # test is about argument order, not about the shape of the wrapper around
    # it. `ns.fillFormFromProfile(` appears exactly once in agent.js.
    assert AGENT_JS.count("ns.fillFormFromProfile(") == 1
    call = re.search(r"ns\.fillFormFromProfile\(([^)]*)\)", AGENT_JS, re.S)
    assert call, "the profile_fill handler is not where this test expects it"
    passed = [re.search(r"msg\.(\w+)", arg).group(1) for arg in call.group(1).split(",")]
    assert passed == params, (
        f"the handler passes {passed} into a signature declaring {params} — "
        "a swap here writes one field's value into another's")

    fill_js = (ROOT / "extension" / "panel" / "actions" / "fill.js").read_text(
        encoding="utf-8")
    literal = re.search(r'type: "profile_fill",(.*?)\n    \}\);', fill_js, re.S)
    assert literal, "the profile_fill message literal is not where this test expects it"
    assert re.findall(r"^      (\w+):", literal.group(1), re.M) == params


def test_the_listener_keeps_the_channel_open():
    """`return true` is what lets the async `sendResponse` below it be
    delivered at all. Returning false closes the port immediately, so every
    handler runs to completion in the page and every answer is thrown away —
    the caller sees "no reply from the page" and the fill silently does nothing
    it can report. Nothing else in this repo would notice."""
    listener = re.search(
        r"chrome\.runtime\.onMessage\.addListener\(\(msg, sender, sendResponse\) => \{"
        r"(.*?)\n  \}\);", AGENT_JS, re.S)
    assert listener, "agent.js's onMessage listener is not where this test expects it"

    assert listener.group(1).rstrip().endswith("return true;")


@pytest.mark.parametrize(
    "frame, expected",
    [
        ({"frameId": 0, "reply": {"ok": True, "data": ["q1"]}},
         {"data": ["q1"], "error": None}),
        ({"frameId": 0, "reply": {"ok": False, "error": "no such field"}},
         {"data": None, "error": "no such field"}),
        ({"frameId": 0, "throws": "Could not establish connection."},
         {"data": None, "error": "Could not establish connection."}),
        # A listener that returned without answering: Chrome resolves undefined.
        ({"frameId": 0, "reply": None},
         {"data": None, "error": "no reply from the page"}),
    ],
    ids=["ok", "handler-error", "unreachable", "no-reply"],
)
def test_one_frame_reports_either_a_result_or_a_reason(tmp_path, frame, expected):
    """The four shapes a single frame's reply can take, and the rule that they
    never overlap: a frame contributes a `result` or an `error`, never both and
    never neither.

    The panel had a second, STRICTER entry point for this — `callFrame`, which
    threw — and the AI write-back path used it directly on the grounds that a
    qid tagged in that frame moments earlier makes a silent frame a real
    failure. The widget has no such call: `fill_answers` broadcasts and then
    reads `reachedFrames` back out of the array, so the same four shapes have
    to be legible HERE, per frame, or a lost frame becomes an answer nobody
    wrote and nobody counted.
    """
    out = run_fanout(tmp_path, [frame])

    assert out["perFrame"]["0"] == expected
