"""The widget's shell contract, and the one piece of it that is pure logic.

`extension/content/widget.js` is a UI. Most of it — a shadow root, the top
layer, an IntersectionObserver, a pointer drag — cannot be exercised from
Python, and faking a DOM detailed enough to try would only test the fake. So
this file tests two things that are real, and says plainly what it is not
covering.

**1. The shell's non-negotiables, as source assertions.** Design §3.3 is a list
of defenses, each written because of a documented failure, and each one is a
single line that a later refactor deletes without breaking anything visible.
The seven inline-`!important` properties are the clearest case: drop
`display` and the widget still works on every page except the ones with a
`div { display: none !important }` rule, which are exactly the pages nobody
tests on. Source assertions are what a text search can honestly claim, and they
are in the same spirit as the duplicate-copy pins in
`test_extension_policy_blocked.py`.

**2. The three decisions, executed.** `chooseEvasion` is pure geometry —
rectangles in, a corner out — and it is the whole of Task 12's judgement.
`resolvePrimary` and `reconcileFill` are the whole of the expanded card's:
which dot, which single primary button, which nudge, and what the
reconciliation strip's four numbers mean. All three are tables, all three run
in node, and a table is what a later feature edits one row of without reading
the rest.

WHAT WAS EXECUTED IN A BROWSER, and what was not. The content scripts were loaded
into a real page (`extension/dev/preview.html`, served over localhost) and
driven. Confirmed there, not here:

* the cross-file namespace populates and `widget.js` reads it;
* an UNREGISTERED custom-element name takes a closed shadow root, the page sees
  `host.shadowRoot === null`, and `showPopover()` puts it in the top layer
  (`:popover-open` matched);
* a page rule `html > :not(head):not(body) { display: none !important }` does
  NOT hide it — computed `display` stayed `block`;
* the full-viewport host is pointer-transparent (`elementFromPoint` at the
  centre returns the page's own element) and opaque over the bubble;
* clicking the bubble opens the card and the page's document-level bubble-phase
  `pointerdown` listener counts 0 — while a capture-phase one counts 1 and sees
  only the host's random tag name.

NOT executed anywhere, and the exact check that would settle each:

* **Does an isolated world share one `window` across the files in a
  `content_scripts.js` array?** The preview page runs them in the PAGE's world,
  where they demonstrably share one. That is the weaker environment, so it
  cannot prove the isolated case. Settle it by loading unpacked and evaluating
  `window.careerStudioCompanion` from the content-script context.
* **Does the collision observer ever fire on a real ATS?** Not exercised:
  IntersectionObserver delivers nothing to a hidden tab, and the automated
  browser here reports `document.hidden === true`. Open preview.html as the
  front tab and scroll the submit bar into view, or load unpacked on a Workday
  step.
* **Does `chrome.action.onClicked` fire while `setPanelBehavior({
  openPanelOnActionClick: true })` is set?** If it does not, the toolbar route
  to un-dismissal is dead until Task 19 deletes the side panel, and the hotkey
  is the only one. See the comment at that listener in `extension/sw.js`.
* **Does `chrome.webNavigation.getAllFrames` reach the application subframe on
  a real Greenhouse or Lever posting?** `broadcastToFrames` (`sw.js`) is the
  card's whole route to the engine, and it has never run in a browser. The
  preview page answers its messages with a stub, which exercises the CARD's
  aggregation and nothing about the fan-out. Settle it by loading unpacked on
  an embedded Greenhouse form and filling.
"""

import json
import re

import pytest

from tests.extension_harness import ROOT, run_node

EXTENSION = ROOT / "extension"
WIDGET_JS = (EXTENSION / "content" / "widget.js").read_text(encoding="utf-8")
DETECT_JS = (EXTENSION / "content" / "detect.js").read_text(encoding="utf-8")
AGENT_JS = (EXTENSION / "content" / "agent.js").read_text(encoding="utf-8")
SW_JS = (EXTENSION / "sw.js").read_text(encoding="utf-8")
MANIFEST = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))


# ---------- the namespace, which replaces an assumption ----------


def test_every_content_script_publishes_onto_one_namespace():
    """The assumption this removes: that a top-level `function detectPage` in
    one file is reachable by name from the next.

    Chrome documents that a `content_scripts.js` array injects in order into one
    isolated world. It does not document that top-level declarations cross the
    files, and nobody here has been able to check — a branded Chrome refuses
    `--load-extension`. An explicit property on the isolated world's `window` is
    correct under both readings, so it is what every content script uses.
    """
    module_paths = [
        "job-posting.js", "policy.js", "eeo.js", "autofill.js",
        "open-questions.js",
    ]
    modules = {
        name: (EXTENSION / "content" / name).read_text(encoding="utf-8")
        for name in module_paths
        if (EXTENSION / "content" / name).is_file()
    }
    assert set(modules) == set(module_paths), (
        f"split content modules missing: {sorted(set(module_paths) - set(modules))}")

    for name, source in [*modules.items(), ("detect.js", DETECT_JS),
                         ("agent.js", AGENT_JS), ("widget.js", WIDGET_JS)]:
        assert "window.careerStudioCompanion ??= {}" in source, (
            f"{name} does not join the namespace; the widget reads it by name "
            "and fails loudly when it is empty")

    assert "ns.findJobPostingInDocument = findJobPostingInDocument;" in modules["job-posting.js"]
    assert "ns.isPolicyBlocked = isPolicyBlocked;" in modules["policy.js"]
    assert "ns.createEeoContext = createEeoContext;" in modules["eeo.js"]
    assert "ns.handleEeoControl = handleEeoControl;" in modules["eeo.js"]
    assert "ns.fillFormFromProfile = fillFormFromProfile;" in modules["autofill.js"]
    assert "ns.collectOpenQuestions = collectOpenQuestions;" in modules["open-questions.js"]
    assert "ns.fillAnswersByQid = fillAnswersByQid;" in modules["open-questions.js"]
    assert "ns.detectPage = detectPage;" in DETECT_JS
    assert "ns.pageHandlers = PAGE_HANDLERS;" in AGENT_JS


def test_eeo_module_owns_protected_class_control_orchestration():
    """The EEO split includes DOM decisions, not only a rule-data builder."""
    eeo = (EXTENSION / "content" / "eeo.js").read_text(encoding="utf-8")
    autofill = (EXTENSION / "content" / "autofill.js").read_text(encoding="utf-8")

    assert "async function handleEeoControl(" in eeo
    assert "await ns.handleEeoControl({" in autofill
    assert "if (isEeoField && input.value)" not in autofill
    assert "const option = isEeoField ? eeoOptionFor" not in autofill


def test_nothing_is_declared_at_the_top_level_of_a_publish_block():
    """The failure mode that makes the IIFEs load-bearing rather than tidy.

    IF the files do share top-level scope, then a second file declaring the same
    `const` is a redeclaration SyntaxError — which does not degrade, it kills
    the whole script. So the publish blocks declare nothing outside a function,
    and `widget.js` wraps its entire body.
    """
    module_paths = [
        "job-posting.js", "policy.js", "eeo.js", "autofill.js",
        "open-questions.js",
    ]
    modules = {
        name: (EXTENSION / "content" / name).read_text(encoding="utf-8")
        for name in module_paths
        if (EXTENSION / "content" / name).is_file()
    }
    assert set(modules) == set(module_paths), (
        f"split content modules missing: {sorted(set(module_paths) - set(modules))}")

    for name, source in [*modules.items(), ("detect.js", DETECT_JS),
                         ("agent.js", AGENT_JS)]:
        publish = source.split("WHAT THIS FILE PUBLISHES")[-1]
        assert "(() => {" in publish and source.rstrip().endswith("})();"), (
            f"{name}'s publish block is not an IIFE")
        assert not re.search(r"^(const|let|class)\s", publish, re.M), (
            f"{name} declares a top-level binding beside its publish block")

    body = WIDGET_JS.split("*/", 1)[1]
    assert body.lstrip().startswith("(() => {"), (
        "widget.js must be one IIFE: it has ~40 bindings and any of them could "
        "collide with agent.js's if the files share scope")


def test_the_widget_fails_loudly_when_the_namespace_is_empty():
    """A build where a file did not inject is otherwise INVISIBLE: the widget
    simply never appears, which is also what a page scoring 0 looks like.

    Loud in the console always; loud on screen only when the user explicitly
    asked for the widget. A banner on page load would put an error box on every
    page on the web — design §5's negative rule, inverted.
    """
    assert "console.error(" in WIDGET_JS
    assert "function mountFailure(" in WIDGET_JS
    # The visible half hangs off the two request paths, never off `autoMount()`.
    request_paths = re.search(
        r'msg\?\.type === "widget_toggle" \|\| msg\?\.type === "widget_show"(.*?)\n  \}\);',
        WIDGET_JS, re.S)
    assert request_paths, "the widget's message listener is not where this test expects it"
    assert "mountFailure(missing)" in request_paths.group(1)


# ---------- design §3.3, the shell ----------


def test_the_seven_inline_important_properties_are_all_there():
    """Design §3.3's list, and the reason it is a list.

    Inline-`!important` is the top of the author cascade, so it is what beats a
    page's `div { display: none !important }`. Drop `display` and the widget
    still works everywhere except on the pages that rule exists on; drop
    `pointer-events` and a viewport-sized transparent host swallows every click
    on the page underneath.
    """
    block = re.search(r"const HOST_INLINE = \{(.*?)\n  \};", WIDGET_JS, re.S)
    assert block, "HOST_INLINE is not where this test expects it"
    declared = set(re.findall(r'^\s{4}"?([a-z-]+)"?:', block.group(1), re.M))

    assert declared == {
        "position", "z-index", "display", "visibility",
        "opacity", "pointer-events", "contain",
    }
    # Set as a list, and set with priority: `host.style.display = "block"` is
    # inline but NOT important, and loses to the page's `!important` rule.
    assert 'host.style.setProperty(name, value, "important")' in WIDGET_JS


@pytest.mark.parametrize(
    "fragment, why",
    [
        ('attachShadow({ mode: "closed" })',
         "an open root is the documented DOM-clickjacking vector, and closed "
         "also strips our internals out of composedPath()"),
        ("document.documentElement.appendChild(host)",
         "under <body>, an ancestor with transform/filter/contain becomes the "
         "containing block for position:fixed and Workday-class shells do that"),
        ('setAttribute("popover", "manual")',
         "an `auto` popover light-dismisses, so the widget would vanish on the "
         "user's first click anywhere on the page"),
        ("all: initial;",
         "nothing inherits in from the page, and it also wipes what the UA's "
         "own [popover] rule would impose"),
        ("adoptedStyleSheets",
         "everything except the seven inline properties lives in one sheet"),
        ("@media (forced-colors: active)",
         "box-shadow is forced to none there, so a shadow-only widget is "
         "invisible; it needs a real border"),
        ("@media (prefers-reduced-motion: reduce)",
         "design §3.3"),
        ("if (window.top !== window.self) return;",
         "the engine runs in every frame, the UI in exactly one — otherwise a "
         "Greenhouse application iframe grows its own bubble"),
    ],
)
def test_the_shell_keeps_its_defenses(fragment, why):
    assert fragment in WIDGET_JS, why


def test_the_six_pointer_events_are_shielded_at_the_host():
    """UA-dispatched UI events are `composed`: they cross the shadow boundary
    and keep going up into the page, which is how an injected widget closes a
    page's own dialog just by being clicked.

    The phase is BUBBLE, and that is a correction to design §3.3's wording made
    by measuring it in a browser: a capture-phase `stopPropagation` at the host
    is reached BEFORE the control inside it, so it makes every button in this
    widget dead (inner listener fired 0 times; bubble-phase, 1 time). Asserted
    here because "capture" reads more defensive and someone will change it back.
    """
    block = re.search(r"const SHIELDED_EVENTS = \[(.*?)\n  \];", WIDGET_JS, re.S)
    assert block
    assert set(re.findall(r'"(\w+)"', block.group(1))) == {
        "pointerdown", "mousedown", "pointerup", "mouseup", "click", "touchstart",
    }

    listener = re.search(
        r"for \(const type of SHIELDED_EVENTS\) \{\n\s*host\.addEventListener\("
        r"type, \(event\) => event\.stopPropagation\(\)\);", WIDGET_JS)
    assert listener, "the shield is not one bubble-phase listener per event at the host"


def test_the_widget_never_auto_expands():
    """Design §4.1's loudest rule: detection changes the dot and nothing else.

    A competitor's auto-expanding panel is the single most-upvoted complaint in
    the research corpus. `autoMount()` therefore ends at `mount()`, and `mount()`
    contains no expansion — the only `setExpanded(true)` sites are a click, a
    keyboard activation, and the toolbar action, which are all a user asking.
    """
    mount = re.search(r"async function mount\(\) \{(.*?)\n  \}", WIDGET_JS, re.S)
    assert mount, "mount() is not where this test expects it"
    assert "setExpanded" not in mount.group(1)

    auto = re.search(r"async function autoMount\(\) \{(.*?)\n  \}", WIDGET_JS, re.S)
    assert auto, "autoMount() is not where this test expects it"
    assert "setExpanded" not in auto.group(1)
    # And the gate still comes first: a page that scored nothing gets no widget,
    # no observer and no storage read (design §5's negative rule).
    assert 'if (verdict.tier === "none") return;' in auto.group(1)
    assert auto.group(1).index("ns.detectPage()") < auto.group(1).index("readStore()")


def test_no_content_script_reaches_the_page_world():
    """`world: "ISOLATED"` is what keeps the page out of the fill engine, and
    the widget must not undo it by handing the page a reference.

    Nothing here writes to `document`'s global, dispatches into the page, or
    injects a `<script>`; the namespace lives on the isolated world's own
    `window`, which the page has a different copy of.
    """
    for banned in ("document.defaultView", "createElement(\"script\")", "eval("):
        assert banned not in WIDGET_JS


# ---------- dismissal (Task 13) ----------


def test_all_three_dismissal_levels_exist_and_only_two_are_persisted():
    """Design §4.1's three levels.

    Level 1 is the X, and it is deliberately NOT in storage: it means "this
    page", a page does not outlive its content script, and a key written against
    the URL would resurrect a collapse on a page the user reloaded on purpose.
    It is also the default — this widget never auto-expands.
    """
    assert re.search(r'if \(act === "close"\) \{ setExpanded\(false\)', WIDGET_JS)  # 1
    assert "async function hideHere()" in WIDGET_JS  # 2
    assert "async function toggleGlobally()" in WIDGET_JS  # 3

    keys = re.search(r"const KEY = \{(.*?)\n  \};", WIDGET_JS, re.S)
    stored = set(re.findall(r"^\s{4}(\w+):", keys.group(1), re.M))
    # Enumerated rather than asserted as a whole set: this file's storage is
    # not only dismissal state (`session` remembers which application the card
    # is armed with), and a whole-set assertion made every future key look like
    # a dismissal bug. What must stay true is the property the docstring
    # states — the two persisted dismissals are levels 2 and 3, and level 1 is
    # not among them.
    assert {"hiddenOrigins", "hiddenGlobally"} <= stored
    assert not {key for key in stored if re.search(r"expand|collaps|open", key, re.I)}, (
        "level 1 got written down: a persisted expand/collapse state resurrects "
        "a collapse on a page the user reloaded on purpose"
    )


def test_un_dismissal_is_reachable_and_the_hotkey_is_not_hard_coded():
    """"Without it we ship the Jobscan failure — a message referring to a
    control that does not exist" (design §4.1).

    Two routes, and the copy names the CURRENT binding rather than the manifest's
    suggestion: the user can rebind at chrome://extensions/shortcuts, and Chrome
    silently drops a suggested key another extension already claimed.
    """
    assert MANIFEST["commands"]["toggle-widget"]["suggested_key"]["default"]
    assert 'command === TOGGLE_COMMAND) messageWidget(tab?.id, "widget_toggle")' in SW_JS
    assert 'chrome.action.onClicked.addListener' in SW_JS
    assert "chrome.commands.getAll()" in SW_JS

    # The suggested key is never printed as fact.
    assert "Alt+Shift+J" not in WIDGET_JS
    assert "chrome://extensions/shortcuts" in WIDGET_JS


def test_the_toggles_on_direction_always_produces_a_widget():
    """A toggle whose ON direction can leave the screen unchanged is the failure
    above wearing a different hat.

    So turning it on clears the global flag AND does not consult the per-origin
    hide: `mount()` is unconditional, and `autoMount()` is the only place the stored
    hides are read.
    """
    toggle = re.search(r"async function toggleGlobally\(\) \{(.*?)\n  \}", WIDGET_JS, re.S)
    assert toggle
    assert "[KEY.hiddenGlobally]: false" in toggle.group(1)
    assert "await mount();" in toggle.group(1)

    reads = re.findall(r"KEY\.hiddenOrigins\]\?\.\[location\.origin\]", WIDGET_JS)
    assert len(reads) == 1, (
        "the per-origin hide is consulted somewhere other than autoMount() — the "
        "explicit-request path must not gate on it")


def test_the_two_ways_in_are_named_after_the_path_they_take():
    """A reviewer driving the preview page read "Remount" bringing the widget
    back on a hidden origin as the persistence guard failing, and went to the
    source to file a bug. It is not one — that button takes the EXPLICIT path,
    which is the same one the toolbar action takes and must not gate.

    The near miss is the point: the next reader "fixes" `mount()` to consult
    the stored hides, and un-dismissal silently stops working on exactly the
    origin where it is needed. So the two entries are named after the path they
    take and exposed side by side, and only the gated one runs by itself.
    """
    assert "async function autoMount()" in WIDGET_JS

    exported = re.search(r"ns\.widget = \{(.*?)\n  \};", WIDGET_JS, re.S)
    assert exported
    assert re.search(r"^\s{4}autoMount,$", exported.group(1), re.M)
    assert re.search(r"^\s{4}mount,$", exported.group(1), re.M)

    # Called once, at the bottom of the file, with no user gesture behind it.
    assert WIDGET_JS.count("\n  autoMount();\n") == 1


# ---------- the collision decision, executed ----------

_EVASION_DRIVER_JS = r"""
const clampOffset = extract("clampOffset", "\n  // ---- end clampOffset ----");
const chooseEvasion = extract("chooseEvasion", "\n  // ---- end chooseEvasion ----");

main(async () => {
  const clamped = {};
  for (const [name, args] of Object.entries(spec.clamps)) {
    clamped[name] = clampOffset(args.offset, args.viewportHeight, args.size, args.margin);
  }

  const decided = {};
  for (const [name, scenario] of Object.entries(spec.scenarios)) {
    decided[name] = chooseEvasion({
      dock: scenario.dock,
      viewport: spec.viewport,
      targets: scenario.targets,
      size: spec.size,
      margin: spec.margin,
      gap: spec.gap,
    });
  }

  // The hazard, demonstrated rather than asserted: ask again as if the widget's
  // CURRENT corner were the input — which is what a version measuring
  // getBoundingClientRect() would be doing — and watch the answer flip.
  const fedBack = {};
  for (const [name, scenario] of Object.entries(spec.scenarios)) {
    const moved = {
      side: decided[name].evadeSide ?? scenario.dock.side,
      offset: scenario.dock.offset,
    };
    fedBack[name] = {
      movedTo: moved.side,
      again: chooseEvasion({
        dock: moved, viewport: spec.viewport, targets: scenario.targets,
        size: spec.size, margin: spec.margin, gap: spec.gap,
      }),
    };
  }

  emit({ clamped, decided, fedBack });
});
"""

VIEWPORT = {"width": 1280, "height": 800}
SIZE = 44
MARGIN = 16
GAP = 24

# The bubble's home corner at offset 16 in that viewport: left 1220, right 1264,
# top 740, bottom 784.
_BOTTOM_RIGHT_SUBMIT = {"left": 1050, "right": 1250, "top": 730, "bottom": 780,
                        "width": 200, "height": 50}
_FULL_WIDTH_BAR = {"left": 0, "right": 1280, "top": 730, "bottom": 790,
                   "width": 1280, "height": 60}
_BOTTOM_LEFT_SUBMIT = {"left": 0, "right": 220, "top": 730, "bottom": 780,
                       "width": 220, "height": 50}
_ABOVE_THE_FOLD = {"left": 1050, "right": 1250, "top": 40, "bottom": 90,
                   "width": 200, "height": 50}
# Present in the DOM, zero area: a collapsed wizard step or a template node.
_HIDDEN_SUBMIT = {"left": 0, "right": 0, "top": 0, "bottom": 0, "width": 0, "height": 0}
HOME = {"side": "right", "offset": MARGIN}


@pytest.fixture(scope="module")
def evasion(tmp_path_factory) -> dict:
    return run_node(
        _EVASION_DRIVER_JS,
        {
            "viewport": VIEWPORT,
            "size": SIZE,
            "margin": MARGIN,
            "gap": GAP,
            "clamps": {
                "inRange": {"offset": 300, "viewportHeight": 800, "size": SIZE, "margin": MARGIN},
                # The case design §4.1 names: saved on a tall window, restored on
                # a short one.
                "tallWindowOffsetOnShortWindow": {
                    "offset": 900, "viewportHeight": 500, "size": SIZE, "margin": MARGIN},
                "negative": {"offset": -40, "viewportHeight": 800, "size": SIZE, "margin": MARGIN},
                # Shorter than the bubble plus both margins: the ceiling would
                # fall below the floor and pin the widget off-screen.
                "absurdlyShortWindow": {
                    "offset": 300, "viewportHeight": 50, "size": SIZE, "margin": MARGIN},
                "fractional": {
                    "offset": 120.6, "viewportHeight": 800, "size": SIZE, "margin": MARGIN},
            },
            "scenarios": {
                "clear": {"dock": HOME, "targets": []},
                "aboveTheFold": {"dock": HOME, "targets": [_ABOVE_THE_FOLD]},
                "saveAndContinue": {"dock": HOME, "targets": [_BOTTOM_RIGHT_SUBMIT]},
                "fullWidthBar": {"dock": HOME, "targets": [_FULL_WIDTH_BAR]},
                "bothCorners": {
                    "dock": HOME, "targets": [_BOTTOM_RIGHT_SUBMIT, _BOTTOM_LEFT_SUBMIT]},
                # The user dragged to the left corner; the blocked corner is now
                # the left one and the hop goes the other way.
                "dockedLeftBlocked": {
                    "dock": {"side": "left", "offset": MARGIN}, "targets": [_BOTTOM_LEFT_SUBMIT]},
                "hiddenControl": {"dock": HOME, "targets": [_HIDDEN_SUBMIT]},
                # 24px is the design's number; 25px away is not a collision.
                "justOutsideTheGap": {
                    "dock": HOME,
                    "targets": [{"left": 1050, "right": 1195, "top": 730, "bottom": 780,
                                 "width": 145, "height": 50}],
                },
            },
        },
        tmp_path_factory.mktemp("evasion"),
        source=WIDGET_JS,
    )


def test_a_clear_corner_is_left_alone(evasion):
    """The common case, and the one that must not cost anything: no submit
    control near the bubble means no hop, no collapse, no movement."""
    assert evasion["decided"]["clear"] == {"homeBlocked": False, "evadeSide": None}
    assert evasion["decided"]["aboveTheFold"] == {"homeBlocked": False, "evadeSide": None}


def test_the_workday_case_hops_to_the_other_corner(evasion):
    """*"On workday I have to press x to close it since it covers the save and
    continue buttons"* — the most damning quote in the research corpus, and the
    reason Task 12 exists. A user dismissing the tool in order to finish the
    application it exists to help with."""
    assert evasion["decided"]["saveAndContinue"] == {"homeBlocked": True, "evadeSide": "left"}
    assert evasion["decided"]["dockedLeftBlocked"] == {"homeBlocked": True, "evadeSide": "right"}


def test_a_bar_across_the_whole_width_reports_nowhere_to_go(evasion):
    """Both corners blocked. The answer is not "hop anyway" — it is
    `evadeSide: null` with `homeBlocked: true`, which is what makes the caller
    collapse the card and stay put instead of shuffling sideways into the same
    problem. Workday's own bottom-navigation bar is this shape."""
    assert evasion["decided"]["fullWidthBar"] == {"homeBlocked": True, "evadeSide": None}
    assert evasion["decided"]["bothCorners"] == {"homeBlocked": True, "evadeSide": None}


def test_a_zero_area_control_is_not_in_the_way(evasion):
    """`display:none`, a collapsed wizard step, a template node. It matches the
    selector, it is in the DOM, and it covers nothing — hopping for it would
    move the widget for a control the user cannot see."""
    assert evasion["decided"]["hiddenControl"] == {"homeBlocked": False, "evadeSide": None}


def test_the_gap_is_a_gap_and_not_an_overlap_test(evasion):
    """Design §4.1 says "within ~24px", not "overlapping". A submit button 25px
    from the bubble is not a collision; the same button 24px away is. Touching
    is too late: the user is aiming at it."""
    assert evasion["decided"]["justOutsideTheGap"]["homeBlocked"] is False
    # The same rectangle, extended so its right edge lands 24px from the bubble.
    assert evasion["decided"]["saveAndContinue"]["homeBlocked"] is True


def test_the_decision_is_taken_from_the_saved_corner_not_the_current_one(evasion):
    """The bug this function's SHAPE exists to prevent, demonstrated.

    `fedBack` re-asks the question as if the widget's CURRENT corner were the
    input — which is what any version measuring `getBoundingClientRect()` would
    be doing — and the answer flips: having moved out of the blocked corner, the
    blocked corner looks clear. Feed that back and the widget evades, returns,
    evades, returns, once per animation frame.

    Which is why the caller passes `dock`, the SAVED corner, and never
    `collision.evadeSide` or a live rect. The decision is then a function of the
    page alone and gives the same answer every frame.
    """
    flipped = evasion["fedBack"]["saveAndContinue"]
    assert flipped["movedTo"] == "left"
    assert flipped["again"]["homeBlocked"] is False, (
        "the hazard is no longer real, so this test no longer demonstrates "
        "anything — check whether the geometry changed")

    call = re.search(
        r"= chooseEvasion\(\{(.*?)\n    \}\);", WIDGET_JS, re.S)
    assert call, "evaluateCollision's chooseEvasion call is not where this test expects it"
    assert "dock: { side: dock.side, offset: clamp(dock.offset) }" in call.group(1), (
        "the collision decision is being fed the widget's current position; it "
        "must be fed the saved dock, or it oscillates")
    assert "evadeSide" not in call.group(1)


def test_a_saved_offset_is_re_clamped_for_this_window(evasion):
    """Design §4.1: persist a dock side plus an offset, never absolute x/y, and
    re-clamp on every mount — because the next page loads at a different zoom
    and window size than the one the offset was saved at."""
    clamped = evasion["clamped"]
    assert clamped["inRange"] == 300
    # 900px up a 500px-tall window: without the clamp the widget is above the
    # top of the screen and unreachable.
    assert clamped["tallWindowOffsetOnShortWindow"] == 500 - SIZE - MARGIN
    assert clamped["negative"] == MARGIN
    # Floor wins over a ceiling that fell below it, so the widget stays on
    # screen rather than being pinned off the top of a tiny window.
    assert clamped["absurdlyShortWindow"] == MARGIN
    # Integers: a fractional px offset re-rendered every mount drifts.
    assert clamped["fractional"] == 121


# ---------- the card's two decisions, executed ----------
#
# Everything else in the expanded card is layout, and layout is what a source
# assertion can honestly claim. These two are judgement, they are both tables,
# and a table is what a later feature edits one row of without reading the rest.

_CARD_DRIVER_JS = r"""
const resolvePrimary = extract("resolvePrimary", "\n  // ---- end resolvePrimary ----");
const reconcileFill = extract("reconcileFill", "\n  // ---- end reconcileFill ----");
const restorableSession = extract("restorableSession", "\n  // ---- end restorableSession ----");
const rankBaseResumes = extract("rankBaseResumes", "\n  // ---- end rankBaseResumes ----");

main(async () => {
  const resolved = {};
  for (const [name, facts] of Object.entries(spec.facts)) {
    resolved[name] = resolvePrimary(facts);
  }
  const reconciled = {};
  for (const [name, frames] of Object.entries(spec.fills)) {
    reconciled[name] = reconcileFill(frames);
  }
  const restored = {};
  for (const [name, args] of Object.entries(spec.sessions ?? {})) {
    restored[name] = restorableSession(args.entry, args.context);
  }
  const ranked = {};
  for (const [name, args] of Object.entries(spec.rankings ?? {})) {
    ranked[name] = rankBaseResumes(args.resumes, args.scores);
  }
  emit({ resolved, reconciled, restored, ranked });
});
"""

# A tracked job whose application has a rendered PDF: design §4.1's green.
_READY = {"match": "exact", "hasApplication": True, "pdfReady": True,
          "status": "draft", "touched": False}


# The library's own order, which is what the dropdown used to show.
_RESUMES = [
    {"slug": "data_engineer", "display_name": "Data Engineer"},
    {"slug": "data_scientist", "display_name": "Data Scientist"},
    {"slug": "business_analyst", "display_name": "Business Analyst"},
]


def _score(slug, composite):
    return {"target_type": "base_resume", "target_id": slug,
            "phase": "base", "composite": composite}


# One remembered pick, as `rememberSession` writes it.
_SESSION = {
    "origin": "https://acme.wd5.example",
    "at": 10_000_000,
    "applicationId": "app-1",
    "status": "draft",
    "jobId": "job-1",
    "company": "Acme",
    "title": "Data Scientist",
    "pdfReady": True,
    "touched": True,
}


def _observation(outcome, label="a field"):
    return {"label": label, "kind": "text", "outcome": outcome}


@pytest.fixture(scope="module")
def card(tmp_path_factory) -> dict:
    return run_node(
        _CARD_DRIVER_JS,
        {
            "facts": {
                # Nothing asked yet, or the backend could not be reached.
                "unknown": {"match": None, "hasApplication": False, "pdfReady": False,
                            "status": None, "touched": False},
                "notTracked": {"match": "none", "hasApplication": False,
                               "pdfReady": False, "status": None, "touched": False},
                "trackedNoApplication": {"match": "exact", "hasApplication": False,
                                         "pdfReady": False, "status": None,
                                         "touched": False},
                "tailoredButNoPdf": {"match": "exact", "hasApplication": True,
                                     "pdfReady": False, "status": "draft",
                                     "touched": False},
                "ready": _READY,
                "filledAndStillDraft": {**_READY, "touched": True},
                "filledAndAlreadyApplied": {**_READY, "touched": True, "status": "applied"},
                # A row created and never touched can carry a null status.
                "filledWithNullStatus": {**_READY, "touched": True, "status": None},
                # D3: the escape hatch attached, and there is no row at all.
                "escapeHatch": {"match": "none", "hasApplication": False,
                                "pdfReady": False, "status": None, "touched": True},
                # Base mode on a page that holds a form: no job, no
                # application, a base resume armed. The gap that left the card
                # with nothing to press.
                "baseOnAForm": {"match": "none", "hasApplication": False,
                                "pdfReady": False, "status": None,
                                "touched": False, "hasForm": True,
                                "baseArmed": True},
                # …the same page with no resume chosen yet, and the same page
                # in tailored mode. Neither may reach the fill.
                "baseNotChosen": {"match": "none", "hasApplication": False,
                                  "pdfReady": False, "status": None,
                                  "touched": False, "hasForm": True,
                                  "baseArmed": False},
                "postingNotAForm": {"match": "none", "hasApplication": False,
                                    "pdfReady": False, "status": None,
                                    "touched": False, "hasForm": False,
                                    "baseArmed": True},
                # A tracked job whose application has no PDF yet, on a form.
                # Tailoring is still the next step — base mode is not armed.
                "tailoredNoPdfOnAForm": {"match": "exact", "hasApplication": True,
                                         "pdfReady": False, "status": "draft",
                                         "touched": False, "hasForm": True,
                                         "baseArmed": False},
            },
            "fills": {
                "empty": [],
                "noFrameAnswered": [
                    {"frameId": 0, "error": "no reply from the page"},
                    {"frameId": 1, "error": "no reply from the page"},
                ],
                "oneFrameOfTwo": [
                    {"frameId": 0, "error": "no reply from the page"},
                    {"frameId": 1, "result": {
                        "filled": [{"label": "email", "value": "a@b.test"}],
                        "eeoFilled": [],
                        "corrected": [],
                        "observations": [_observation("filled", "email")],
                    }},
                ],
                "everyBucket": [
                    {"frameId": 0, "result": {
                        "filled": [{"label": "first name", "value": "Jordan"}],
                        "eeoFilled": [{"field": "gender", "label": "gender",
                                       "value": "decline"}],
                        "corrected": [{"label": "email", "was": "old", "value": "new"}],
                        "observations": [
                            _observation("filled"),
                            _observation("filled_normalized"),
                            _observation("corrected"),
                            _observation("not_stuck"),
                            _observation("combobox_snap_failed"),
                            _observation("policy_blocked"),
                            _observation("skipped_checkbox"),
                            _observation("missing_source"),
                            _observation("eeo_disabled"),
                            _observation("skip_rule"),
                            _observation("hidden"),
                            _observation("no_rule"),
                            _observation("no_rule"),
                            # Not a profile-fill outcome. It must not be
                            # guessed into a bucket.
                            _observation("ai_answered"),
                        ],
                    }},
                    {"frameId": 1, "result": {
                        "filled": [{"label": "phone", "value": "555"}],
                        "corrected": [],
                        "observations": [_observation("filled")],
                    }},
                ],
                # The re-run: every field already held the answer, so the
                # engine reported them under `already` and emitted NO
                # observations — the frozen vocabulary has no outcome for a
                # write that never happened.
                "secondRun": [
                    {"frameId": 0, "result": {
                        "filled": [],
                        "eeoFilled": [],
                        "corrected": [],
                        "already": [
                            {"label": "email", "value": "a@b.test"},
                            {"label": "city", "value": "Chicago"},
                        ],
                        "observations": [],
                    }},
                    {"frameId": 1, "result": {
                        "filled": [],
                        "corrected": [],
                        "already": [{"label": "phone", "value": "555"}],
                        "observations": [],
                    }},
                ],
            },
            "rankings": {
                "byScore": {
                    "resumes": _RESUMES,
                    "scores": [
                        _score("data_engineer", 27.9),
                        _score("data_scientist", 65.0),
                        _score("business_analyst", 40.6),
                    ],
                },
                # Nothing scored yet: library order, every score null.
                "unscored": {"resumes": _RESUMES, "scores": []},
                # Scored only in part — the unscored ones sort last and keep
                # their library order among themselves.
                "partial": {
                    "resumes": _RESUMES,
                    "scores": [_score("business_analyst", 40.6)],
                },
                # Rows that are not base-phase base-resume scores must not be
                # read as one: an application's tailored score is a number
                # about a different target entirely.
                "ignoresOtherTargets": {
                    "resumes": _RESUMES,
                    "scores": [
                        {"target_type": "application", "target_id": "app-1",
                         "phase": "tailored", "composite": 99.0},
                        {"target_type": "base_resume", "target_id": "data_scientist",
                         "phase": "tailored", "composite": 98.0},
                    ],
                },
            },
            # The remembered pick. `now` is 10_000_000 in every case so the
            # ages below read as literal offsets from it.
            "sessions": {
                "sameOriginFresh": {
                    "entry": _SESSION,
                    "context": {"now": 10_000_000, "origin": "https://acme.wd5.example",
                                "matchedJobId": None, "ttlMs": 60_000},
                },
                "otherOrigin": {
                    "entry": _SESSION,
                    "context": {"now": 10_000_000, "origin": "https://evil.example",
                                "matchedJobId": None, "ttlMs": 60_000},
                },
                "expired": {
                    "entry": {**_SESSION, "at": 10_000_000 - 90_000},
                    "context": {"now": 10_000_000, "origin": "https://acme.wd5.example",
                                "matchedJobId": None, "ttlMs": 60_000},
                },
                "clockWentBackwards": {
                    "entry": {**_SESSION, "at": 10_000_000 + 5_000},
                    "context": {"now": 10_000_000, "origin": "https://acme.wd5.example",
                                "matchedJobId": None, "ttlMs": 60_000},
                },
                "backendKnowsADifferentJob": {
                    "entry": _SESSION,
                    "context": {"now": 10_000_000, "origin": "https://acme.wd5.example",
                                "matchedJobId": "job-other", "ttlMs": 60_000},
                },
                "backendAgrees": {
                    "entry": _SESSION,
                    "context": {"now": 10_000_000, "origin": "https://acme.wd5.example",
                                "matchedJobId": "job-1", "ttlMs": 60_000},
                },
                "nothingStored": {
                    "entry": None,
                    "context": {"now": 10_000_000, "origin": "https://acme.wd5.example",
                                "matchedJobId": None, "ttlMs": 60_000},
                },
            },
        },
        tmp_path_factory.mktemp("card"),
        source=WIDGET_JS,
    )


# ---------- the remembered pick (bug: the card forgot on every wizard step) ----------


@pytest.mark.parametrize(
    "name, restored, why",
    [
        ("sameOriginFresh", True,
         "the ordinary case: a refresh or the next wizard step of one application"),
        ("nothingStored", False, "nothing was ever picked"),
        ("otherOrigin", False,
         "a pick belongs to the site it was made on"),
        ("expired", False,
         "past its TTL it is a memory of a pick, not a pick"),
        ("clockWentBackwards", False,
         "a negative age is not freshness — the range test is why"),
        ("backendKnowsADifferentJob", False,
         "one Workday tenant serves every posting from one origin, so the "
         "backend recognising a DIFFERENT job means this pick is about another "
         "posting"),
        ("backendAgrees", True,
         "the backend recognised the same job the pick was made for"),
    ],
)
def test_which_remembered_picks_may_be_restored(card, name, restored, why):
    """The guards on re-arming the card from storage.

    The failure this exists for is mundane — an ATS wizard is six page loads
    and the pick died on the first — but the way it could go wrong is not:
    restoring the wrong application silently targets someone else's posting.
    """
    assert (card["restored"][name] is not None) is restored, why


@pytest.mark.parametrize(
    "name, state, action, nudge",
    [
        # Design §4.1's dot table, and design §4.2's three-step flow, together.
        ("unknown", "detected", "add-job", None),
        ("notTracked", "detected", "add-job", None),
        ("trackedNoApplication", "saved", "fast-tailor", None),
        # An application exists and is still a draft, so it can be marked
        # applied — whether or not this widget has written to THIS page. The
        # dot stays on the flow's stage, because the dot is the claim that we
        # filled here and these two have not.
        ("tailoredButNoPdf", "saved", "fast-tailor", "mark-applied"),
        ("ready", "ready", "autofill", "mark-applied"),
    ],
)
def test_the_primary_button_walks_the_flow(card, name, state, action, nudge):
    """`Add job` → `Fast tailor` → `Autofill this form`, and the dot beside it.

    Three actions, four dot states. The asymmetry is the point of the next
    test.

    The nudge is deliberately NOT tied to the flow: it answers a different
    question — is there a draft application to mark applied — and it used to be
    suppressed here for every case, which is the bug in the row below.
    """
    assert card["resolved"][name]["state"] == state
    assert card["resolved"][name]["action"]["id"] == action
    assert card["resolved"][name]["nudge"] == nudge


def test_a_draft_application_can_be_marked_applied_without_filling_here(card):
    """Reported twice as "where is the applied button", both times on a card
    that was showing the application correctly.

    The nudge used to require `touched` — this widget having filled or attached
    on THIS page. So it vanished on the submission-confirmation page, which is
    the one moment it is most wanted, and again on any re-run where every field
    already held the right value. The precondition is simply: there is a
    targeted application and it is still a draft.

    The dot keeps the stricter rule. It means "filled here", and that is a
    claim about the page which only `touched` can support.
    """
    cold = card["resolved"]["ready"]
    assert cold["nudge"] == "mark-applied"
    assert cold["prompted"] is False, "no grounds to ask 'Submitted it?' yet"
    assert cold["state"] == "ready", "the dot must not claim a fill that did not happen"

    filled = card["resolved"]["filledAndStillDraft"]
    assert filled["nudge"] == "mark-applied"
    assert filled["prompted"] is True
    assert filled["state"] == "draft"


def test_an_applied_application_is_not_nudged_again(card):
    """The nudge is for a DRAFT. Once it is applied there is nothing to ask."""
    assert card["resolved"]["filledAndAlreadyApplied"]["nudge"] is None


def test_a_backend_we_could_not_reach_is_not_a_page_we_do_not_have(card):
    """`match: null` and `match: "none"` land on the same button and must not
    be collapsed into one test of truthiness.

    They agree here because `Add job` re-asks either way. They would not agree
    on `Autofill`, which would target an application that may not exist — so
    the rule is written as `!== "exact"` rather than `=== "none"`.
    """
    assert card["resolved"]["unknown"] == card["resolved"]["notTracked"]


def test_filling_a_draft_changes_the_dot_and_not_the_primary(card):
    """The trap in design §4.1's table, and the reason the primary resolves
    from THREE actions while the dot has four states.

    A Workday application is a multi-step wizard. Replace the primary with
    "Mark as applied" the moment page one is filled and the user has lost the
    Autofill button they need on page two — while standing inside the exact
    form the widget exists for. So amber moves the dot and adds the nudge; the
    primary keeps offering the next step of the flow.
    """
    filled = card["resolved"]["filledAndStillDraft"]
    assert filled["state"] == "draft"
    assert filled["action"]["id"] == "autofill"
    assert filled["nudge"] == "mark-applied"
    # …and a null status is a draft, because a row can be created without one.
    assert card["resolved"]["filledWithNullStatus"]["nudge"] == "mark-applied"


def test_an_application_already_marked_applied_gets_no_nudge(card):
    """Design §6's prompt asks a question that has been answered. Asking it
    again is how a user learns to dismiss it without reading."""
    applied = card["resolved"]["filledAndAlreadyApplied"]
    assert applied["state"] == "ready"
    assert applied["nudge"] is None


def test_the_escape_hatch_nudge_offers_to_track_rather_than_to_flip(card):
    """D3. `Attach base resume` wrote nothing — no job, no application, no
    status — so there is nothing to mark applied and the same slot has to offer
    the write instead. One nudge, two contents, decided by whether a row
    exists."""
    hatch = card["resolved"]["escapeHatch"]
    assert hatch["state"] == "draft"
    assert hatch["nudge"] == "track-this"
    # The flow's own next step is still on offer beside it.
    assert hatch["action"]["id"] == "add-job"


def test_a_page_nobody_read_is_not_a_page_with_nothing_on_it(card):
    """The distinction the panel used to collapse. "No matching fields found"
    is a claim about the page, and it is a lie when every frame failed —
    `reached` is what the card branches on before it says anything."""
    assert card["reconciled"]["empty"]["reached"] is False
    assert card["reconciled"]["noFrameAnswered"]["reached"] is False
    assert card["reconciled"]["oneFrameOfTwo"]["reached"] is True


def test_one_dead_frame_does_not_cost_the_user_the_form(card):
    """An ATS page carries ad and analytics iframes that will never answer.
    Greenhouse and Lever put the whole application form in a subframe, so the
    surviving frame is usually the one that matters."""
    one = card["reconciled"]["oneFrameOfTwo"]
    assert [item["label"] for item in one["filled"]] == ["email"]
    assert one["counts"]["filled"] == 1


def test_the_strip_counts_come_from_the_commit_ladders_own_outcomes(card):
    """Design §4.2: render them, compute nothing new.

    Every number in `14 filled · 2 corrected · 1 didn't stick · 3 skipped`
    is a bucket of the frozen outcome vocabulary in
    `backend/app/schemas/autofill_telemetry.py`, counted across every frame
    that answered.
    """
    counts = card["reconciled"]["everyBucket"]["counts"]
    # filled + filled_normalized, across two frames. A site that REFORMATS what
    # we wrote still took it, and hedging a success teaches the user to
    # distrust the ones that worked.
    assert counts["filled"] == 3
    assert counts["corrected"] == 1
    # not_stuck + combobox_snap_failed: the two ways a write did not land.
    assert counts["notStuck"] == 2
    # policy_blocked, skipped_checkbox, missing_source, eeo_disabled, skip_rule,
    # hidden — recognised, and deliberately not written.
    assert counts["skipped"] == 6


def test_fields_with_no_rule_are_counted_apart_from_fields_we_skipped(card):
    """An ATS form carries dozens of controls no rule claims. Folding them into
    "skipped" prints a number about the SIZE OF THE FORM beside one about what
    we did — and buries the six deliberate decisions among thirty accidents."""
    counts = card["reconciled"]["everyBucket"]["counts"]
    assert counts["noRule"] == 2
    assert counts["skipped"] == 6, "no_rule leaked into the skipped bucket"


def test_an_outcome_the_table_does_not_know_is_counted_nowhere(card):
    """`ai_answered` reaches this function only if an AI batch is ever fed
    through it. Guessing it into a bucket would be a number the user cannot
    reconcile with anything; leaving it out is visible as a total that does not
    add up to the observation count, which is the honest failure."""
    result = card["reconciled"]["everyBucket"]
    assert len(result["observations"]) == 15
    assert sum(result["counts"].values()) == 14


def test_the_eeo_list_survives_aggregation_separately(card):
    """It is rendered under its own heading and reads as a completed
    disclosure, so it may never be merged into `filled` — and the engine only
    puts a field there when it watched the value land (design §8.5)."""
    assert card["reconciled"]["everyBucket"]["eeoFilled"] == [
        {"field": "gender", "label": "gender", "value": "decline"},
    ]


def test_a_second_run_counts_already_filled_fields_from_the_engines_own_list(card):
    """The "0 filled" fix, at the aggregation layer. `already` is the one
    count NOT derived from observations — the engine deliberately emits none
    for a field that already held the answer — so it is the length of the
    engine's own list, concatenated in frame order like the others, and it must
    not leak into `filled` or into any observation-derived bucket."""
    result = card["reconciled"]["secondRun"]
    assert result["reached"] is True
    assert result["filled"] == []
    assert [item["label"] for item in result["already"]] == [
        "email", "city", "phone",
    ]
    assert result["counts"]["already"] == 3
    assert result["counts"]["filled"] == 0
    # A frame that omits the key entirely (an older engine, a partial result)
    # reads as zero, never as an error.
    assert card["reconciled"]["everyBucket"]["counts"]["already"] == 0
    assert card["reconciled"]["everyBucket"]["already"] == []


# ---------- the card's shape (design §4.2) ----------


def test_the_card_has_no_tab_bar():
    """The old `Save job` / `Autofill` tablist existed because a 3,007-line
    panel needed a divider. The flow is sequential, so tabs become states of
    one card — and the four `data-view` blocks are one level down inside it,
    reached and left by one back button."""
    for banned in ('role="tab"', 'role="tablist"', 'class="tab"', "switchTab"):
        assert banned not in WIDGET_JS, f"{banned} is a tab bar returning"

    views = set(re.findall(r'data-view="(\w+)"', WIDGET_JS))
    assert views == {"main", "fields", "questions", "more"}
    # One card, one dialog. A second `role="dialog"` is a second surface.
    assert WIDGET_JS.count('setAttribute("role", "dialog")') == 1


def test_there_is_exactly_one_primary_button():
    """Design §4.2 item 2, and it is a count, not a style rule. Two primaries
    is the state the tablist produced: one flow, two entry points, and no
    answer to "what do I press"."""
    assert WIDGET_JS.count('data-act="primary"') == 1
    labels = re.search(r"const ACTIONS = \{(.*?)\n    \};", WIDGET_JS, re.S)
    assert labels
    assert set(re.findall(r'label: "([^"]+)"', labels.group(1))) == {
        "Add job", "Fast tailor", "Autofill this form",
    }


def test_the_escape_hatch_writes_nothing():
    """D3, and it is the whole point of the feature: `Attach base resume` costs
    the user no setup, so it may not create a job, an application or a status.
    "Track this" is where the write lives, and only when the user asks."""
    attach = re.search(
        r"async function attachBaseResume\(\) \{(.*?)\n  \}", WIDGET_JS, re.S)
    assert attach, "attachBaseResume is not where this test expects it"
    body = attach.group(1)
    assert "method:" not in body and "POST" not in body, (
        "the escape hatch is issuing a write; D3 says it attaches and records "
        "nothing until the user presses Track this")

    track = re.search(r"async function trackThis\(\) \{(.*?)\n  \}", WIDGET_JS, re.S)
    assert track
    assert "/api/applications/from-base" in track.group(1)


def test_the_ai_answer_is_never_folded_into_the_primary_autofill():
    """D2. The AI action is distinct, explicit and per-click, and it is bounded
    — eight questions is one model call the user is waiting on inside a timed
    form. An `Autofill` button that also invented free-text answers is the
    aggressive default design §11.9 rejects."""
    autofill = re.search(r"async function autofill\(\) \{(.*?)\n  \}", WIDGET_JS, re.S)
    assert autofill, "autofill() is not where this test expects it"
    for banned in ("aiAnswer", "collect_open_questions", "/api/qa"):
        assert banned not in autofill.group(1), (
            f"the primary Autofill button reaches {banned}; D2 keeps the AI "
            "answer a separate, explicit action")

    assert "const AI_FILL_MAX = 8;" in WIDGET_JS
    ai = re.search(r"async function aiAnswer\(\) \{(.*?)\n  \}", WIDGET_JS, re.S)
    assert "slice(0, AI_FILL_MAX)" in ai.group(1)


def test_the_eeo_toggle_sits_beside_the_fill_and_not_in_the_overflow():
    """Design §8.4 and the one place a wrong value is a false disclosure rather
    than an approximation. Off by default, and opt-in NEXT TO the fill action —
    a competitor's own per-field opt-out list is the evidence that users want
    to withhold this, and it still fills them by default."""
    # The sticky region: outside the body's scroll, above the footer, and
    # rendered only in the main view. It holds the toggle and the secondary
    # row, which is where the escape hatch lives — both are things design §4.2
    # calls always-present, and "present under a scroll" is not that.
    sticky = re.search(
        r'<div class="card-sticky" data-role="sticky">(.*?)\n      </div>',
        WIDGET_JS, re.S)
    assert sticky, "the sticky region is not where this test expects it"
    for control in ('data-act="eeo"', 'data-act="attach-base"'):
        assert control in sticky.group(1), (
            f"{control} has moved into the scrolling body or one level down; "
            "design §4.2 and §8.4 keep both on the one visible surface")
    assert 'slot("sticky").hidden = card.view !== "main"' in WIDGET_JS
    # And nothing here turns it on: since the EEO standing-consent round
    # (2026-07-30) the fill state comes from the BACKEND's consent record
    # (settings/eeo_consent.json via /api/autofill/context), not local
    # extension storage; the widget only ever reflects what the user consented
    # to in Profile. The legacy sw.js default stays off and is ignored for fill.
    assert "eeoAutofillEnabled: false" in SW_JS
    assert 'eeoEnabled: context.eeo_consent?.enabled === true' in WIDGET_JS


def test_the_fit_number_is_rendered_and_never_recomputed():
    """Design §11.7. A competitor's extension score disagrees with its own
    platform score for the same job; the number here comes from the tailor
    response and the widget owns no arithmetic that could disagree with it."""
    fit = re.search(r"function renderFit\(\) \{(.*?)\n  \}", WIDGET_JS, re.S)
    assert fit
    assert "compare.before" in fit.group(1) and "compare.after" in fit.group(1)
    assert not re.search(r"[-+*/]\s*(compare|score)", fit.group(1))
    # Assigned from the response and from nowhere else.
    assignments = re.findall(r"card\.compare = ([^;]+);", WIDGET_JS)
    assert assignments == ["out.compare ?? null", "null"]


def test_the_widget_never_submits_a_form():
    """Design §8.1, and the promise is printed on the surface where the user
    can read it.

    The engine's `isFormJunk` structurally excludes submit controls. This is
    the UI half, and it has a specific hazard of its own: the widget holds a
    selector that names every submit control on the page, for the collision
    observer. So the rule is that the selector is only ever READ through —
    nothing here activates a control on the page at all.
    """
    for banned in (".submit()", "requestSubmit", ".click()"):
        assert banned not in WIDGET_JS, f"{banned} activates a page control"
    assert "never submits for you" in WIDGET_JS, (
        "the promise is printed on the surface, not only in the README")

    uses = re.findall(r"(\w+)\(SUBMIT_SELECTOR\)", WIDGET_JS)
    assert uses == ["querySelectorAll"], (
        "SUBMIT_SELECTOR is being used for something other than looking; it "
        "names every submit control on the page")

    # Design §4.1's four selectors, verbatim — ported from the deleted
    # applied-detection suite, whose sync test was the only pin on the count.
    selector = re.search(r"const SUBMIT_SELECTOR = \[(.*?)\]\.join", WIDGET_JS, re.S)
    assert selector
    assert len(re.findall(r"'[^']+'", selector.group(1))) == 4


def test_exactly_one_thing_in_the_widget_patches_a_status():
    """`applied_at` is stamped on entry to applied and read by the analytics
    series as a fact about the past, so the status PATCH must stay behind ONE
    explicit click — `setStatus` — and never acquire a second call site.
    (Ported from the deleted applied-detection suite, where it pinned that the
    watcher on fire wrote nothing; the watcher is gone, the invariant is not.)
    """
    assert WIDGET_JS.count('method: "PATCH"') == 1
    patch_site = re.search(
        r"async function setStatus\(status\) \{(.*?)\n  \}", WIDGET_JS, re.S)
    assert patch_site and 'method: "PATCH"' in patch_site.group(1), (
        "the one PATCH in the widget must live in setStatus")


def test_everything_the_page_or_the_backend_supplies_is_written_as_text():
    """A company name, a job title and a field label are all attacker-
    influenced on an ATS that lets employers write their own postings, and the
    closed shadow root protects the page from us rather than us from the page.

    So `innerHTML` is assigned exactly twice — the card's constant skeleton and
    the bubble's glyph, both literals — and every dynamic value goes through
    `textContent`.
    """
    assigned = re.findall(r"\.innerHTML\s*=", WIDGET_JS)
    assert len(assigned) == 2, (
        "innerHTML is assigned somewhere other than the card skeleton and the "
        "bubble glyph; dynamic text must go through textContent")
    for banned in ("insertAdjacentHTML", "outerHTML", "document.write"):
        assert banned not in WIDGET_JS


def test_the_transcript_and_the_prefs_are_links_rather_than_screens():
    """Design §4.2 moved both out of the extension: a chat log is list-shaped,
    versioned and re-readable, and the web app does it better; the quick-tailor
    prefs live in /settings, which carries an explanatory sentence each plus a
    field the panel could not set at all. The composer stays — it answers the
    question in front of you."""
    assert "?tab=qa" in WIDGET_JS
    for banned in ("loadQaHistory", "renderQaHistory", "qa-thread", "qt-instruction",
                   "/api/settings/quick-tailor"):
        assert banned not in WIDGET_JS


def test_a_route_change_forgets_the_previous_posting():
    """Found by driving the preview page, and it is the worst thing this card
    could do: on an SPA route change the Tier C ask can FAIL while the previous
    posting's match is still in `card`, and the widget would then offer to
    autofill the application belonging to the job the user navigated away from.

    So the failure path clears the four facts rather than leaving them, and
    `reDetect` clears everything that is about one posting.
    """
    failure = re.search(
        r"async function loadContext\(\) \{.*?\} catch \(err\) \{(.*?)\n    \}",
        WIDGET_JS, re.S)
    assert failure, "loadContext's failure path is not where this test expects it"
    for cleared in ("card.match = null", "card.job = null",
                    "card.application = null", "card.pdfReady = false"):
        assert cleared in failure.group(1), (
            f"{cleared} is missing: an unreachable backend would leave the "
            "previous posting's answer on screen")

    redetect = re.search(r"async function reDetect\(\) \{(.*?)\n  \}", WIDGET_JS, re.S)
    assert redetect
    for cleared in ("card.fill = null", "card.attached = null", "card.touched = false",
                    "card.compare = null", "card.questions = null"):
        assert cleared in redetect.group(1)
    # …and NOT the things that are not about the posting.
    for kept in ("card.settings", "dock", "hiddenOrigins"):
        assert kept not in redetect.group(1)


# ---------- the service worker's half of the card ----------


def test_only_the_top_frame_may_drive_the_engine():
    """The widget mounts only where `window.top === window.self`, so a
    broadcast request arriving FROM a subframe is not the UI asking — on a
    Greenhouse posting it is an ad iframe. Same rule `sendToFrame` already
    enforces, and the tab id comes from the SENDER either way, so a message can
    never name another tab."""
    for handler in ("page_broadcast", "attach_pdf"):
        block = re.search(rf"async {handler}\(msg, frame\) \{{(.*?)\n  \}},",
                          SW_JS, re.S)
        assert block, f"{handler} is not where this test expects it"
        assert "from.frameId !== 0" in block.group(1)
        assert "from.tabId" in block.group(1)
        assert "msg.tabId" not in block.group(1)


def test_the_broadcastable_types_are_an_allow_list():
    """`extract_job_posting` is deliberately absent: a posting's JSON-LD is in
    the top document, the widget runs there and calls the handler directly, and
    broadcasting it would read every subframe on the page for nothing."""
    block = re.search(r"const BROADCASTABLE = \[(.*?)\];", SW_JS, re.S)
    assert block
    assert set(re.findall(r'"(\w+)"', block.group(1))) == {
        "profile_fill", "collect_open_questions", "fill_answers",
    }


def test_telemetry_is_scrubbed_and_gated_at_the_only_fetch_site():
    """Design §8.9. The allow-list rebuild is defense in depth over the
    backend's `extra="forbid"`, and it lives in the service worker because that
    is the only context that can post — a future caller that forgets to scrub
    cannot reach the network on its own."""
    assert "function scrubObservation(" in SW_JS
    keys = re.search(r"const TELEMETRY_KEYS = \[(.*?)\];", SW_JS, re.S)
    assert set(re.findall(r'"(\w+)"', keys.group(1))) == {
        "label", "kind", "rule_id", "options", "outcome", "host",
    }
    handler = re.search(r"async telemetry\(msg\) \{(.*?)\n  \},", SW_JS, re.S)
    assert handler
    assert "telemetryEnabled === false" in handler.group(1)
    assert "map(scrubObservation)" in handler.group(1)

    # And the widget has no other route to the endpoint.
    assert WIDGET_JS.count("/api/autofill/telemetry") == 0
    assert WIDGET_JS.count('ask("telemetry"') == 1


# ---------- the preview harness ----------


def test_the_preview_page_is_dev_only_and_not_shipped():
    """It loads the content scripts as ordinary <script> tags so the
    widget can be driven without an extension. That is only safe as long as it
    is not part of one: a page that is in `web_accessible_resources` or named by
    the manifest would be a real surface."""
    preview = EXTENSION / "dev" / "preview.html"
    assert preview.is_file(), "the widget's only executable harness"

    named = json.dumps(MANIFEST)
    assert "dev/" not in named and "preview" not in named
    assert "web_accessible_resources" not in MANIFEST
    assert "DEV ONLY" in preview.read_text(encoding="utf-8")[:200]


# ---------- the ghost card (reported: "where is the applied button") ----------


def test_a_dead_extension_context_says_what_to_do_about_it():
    """Reloading the extension orphans the content scripts already on open
    pages. The card stays on screen rendering the state it held at that moment
    — real job title, real counts — and every button on it is dead.

    It used to fail as `Cannot read properties of undefined (reading
    'sendMessage')`, printed on the card: one of our own stack frames, shown to
    somebody who wants to know why a button did nothing, never mentioning the
    one action that fixes it.
    """
    assert "CONTEXT_LOST" in WIDGET_JS
    guard = re.search(r"if \(!chrome\.runtime\?\.id\) throw new Error\(CONTEXT_LOST\)", WIDGET_JS)
    assert guard, "ask() no longer checks for an invalidated context before using it"
    # Both spellings: the API can also reject mid-call once the context dies.
    assert re.search(r"context invalidated\|receiving end does not exist", WIDGET_JS)
    message = re.search(r'const CONTEXT_LOST =\s*\n?\s*"([^;]+);', WIDGET_JS, re.S).group(1)
    assert "Reload this page" in message, "the remedy has to come first"


def test_re_injection_retires_the_previous_widget():
    """The toolbar icon injects into a tab with no content script — which after
    an extension reload is a tab with ORPHANED ones. Injection cannot tell those
    apart, so without this the user gets two bubbles: a live one and a ghost
    that answers every click with "reload this page"."""
    assert re.search(r"ns\.widget\?\.unmount\?\.\(\)", WIDGET_JS)


def test_the_applied_nudge_reads_as_a_button():
    """It was a bare `text-button`: grey on transparent, no border. In the
    sticky region — among labels and a checkbox — that renders as a grey
    SENTENCE, and was reported as the applied button missing from a card that
    was displaying it."""
    nudge = re.search(r'actionButton\(\s*\n?\s*"mark-applied".*?\);', WIDGET_JS, re.S).group(0)
    assert "nudge-button" in nudge
    assert re.search(r"\.nudge-button \{[^}]*border: 1px solid var\(--cs-primary\)", WIDGET_JS)
    # Still not the primary: that is the next step of the flow (Autofill again
    # on page two of a wizard) and the nudge must not compete with it.
    assert "class=\"primary\"" not in nudge


# ---------- does this file survive being LOADED ----------


_LOAD_DRIVER_JS = r"""
// Deliberately NOT `extract()`. Every other test in this file pulls one pure
// function out of widget.js and runs it, which is why the whole suite stayed
// green while the file was throwing at load on every page on the web: nothing
// had ever evaluated it end to end.
//
// The stubs are the smallest surface the module body touches before its
// top-frame guard. `window.top !== window.self` makes it return early, so this
// asserts exactly the part that runs before any UI exists — the constants, the
// stylesheet template, and the namespace publish.
global.window = { top: {}, self: {} };
const stubEl = () => ({
  style: { setProperty() {} }, setAttribute() {}, addEventListener() {},
  append() {}, appendChild() {}, querySelector: () => null,
  querySelectorAll: () => [], focus() {}, remove() {}, dataset: {},
});
global.document = {
  createElement: stubEl, documentElement: { appendChild() {} },
  querySelector: () => null, querySelectorAll: () => [], title: "t",
};
global.location = { origin: "https://x.test", hostname: "x.test", href: "https://x.test" };
global.chrome = {
  runtime: { id: "abc", onMessage: { addListener() {} }, sendMessage: async () => ({ ok: true }) },
  storage: { local: { get: async () => ({}), set: async () => {} },
             sync: { get: async () => ({}), set: async () => {} } },
};
global.CSSStyleSheet = class { replaceSync(text) { this.text = text; } };
global.IntersectionObserver = class { observe() {} disconnect() {} };
global.MutationObserver = class { observe() {} disconnect() {} };
global.requestAnimationFrame = (fn) => setTimeout(fn, 0);
global.addEventListener = () => {};

main(async () => {
  let threw = null;
  try {
    new Function(source)();
  } catch (err) {
    threw = `${err.constructor.name}: ${err.message}`;
  }
  emit({ threw });
});
"""


def test_widget_js_survives_being_loaded(tmp_path):
    """The guard that was missing, and what it cost.

    A CSS comment inside the SHEET template literal used this file's own prose
    convention — backticks around an identifier — and a backtick ENDS a
    template literal. The stylesheet terminated early, the CSS after it parsed
    as JavaScript, and the widget died at load with "….primary is not a
    function" on every page. `node --check` passes it (it is valid syntax,
    meaning something else), and all 537 extension tests passed, because every
    one of them extracts a single function instead of loading the file.

    So this executes the module body. It cannot assert the widget WORKS — that
    needs a browser — but "does it survive being loaded" is the floor, and it
    is the floor that was missing.
    """
    result = run_node(_LOAD_DRIVER_JS, {}, tmp_path, source=WIDGET_JS)
    assert result["threw"] is None, result["threw"]


# ---------- filling from a base resume, with no application in sight ----------


def test_a_form_can_be_filled_from_a_base_resume(card):
    """The reported gap: choosing Base left the card with no way to fill.

    The primary reached `autofill` only through a tracked job with a tailored
    PDF, so a user who had chosen Base on the control directly above it was
    offered Add job or Fast tailor instead — while the escape hatch could
    already ATTACH that same resume with no job and no application.
    """
    assert card["resolved"]["baseOnAForm"]["action"]["id"] == "autofill"


@pytest.mark.parametrize("name, action, why", [
    ("baseNotChosen", "add-job",
     "no resume is armed, so there is nothing to fill from"),
    ("postingNotAForm", "add-job",
     "a posting with no form has nothing to fill"),
    ("tailoredNoPdfOnAForm", "fast-tailor",
     "tailored mode: the base-fill gate must not pre-empt the tailoring flow"),
])
def test_what_the_base_fill_must_not_take_over(card, name, action, why):
    assert card["resolved"][name]["action"]["id"] == action, why


# ---------- ranking the base resumes the job already scored ----------


def test_the_dropdown_is_ordered_by_this_jobs_own_scores(card):
    """The reported problem: the card listed resumes in library order, so the
    pick was blind — and Fast tailor then built on whatever it was, reporting
    one ATS number for a resume nobody had reason to think was the right one.

    The app has scored every base against the job for a long time; the card
    simply never asked.
    """
    ranked = card["ranked"]["byScore"]
    assert [r["slug"] for r in ranked] == [
        "data_scientist", "business_analyst", "data_engineer"]
    assert [r["score"] for r in ranked] == [65.0, 40.6, 27.9]


def test_an_unscored_library_keeps_its_own_order(card):
    """"Not scored yet" is not a bad score. Showing it as one would be the card
    inventing a judgement it was not given."""
    ranked = card["ranked"]["unscored"]
    assert [r["slug"] for r in ranked] == [r["slug"] for r in _RESUMES]
    assert all(r["score"] is None for r in ranked)


def test_unscored_resumes_sort_below_scored_ones(card):
    ranked = card["ranked"]["partial"]
    assert ranked[0]["slug"] == "business_analyst" and ranked[0]["score"] == 40.6
    assert [r["slug"] for r in ranked[1:]] == ["data_engineer", "data_scientist"]
    assert all(r["score"] is None for r in ranked[1:])


def test_only_base_phase_base_resume_rows_are_read_as_scores(card):
    """An application's tailored score is a number about a different target,
    and a base resume's TAILORED row is a number about a resume that no longer
    exists in the form the dropdown is offering."""
    assert all(r["score"] is None for r in card["ranked"]["ignoresOtherTargets"])


def test_every_backend_path_the_card_calls_exists_in_the_api():
    """A typo'd path fails at RUNTIME, on a real form, as a bare 404 on the
    card — and nothing else in this repo reads these strings.

    Written after `/api/ats` was used for a router mounted at `/api/ats-scores`
    and reached review intact; the tests were green because none of them calls
    a URL. Checked against the live app's own OpenAPI paths, so it follows a
    route that moves.
    """
    from app.main import app

    known = set(app.openapi()["paths"])
    # Path template, not query string: the widget interpolates ids.
    called = {
        re.sub(r"\$\{[^}]*\}", "{id}", raw).split("?")[0]
        for raw in re.findall(r"""api\(\s*[`"']([^`"']+)""", WIDGET_JS)
    }
    assert called, "no backend paths found — this test is looking in the wrong place"

    def matches(path: str) -> bool:
        # A trailing interpolation may be a QUERY string rather than a path
        # segment — `/api/autofill/context${resumeQuery()}` builds "?base=…" —
        # so the bare path counts as a hit too.
        candidates = {path, re.sub(r"\{id\}$", "", path).rstrip("/") or "/"}
        if candidates & known:
            return True
        for candidate in candidates:
            pattern = re.compile(
                "^" + re.escape(candidate).replace(r"\{id\}", r"\{[^/]+\}") + "$")
            if any(pattern.match(route) for route in known):
                return True
        return False

    missing = sorted(path for path in called if not matches(path))
    assert missing == [], f"the card calls paths the API does not serve: {missing}"
