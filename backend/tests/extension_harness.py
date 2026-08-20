"""Node fake-DOM harness for the extension's split content-script modules.

The form and detection drivers execute the real namespace-published IIFEs, then
call their public entry points against a hand-written DOM. Node's `vm` does that
without adding a JS test runner to a Python project.

This module owns everything the tests share: the fake DOM, the scenario driver,
element construction, and the label remap. A capability one test needs —
`blur()`, `isConnected`, `normalizesTo`, an events recorder — is therefore
available to every other test instead of being a landmine the next author steps
on, and a new field flag is one line here rather than a copied driver.

Call `run_profile_fill` / `run_ai_fill`. `PRELUDE_JS` + `run_node` stay exported
for a test that genuinely needs its own driver; prefer extending the shared one.

`run_detect` is the second driver, for the page-detection gate. It models a
PAGE — a URL, ld+json scripts, attributes, body text — where the drivers above
model a form, so it installs its own `document`/`location` rather than making
one fake DOM answer both.

`fixtures/autofill/*.json` holds reconstructions of the live ATS control shapes
we fail on, built from telemetry signatures rather than captured DOM. Load them
with `load_fixture` / `run_fixture`, and the `detect_*` page shapes with
`load_detect_page` / `run_detect_fixture`; see that directory's README for why
none of them is captured DOM and what may never be pasted into them.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]

# Every file that can carry a PAGE FUNCTION **or a telemetry emitter**. Both
# halves of that rule are load-bearing and the second half is the one that was
# understated here before Task 19: `test_outcomes_the_extension_already_emits_
# are_all_accepted` scans `extension_source()` for outcome strings, so a file
# holding an emitter and missing from this list makes that roster silently
# shorter — the floor is what catches it, and only if the list is right.
#
# Task 9 moved all five page functions from sidepanel.js into content/agent.js.
# Phase 2 split the two writers and question collector into namespace-published
# modules and shared the JSON-LD walk; agent.js retains the extraction wrapper,
# attach operation, and stable PAGE_HANDLERS front door.
#
# R-C deleted `content/widget.js`, the one entry that was here as an EMITTER
# and not as a page function. Its four AI-path outcomes (`ai_answered`,
# `ai_no_stick`, `ai_unaligned`, `ai_unanswered`) went with it — the backend
# still accepts them because stored rows carry them, but nothing in the
# extension emits one any more. See
# `test_outcomes_the_extension_already_emits_are_all_accepted`, which records
# the drop.
#
# Task 12 split `content/open-questions.js`: the routing, the /choose batching
# and the `rest_fill` shaping are `shared/choose.js` now, so the panel document
# can load them and the page-DOM writers stay behind. It is on this list for the
# rule's SECOND half — it holds `ai_abstained`, and a telemetry emitter missing
# from here makes the outcome roster silently shorter.
#
# All are concatenated for source scans — see `extension_source`. Runtime
# drivers use the dependency-ordered subsets below and execute their IIFEs.
#
# READ FROM THE MANIFEST, which is sw.js's own rule (`contentScriptFiles`)
# applied to the test side, and it is a correction rather than a tidy-up. The
# list used to be typed out here, and it was WRONG in a way nothing could
# report: `shared/decisions.js` and `shared/guided-run.js` are injected into
# every page by `manifest.json` and were missing from it, so "everything a
# source scan must see" was a claim this file could not keep. A hand-kept
# mirror of a list the browser reads from a file is a mirror that drifts, and
# the drift is invisible precisely because the tests still pass — they scan a
# smaller world and find nothing wrong with it.
#
# ORDER COMES WITH IT, and that is the other half of the win: the manifest's
# order IS the injection order, so a driver now executes the modules in the
# sequence the browser does rather than in the sequence somebody typed. Each
# file publishes onto the namespace the next one reads, so that has always
# mattered and was previously kept by hand too.
SHARED = ROOT / "extension" / "shared"
CONTENT = ROOT / "extension" / "content"

_MANIFEST = json.loads(
    (ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))

EXTENSION_SOURCES = [
    ROOT / "extension" / relative
    for entry in _MANIFEST["content_scripts"]
    for relative in entry["js"]
]
assert EXTENSION_SOURCES, "manifest.json declares no content scripts"

FORM_MODULE_SOURCES = [
    SHARED / "choose.js",
    SHARED / "policy.js",
    SHARED / "profile-fields.js",
    CONTENT / "eeo.js",
    CONTENT / "autofill.js",
    CONTENT / "open-questions.js",
]
DETECTION_MODULE_SOURCES = [CONTENT / "job-posting.js", CONTENT / "detect.js"]

# The two lists COINCIDE since R-C, and that is a fact about today rather than a
# rule: `EXTENSION_SOURCES` is "everything a source scan must see" and this is
# "everything a runtime driver may execute", and they agreed the moment the one
# file that was scannable-but-not-runnable (`content/widget.js`, an emitter with
# no page function) was deleted. Two names for one list, because the next file
# added answers the two questions separately again — and when that happens this
# becomes a written-out list, NOT a slice of the other.
#
# NEVER A SLICE, and the assertion below is what enforces it rather than a
# comment asking nicely. This line used to read `EXTENSION_SOURCES[:-1]`, one
# index away from silently dropping `agent.js` — which publishes
# `PAGE_HANDLERS`, so every driver would have gone on running against a world
# with no message boundary in it, reporting handlers as unreachable and page
# functions as absent. An index range re-points itself when a file is added,
# which is exactly how a driver ends up executing a set nobody chose.
PAGE_RUNTIME_SOURCES = list(EXTENSION_SOURCES)
assert PAGE_RUNTIME_SOURCES == EXTENSION_SOURCES, (
    "PAGE_RUNTIME_SOURCES has diverged from EXTENSION_SOURCES. That is allowed "
    "— but write the paths out, do not slice: a range silently re-points when "
    "the manifest gains a file, and this assertion is the reminder to choose.")


def _content_source(paths: list[Path]) -> str:
    """Read real module files in browser injection order, failing if one moved."""
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def extension_source() -> str:
    """Concatenated text of every extension content source for source scans."""
    return _content_source(EXTENSION_SOURCES)


def page_runtime_source() -> str:
    """Real dependency-ordered modules through the agent message boundary."""
    return _content_source(PAGE_RUNTIME_SOURCES)


def js_code(source: str) -> str:
    """`source` with its comment-only lines dropped, for source-scan pins.

    A raw-source pin on a string the comments NARRATE asserts nothing, and this
    repo's extension comments narrate deleted machinery on purpose — they are
    the record of what a control used to do. Both directions are traps:

    * a positive (`"openPanelOnActionClick: true" in SW_JS`) passes on the
      comment that explains the call long after the call itself is gone, which
      is exactly the "green for the wrong reason" failure this repo has hit
      repeatedly;
    * a negative (`"chrome.action.onClicked.addListener" not in SW_JS`) fails
      the day someone quotes the deleted listener in full while explaining why
      it was deleted — a test that forbids honest prose.

    So every pin that means "the CODE says this" runs through here. Line
    oriented, matching the idiom these tests already used inline: a line whose
    first non-space characters open or continue a comment is not code. That
    misses a trailing `// …` after real code and the tail of a `/* … */` whose
    continuation lines are unprefixed, and it is deliberately not a JS parser —
    a pin that needs more precision than this wants to be a behavioural test.
    """
    return "\n".join(
        line for line in source.splitlines()
        if not line.lstrip().startswith(("//", "*", "/*"))
    )


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "autofill"

# Everything a scenario driver can rely on: the source extractor, the fake DOM,
# the browser globals the injected functions reach for, and `emit`/`main`.
PRELUDE_JS = r"""
const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync(process.argv[2], "utf8");
const spec = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));

// The split harness executes the real IIFEs. Source extraction remains below
// only for isolated service-worker/widget helpers whose files are passed
// explicitly and are not content modules.
const loadModules = () => {
  vm.runInThisContext(source);
  return window.careerStudioCompanion;
};

// The `async` prefix is part of the match so an extracted function keeps it —
// slicing from a bare "function NAME" would silently strip it and turn an
// awaited commit into a synchronous one, which is the bug several tests pin.
const extract = (name, endMarker) => {
  const pattern = `(?:async\\s+)?function ${name}\\b`;
  // Sources are CONCATENATED, so a function COPIED rather than moved appears
  // twice and a first-match-wins .exec would silently run the copy while the
  // stale original still ships. Counted separately from "not found" so each
  // failure names itself, rather than surfacing as a byte-identical-copy test
  // reporting a count from a completely different invariant.
  const all = source.match(new RegExp(pattern, "g")) || [];
  if (all.length === 0) {
    throw new Error(`${name} not found in the extension source`);
  }
  if (all.length > 1) {
    throw new Error(
      `${name} defined ${all.length} times — a stale copy was left behind`);
  }
  const match = new RegExp(pattern).exec(source);
  const end = source.indexOf(endMarker, match.index);
  if (end < 0) throw new Error(`end of ${name} not found in the extension source`);
  // The trailing newline makes the slice safe to end in ANY line comment: the
  // wrapper's `)` would otherwise land inside a trailing `//` and never close
  // the expression. Today's slices end on the sentinel's own comment block, but
  // the property is what matters — keep this through any comment reflow.
  return vm.runInThisContext(`(${source.slice(match.index, end)}\n)`);
};

const mutationObservers = new Set();
const notifyMutation = () => {
  for (const observer of [...mutationObservers]) observer._callback([]);
};
class FakeMutationObserver {
  constructor(callback) { this._callback = callback; }
  observe() { mutationObservers.add(this); }
  disconnect() { mutationObservers.delete(this); }
}

const eventLog = [];

class FakeEvent {
  constructor(type, init = {}) {
    this.type = type;
    this.bubbles = init.bubbles === true;
    this.key = init.key;
  }
}

// One [role="option"] node of a rendered listbox. Owned by the control whose
// popup it lives in: clicking it commits the option the way the real widgets
// do — react-select closes over the choice, a Workday button prints it as its
// own text — so the owner records which option was taken and a button test can
// read the committed value back off the control.
class FakeOption {
  constructor(text, owner, chosenChip = false) {
    this.innerText = text;
    this.owner = owner;
    // A multiselect's ALREADY-CHOSEN value, which Workday also marks
    // role="option" (live, bah.wd1 2026-08-08). It is a chip, not an offer —
    // the only thing clicking it can do is un-pick a committed value.
    this._chosenChip = chosenChip;
    // Rendered bounds: listboxOptions' fallback branch filters on isVisible.
    this.offsetWidth = 100;
    this.offsetHeight = 20;
  }
  getAttribute() { return null; }
  // The chip's container, and nothing else — the one ancestor question the
  // engine asks of an option node.
  closest(selector) {
    return this._chosenChip && /selectedItem/.test(selector)
      ? { tagName: "UL" } : null;
  }
  getClientRects() { return [{}]; }
  getBoundingClientRect() { return { width: 100, height: 20 }; }
  dispatchEvent(event) {
    this.owner.events.push(`option:${event.type}:${this.innerText}`);
    if (event.type === "click") this.owner.takeOption(this.innerText);
  }
}

let listboxIds = 0;

class FakeElement {
  constructor({
    label,
    value = "",
    visible = true,
    visibilityMode = "normal",
    qid = null,
    role = null,
    type = "",
    checked = false,
    clickCancelled = false,
    reverts = false,
    revertsTimes = null,
    detaches = false,
    normalizesTo = null,
    disabled = false,
    tokenizes = false,
    legend = null,
    listbox = null,
    listboxDelay = 0,
    listboxVia = null,
    optionFailures = 0,
    workdaySearch = false,
    haspopup = null,
    automationId = null,
    dateWidget = null,
    select2Ancestor = false,
  } = {}) {
    // A section of a split date widget, modelled from the live Workday shape
    // (deluxe.wd5, 2026-08-08): role="spinbutton", an id of
    // `<widget>-dateSection<Part>-input`, and — the load-bearing half — a
    // widget that DISCARDS a section when focus leaves the whole widget while
    // the date is still incomplete. `dateWidget` names the widget the section
    // belongs to, so two sections can share one.
    this._dateWidget = dateWidget;
    // The live Workday shape (bah.wd1, 2026-08-08): a search input carrying
    // NO combobox ARIA — no role, no aria-autocomplete — only the vendor's
    // own widget-type attribute. Declared per field so a test can model the
    // control the telemetry actually recorded rather than an idealised one.
    this._workdaySearch = workdaySearch;
    // aria-haspopup and data-automation-id, for the button dropdowns: the
    // form's own carry haspopup="listbox" and NO automation id, the header's
    // utility chrome carries both (live dump, bah.wd1 2026-08-08) — which is
    // exactly the discriminator the walk uses.
    this._haspopup = haspopup;
    this._automationId = automationId;
    // A react-select/select2 input whose own node carries no combobox ARIA.
    // The production predicate recognizes the surrounding widget class.
    this._select2Ancestor = select2Ancestor;
    this.tagName = "INPUT";
    this._label = label;
    this._value = value;
    this._qid = qid;
    this._role = role;
    this._clickCancelled = clickCancelled;
    this._reverts = reverts;
    this._revertsRemaining = revertsTimes;
    this._detaches = detaches;
    this._normalizesTo = normalizesTo;
    this._tokenizes = tokenizes;
    // The only ANCESTORS this fake DOM models, declared per field by `legend`:
    // a <fieldset> whose <legend> carries the question, and the <label> that
    // wraps the control and carries its own visible text. That pair is how an
    // ATS renders a grouped question — <legend>Do you consent?</legend> over
    // buttons labelled "Yes"/"No" — and it is the only shape where a control's
    // own label and the QUESTION it answers are different strings. Everything
    // else keeps closest() returning null, exactly as before.
    this._fieldset = legend === null ? null : {
      tagName: "FIELDSET",
      innerText: legend,
      // Answers `legend`, not the '[class*="label"], [class*="question"]'
      // container probe — a <fieldset> holds the question in its legend.
      querySelector: (selector) =>
        (/(^|,)\s*legend\s*(,|$)/.test(selector) ? { innerText: legend } : null),
    };
    // A listbox the control can render: option nodes that appear only after
    // the control is engaged (focused, typed into, or clicked open) and, with
    // `listboxDelay`, only after that many milliseconds — the async remote
    // lists the poll loop exists for. `listboxVia: "aria-controls"` routes the
    // options through the attribute branch of listboxOptions instead of the
    // bare [role="option"] fallback; both are real branches and each needs to
    // stay independently reachable.
    // A `listbox` entry may be a bare string (an ordinary offer) or
    // `{text, chosenChip: true}` for a multiselect's committed value.
    this._listbox = (listbox ?? []).map((entry) => (typeof entry === "string"
      ? new FakeOption(entry, this)
      : new FakeOption(entry.text, this, entry.chosenChip === true)));
    this._listboxDelay = listboxDelay;
    this._listboxVia = listboxVia;
    this._optionFailures = optionFailures;
    this._listboxId = `lb-${(listboxIds += 1)}`;
    this._listboxOpen = false;
    this._listboxTimer = null;
    // Which option a click committed — a Workday-style button prints it as its
    // own text, so `value` reports it for button controls.
    this.selectedOption = null;
    // What a token widget has turned our writes into. Reported separately from
    // `value` because they are different things: the chips are the answer the
    // user ends up with, and the box is empty precisely BECAUSE they exist.
    this.tokens = [];
    this.events = [];
    this.writeCount = 0;
    this.isConnected = true;
    this.id = "";
    this.name = "";
    // Drives kindOf() and the loop's per-type branches. "" is a plain text
    // input, which is what every field was before checkboxes needed telling
    // apart from them.
    this.type = type;
    // A control the fill loop skips outright. Declarable because "skipped" has
    // to mean skipped EVERYWHERE — a disabled input in a template block must
    // not make that block look real to the block-scope pre-pass either.
    this.disabled = disabled;
    this.readOnly = false;
    // Which option of a group ended up selected — the whole question a radio
    // or checkbox test asks, and neither control holds it in `value`. Settable
    // from a fixture because a page can arrive with a box already ticked (a
    // saved application, the user's own click), and a writer that clicks
    // blindly would clear it.
    this.checked = checked;
    // Normal bounds even when clipped, so `clipped` exercises the CSS-clip
    // branch of isStrictlyVisible rather than being rejected earlier by the
    // width/height floor — otherwise deleting that branch leaves tests green.
    // The 1x1 case is covered on its own by `tinyBounds`.
    this.offsetWidth = visible ? (visibilityMode === "tinyBounds" ? 1 : 100) : 0;
    this.offsetHeight = visible ? (visibilityMode === "tinyBounds" ? 1 : 20) : 0;
    this._style = {
      display: "block",
      visibility: visibilityMode === "visibilityHidden" ? "hidden" : "visible",
      opacity: visibilityMode === "transparent" ? "0" : "1",
      clip: visibilityMode === "clipped" ? "rect(0px, 0px, 0px, 0px)" : "auto",
      clipPath: visibilityMode === "clipPath" ? "inset(50%)" : "none",
      contentVisibility: "visible",
    };
    this.parentElement = visibilityMode === "ancestorHidden"
      ? {
          _style: {
            display: "none",
            visibility: "visible",
            opacity: "1",
            clip: "auto",
            clipPath: "none",
            contentVisibility: "visible",
          },
          parentElement: null,
          getAttribute: () => null,
        }
      : null;
  }
  // Engaging the control is what renders its popup, exactly like the real
  // widgets: react-select opens on focus/typing, Workday's button on click.
  openListbox() {
    if (!this._listbox.length || this._listboxOpen || this._listboxTimer) return;
    this._listboxTimer = setTimeout(() => {
      this._listboxOpen = true;
      notifyMutation();
    }, this._listboxDelay);
  }
  takeOption(text) {
    if (this._optionFailures > 0) {
      this._optionFailures -= 1;
      return;
    }
    this.selectedOption = text;
    // A button dropdown prints its committed choice as its own text; an input
    // combobox keeps whatever was typed (the real ones render the choice in a
    // sibling node the engine never reads).
    if (this.tagName === "BUTTON") this._value = text;
  }
  get value() { return this._value; }
  set value(value) {
    this.writeCount += 1;
    this._value = value;
    if (value !== "") this.openListbox();
    // A controlled input that rejects the write reverts on a LATER tick, never
    // in the tick that wrote it — a same-tick readback always sees the write.
    if (this._reverts || (this._revertsRemaining ?? 0) > 0) {
      if (this._revertsRemaining !== null) this._revertsRemaining -= 1;
      queueMicrotask(() => { this._value = ""; });
    }
    // A widget that re-renders swaps this node out for a fresh one. The node we
    // hold keeps our value forever precisely because nothing is rendering it.
    if (this._detaches) queueMicrotask(() => { this.isConnected = false; });
    // A field that REWRITES what it was given — a phone mask, a date picker, a
    // currency separator. Like a revert it lands on a later tick, so it is
    // indistinguishable from a rejection to anything reading back verbatim.
    if (this._normalizesTo !== null && value !== this._normalizesTo) {
      queueMicrotask(() => { this._value = this._normalizesTo; });
    }
  }
  getAttribute(name) {
    if (name === "role" && this._dateWidget) return "spinbutton";
    if (name === "aria-label") return this._label;
    if (name === "data-rt-qid") return this._qid;
    if (name === "role") return this._role;
    // Only the aria-controls route advertises the id, and only while the list
    // is rendered — a closed popup's container is not in the DOM, and an id
    // that resolved to options before the control was engaged would let
    // listboxOptions skip the engagement the real widgets require.
    if (name === "aria-controls") {
      return this._listboxVia === "aria-controls" && this._listboxOpen
        ? this._listboxId : null;
    }
    if (name === "data-uxi-widget-type") {
      return this._workdaySearch ? "selectinput" : null;
    }
    if (name === "aria-haspopup") return this._haspopup;
    if (name === "data-automation-id") return this._automationId;
    // A real control reports its own type here. Returning null for every
    // element let a checkbox satisfy `!el.getAttribute("type")` and be
    // collected as a plain text input, which no browser would do.
    if (name === "type") return this.type || null;
    return null;
  }
  // collectOpenQuestions TAGS what it collects, and the tag is what
  // fillAnswersByQid later resolves the field through — so "was this offered
  // to the model" is readable off the element itself, not only off the
  // returned list.
  setAttribute(name, value) {
    if (name === "data-rt-qid") this._qid = value;
  }
  hasAttribute() { return false; }
  closest(selector) {
    if (this._select2Ancestor && /select2|select__|autocomplete/.test(selector)) {
      return { className: "select2-container" };
    }
    // No tree: a field declares its own ancestors (see `_fieldset`), and a
    // field that declares none has no ancestors at all. Matched on the tag as
    // a whole selector token, so '[class*="label" i]' is not a <label>.
    if (!this._fieldset) return null;
    const wants = (tag) => new RegExp(`(^|,)\\s*${tag}\\s*(,|$)`).test(selector);
    if (wants("label")) return { innerText: this._label };
    if (wants("fieldset")) return this._fieldset;
    return null;
  }
  getClientRects() { return this.offsetWidth ? [{}] : []; }
  getBoundingClientRect() {
    return { width: this.offsetWidth, height: this.offsetHeight };
  }
  dispatchEvent(event) {
    this.events.push(event.type);
    eventLog.push(`${this._label}:${event.type}`);
    // The kind-driven combobox open (fireMouseSequence + ArrowDown) and the
    // button writer's click both engage the popup without typing.
    if (event.type === "click" || event.type === "keydown") this.openListbox();
    // A TOKEN input — Workday Skills, react-select's creatable — turns the text
    // in its box into a chip on Enter and then CLEARS the box itself. That
    // inverts the usual readback: an empty box is the success, not the failure.
    // The clear lands on a later tick, like every other framework re-render
    // modelled here, so a writer that reads back in the tick it wrote in still
    // sees its own text and cannot mistake this for an instant success.
    if (this._tokenizes && event.type === "keydown" && event.key === "Enter"
        && this._value) {
      const text = this._value;
      queueMicrotask(() => { this.tokens.push(text); this._value = ""; });
    }
  }
  // A real radio group is exclusive: checking one member unchecks its
  // siblings. Modelled because "which option is selected" is the whole
  // question a radio test asks, and a group where two buttons read as checked
  // would let a wrong answer pass alongside the right one.
  //
  // A checkbox TOGGLES instead — clicking a ticked box clears it, which is why
  // a writer has to look before it clicks.
  click() {
    this.events.push("click");
    eventLog.push(`${this._label}:click`);
    // A framework that calls preventDefault() on the click cancels the default
    // action, and for a tick box the default action IS the state change — so
    // the click is dispatched and the box stays exactly as it was.
    if (this._clickCancelled) return;
    if (this.type === "checkbox") {
      this.checked = !this.checked;
      return;
    }
    for (const el of currentElements) {
      if (el.type === "radio" && el.name === this.name) el.checked = el === this;
    }
  }
  // Recorded distinctly: focus() scrolls the element into view unless asked not
  // to, which walks the page down a long form one field at a time.
  focus(options) {
    this.events.push(options?.preventScroll === true ? "focus:preventScroll" : "focus");
    this.openListbox();
  }
  blur() {
    this.events.push("blur");
    // A WIDGET THAT RE-RENDERS ON BLUR, which is the classic trigger — and the
    // reason `detaches` had to reach past the value setter it lived on: the
    // click writers (radio, checkbox) never set a value, so before the commit
    // gesture existed there was no way for one of them to be blurred at all,
    // and no way to model the node being replaced under the verdict that is
    // about to be read off it.
    //
    // SYNCHRONOUS HERE, where the value setter's copy queues a microtask, and
    // the difference is the DOM's rather than a convenience: `el.blur()`
    // dispatches focusout synchronously, so a framework that re-renders in its
    // blur handler has already replaced the node by the time `blur()` returns.
    // That is precisely the window a click writer's verdict is read in.
    if (this._detaches) this.isConnected = false;
    // The measured behaviour, and the whole point of this flag. A split date
    // validates when focus leaves the WIDGET: if any sibling section of the
    // same widget is still empty, the date is incomplete and the widget throws
    // THIS section's value away. It lands on a later tick, exactly like every
    // other framework re-render modelled here, so a same-tick readback still
    // sees the write and cannot mistake this for an instant success.
    if (!this._dateWidget) return;
    const siblings = currentElements.filter(
      (el) => el._dateWidget === this._dateWidget);
    if (siblings.some((el) => el._value === "")) {
      queueMicrotask(() => { this._value = ""; });
    }
  }
}

class HTMLInputElement extends FakeElement {}
class HTMLTextAreaElement extends FakeElement {
  constructor(init = {}) { super(init); this.tagName = "TEXTAREA"; }
}
class HTMLSelectElement extends FakeElement {
  constructor(init = {}) {
    super(init);
    this.tagName = "SELECT";
    this.options = [{ value: "", textContent: "Select" }, ...(init.options ?? [])];
  }
}
// The Workday dropdown shape (live, bah.wd1 2026-08-08): <button
// aria-haspopup="listbox" type="button" id="country--country"> whose visible
// TEXT is the committed value ("United States of America" / "Select One").
// `value` mirrors the text so `values[label]` reads naturally in a test;
// innerText is what the writer's readback consults.
class HTMLButtonElement extends FakeElement {
  constructor(init = {}) {
    super(init);
    this.tagName = "BUTTON";
  }
  get innerText() { return this._value; }
}
// Browsers put the `value` accessor on the concrete prototype. Mirroring that
// keeps setNativeValue on its real path — the prototype-setter lookup that
// bypasses React's _valueTracker — instead of the assignment fallback.
const valueDescriptor = Object.getOwnPropertyDescriptor(FakeElement.prototype, "value");
for (const Cls of [HTMLInputElement, HTMLTextAreaElement, HTMLSelectElement]) {
  Object.defineProperty(Cls.prototype, "value", valueDescriptor);
}

global.HTMLInputElement = HTMLInputElement;
global.HTMLTextAreaElement = HTMLTextAreaElement;
global.HTMLSelectElement = HTMLSelectElement;
global.HTMLButtonElement = HTMLButtonElement;
global.window = {
  HTMLInputElement, HTMLTextAreaElement, HTMLSelectElement, HTMLButtonElement,
};
global.CSS = { escape: (value) => value };
global.Event = FakeEvent;
global.MouseEvent = FakeEvent;
global.KeyboardEvent = FakeEvent;
global.MutationObserver = FakeMutationObserver;
global.location = { hostname: "jobs.example.test" };
global.getComputedStyle = (element) => element._style;
// vm has no rAF. A setTimeout shim keeps the readback on the macrotask queue,
// i.e. still ordered after the microtask a framework revert would ride on.
// `freezeFrames` models a backgrounded tab, where rAF never fires at all.
global.requestAnimationFrame = spec.freezeFrames === true
  ? () => {}
  : (fn) => setTimeout(fn, 0);

let currentElements = [];
const setElements = (elements) => { currentElements = elements; };
global.document = {
  documentElement: {},
  visibilityState: spec.freezeFrames === true ? "hidden" : "visible",
  querySelector: (selector) => {
    const match = /^\[data-rt-qid="(.*)"\]$/.exec(selector);
    if (!match) return null;
    return currentElements.find((element) => element._qid === match[1]) ?? null;
  },
  querySelectorAll: (selector) => {
    // The page walk, in any of its spellings. A walk that names button gets
    // the button dropdowns; one that does not keeps the pre-button set — both
    // walks are live at once while collectOpenQuestions catches up, and a
    // harness that answered them identically would hide exactly that skew.
    if (/\binput\b/.test(selector) && /\bselect\b/.test(selector)
        && /\btextarea\b/.test(selector)) {
      return selector.includes("button")
        ? currentElements
        : currentElements.filter((el) => el.tagName !== "BUTTON");
    }
    // The radio-group query: both the fill branch and optionTexts() resolve a
    // group through it, so a radio button is only reachable once this answers.
    const group = /^input\[type="radio"\]\[name="(.*)"\]$/.exec(selector);
    if (group) {
      return currentElements.filter(
        (el) => el.type === "radio" && el.name === group[1]);
    }
    // The EEO single-choice group lookup: boxes sharing an id SUFFIX (how
    // Workday groups a disability question) or a name.
    const bySuffix = /^input\[type="checkbox"\]\[id\$="-(.*)"\]$/.exec(selector);
    if (bySuffix) {
      return currentElements.filter(
        (el) => el.type === "checkbox" && String(el.id).endsWith(`-${bySuffix[1]}`));
    }
    const byName = /^input\[type="checkbox"\]\[name="(.*)"\]$/.exec(selector);
    if (byName) {
      return currentElements.filter(
        (el) => el.type === "checkbox" && el.name === byName[1]);
    }
    // listboxOptions' fallback: every option of every OPEN popup. Options of a
    // closed popup are not in the DOM, exactly like the real widgets.
    if (selector === '[role="option"]') {
      return currentElements.flatMap((el) =>
        el._listboxOpen && el._listboxVia !== "aria-controls" ? el._listbox : []);
    }
    return [];
  },
  // Two callers: listboxOptions resolving an aria-controls id to its rendered
  // container, and the readback re-locating a control a framework re-render
  // replaced. Both are id lookups over what is currently "in the DOM".
  getElementById: (id) => {
    const owner = currentElements.find(
      (el) => el._listboxOpen && el._listboxId === id);
    if (owner) return { querySelectorAll: () => [...owner._listbox] };
    return currentElements.find((el) => el.isConnected && el.id === id) ?? null;
  },
};

const emit = (payload) => process.stdout.write(JSON.stringify(payload));
const main = (run) => run().catch((error) => {
  console.error(error);
  process.exit(1);
});
"""


# The one scenario driver. Both entry points below share it, so a field flag
# added to FakeElement is immediately reachable from every test.
_DRIVER_JS = r"""
const ns = loadModules();

const makeElement = (field, label) => {
  const element = new (
    field.kind === "textarea" ? HTMLTextAreaElement
      : field.kind === "select" ? HTMLSelectElement
        : field.kind === "listboxButton" ? HTMLButtonElement
          : HTMLInputElement)({
    label,
  // A listboxButton's "value" is its visible text, "Select One" until an
  // option commits — the live Workday placeholder (bah.wd1, 2026-08-08).
  value: field.value ?? (field.kind === "listboxButton" ? "Select One" : ""),
  visible: field.hidden !== true,
  visibilityMode: field.visibilityMode ?? "normal",
  options: field.options ?? [],
  qid: field.qid ?? null,
  // A workdaySearch field deliberately gets NO combobox role: the live control
  // carries none, and stamping one here would make the flag's tests vacuous.
  role: field.kind === "combobox" && field.workdaySearch !== true ? "combobox" : null,
  // An explicit `type` is for the NATIVE date controls ("month", "date"),
  // whose value format is fixed by HTML rather than by the label beside them.
  // kindOf() still reports those as `text`, which is what telemetry records, so
  // `kind` cannot carry them and the two have to be declared separately.
  type: field.type ?? (field.kind === "checkbox" ? "checkbox"
    : field.kind === "radio" ? "radio"
      : field.kind === "listboxButton" ? "button" : ""),
  checked: field.checked === true,
  disabled: field.disabled === true,
  clickCancelled: field.clickCancelled === true,
  reverts: field.reverts === true,
  revertsTimes: field.revertsTimes ?? null,
  detaches: field.detaches === true,
  normalizesTo: field.normalizesTo ?? null,
  tokenizes: field.tokenizes === true,
  legend: field.legend ?? null,
  listbox: field.listbox ?? null,
  listboxDelay: field.listboxDelay ?? 0,
  listboxVia: field.listboxVia ?? null,
  optionFailures: field.optionFailures ?? 0,
  workdaySearch: field.workdaySearch === true,
  // A listboxButton defaults to the live Workday shape: haspopup="listbox",
  // no automation id. `automationId` lets a test model the header's utility
  // chrome instead.
  haspopup: field.haspopup ?? (field.kind === "listboxButton" ? "listbox" : null),
  automationId: field.automationId ?? null,
  dateWidget: field.dateWidget ?? null,
  select2Ancestor: field.select2Ancestor === true,
  });
  if (field.trackedValue === true) {
    Object.defineProperty(element, "value", {
      configurable: true,
      get() { return this._value; },
      set() { this.events.push("tracked-set"); },
    });
  }
  return element;
};

// A radio GROUP is one logical field rendered as N buttons, so one field spec
// expands to N elements — `{kind: "radio", options: ["Yes", "No"]}` declares
// the question once, the way a test wants to read it.
//
// Each button's label is "<option> | <question>" because that is the order
// labelFor() builds on a real page: the button's own <label for=…> first, the
// group's <legend> after it. OPTION_WORDS anchors on ^yes / ^no, so a group
// built the other way round would answer every question wrongly.
//
// The group `name` defaults to the question — it is what document
// .querySelectorAll resolves the group through, and labelFor() appends it to
// every button's label, so keep it question-shaped. Override it when one page
// asks the same question twice (repeated blocks).
const groups = spec.fields.map((field) => {
  if (field.kind !== "radio") return [makeElement(field, field.label)];
  return (field.options ?? []).map((option) => {
    // With a `legend` declared the button's own text is JUST the option, the
    // way an ATS renders a grouped question: the question sits in the legend
    // and every button reads "Yes"/"No". Without one there is no legend to
    // read it from, so the composite join stands in for it.
    const radio = makeElement(
      field, field.legend ? option : `${option} | ${field.label}`);
    radio.name = field.name ?? field.label;
    radio.optionText = option;
    // A page can arrive with one button of a group already selected — a
    // resumed application, or the user's own click before pressing Fill.
    // `checked` cannot say that: it is declared per FIELD and a radio field
    // declares the whole GROUP, so setting it would tick every button and
    // model a group no browser can produce. `checkedOption` NAMES the one
    // that arrives selected, and leaves `checked` alone when it is absent.
    if (field.checkedOption !== undefined) {
      radio.checked = field.checkedOption === option;
    }
    return radio;
  });
});
const elements = groups.flat();
// A date section is identified by its id — `<widget>-dateSection<Part>-input`
// — which is how the engine tells one date from another. Derived from the
// declared widget and part so a fixture states the shape once.
spec.fields.forEach((field, i) => {
  // An explicit id/name, for the controls whose GROUPING is the thing under
  // test — an EEO checkbox question is several boxes sharing an id suffix.
  if (field.id) groups[i][0].id = field.id;
  if (field.name && field.kind !== "radio") groups[i][0].name = field.name;
  if (!field.dateWidget) return;
  const part = field.datePart ?? "Month";
  groups[i][0].id = `${field.dateWidget}-dateSection${part}-input`;
});
setElements(elements);

if (spec.rerenderAfterOption) {
  const source = elements.find(
    (element) => element._qid === spec.rerenderAfterOption.sourceQid);
  const targetIndex = spec.fields.findIndex(
    (field) => field.qid === spec.rerenderAfterOption.targetQid);
  if (!source || targetIndex < 0) throw new Error("invalid rerenderAfterOption spec");
  const originalTakeOption = source.takeOption.bind(source);
  source.takeOption = (text) => {
    originalTakeOption(text);
    const old = groups[targetIndex][0];
    old.isConnected = false;
    const field = spec.fields[targetIndex];
    const replacement = makeElement(field, field.label);
    replacement.id = old.id;
    replacement.name = old.name;
    groups[targetIndex][0] = replacement;
    const elementIndex = elements.indexOf(old);
    elements.splice(elementIndex, 1, replacement);
    notifyMutation();
  };
}

main(async () => {
  const out = {
    events: {}, values: {}, checked: {}, tokens: {}, qids: {}, attempts: {}, order: eventLog,
  };
  if (spec.mode === "questions") {
    // With a profile, the rule pass runs FIRST — the production order for
    // guided fill, and the only way ns.lastRuleAttempts (the known_value
    // feeder) carries real entries into collection.
    if (spec.profile) {
      await ns.fillFormFromProfile(
        spec.profile, spec.employment ?? [], spec.eeoEnabled === true,
        spec.skills ?? []);
    }
    if (spec.releasedLabels?.length) {
      const wanted = new Set(spec.releasedLabels);
      ns.lastRuleReleases = new WeakSet(spec.fields.flatMap((field, i) =>
        wanted.has(field.label) ? groups[i] : []));
    }
    out.collected = ns.collectOpenQuestions();
    out.routed = ns.routeOpenQuestions(
      out.collected.questions, spec.knownValues ?? {});
  } else if (spec.mode === "ai") {
    out.filled = await ns.fillAnswersByQid(spec.pairs);
  } else if (spec.mode === "guided") {
    out.results = await ns.guidedWrite(spec.items.map((item) => ({
      ...item,
      el: elements.find((element) => element._qid === item.qid) ?? null,
    })));
  } else {
    const result = await ns.fillFormFromProfile(
      spec.profile, spec.employment, spec.eeoEnabled === true, spec.skills,
      spec.consentForms === true);
    out.observations = result.observations;
    out.filled = result.filled;
    out.eeoFilled = result.eeoFilled;
    out.already = result.already;
  }
  spec.fields.forEach((field, i) => {
    const group = groups[i];
    out.events[field.label] = group.flatMap((el) => el.events);
    out.attempts[field.label] = group.reduce((count, el) => count + el.writeCount, 0);
    // A radio group's "value" is the option that ended up selected — "" when
    // none did, which is the same "nothing was written" a text field reports.
    out.values[field.label] = field.kind === "radio"
      ? (group.find((el) => el.checked)?.optionText ?? "")
      : group[0].value;
    // A checkbox holds nothing in `value`, so "did it end up ticked" is
    // reported separately — including for a box that arrived ticked and must
    // still be ticked afterwards.
    out.checked[field.label] = group.some((el) => el.checked === true);
    // …and a token input holds its answer in neither: the chips are the answer
    // and the box is empty. Reported for every field so a test can assert that
    // an ordinary control produced no tokens.
    out.tokens[field.label] = group.flatMap((el) => el.tokens);
    // The data-rt-qid collectOpenQuestions stamped on the control, if any.
    // A field that was never offered to the model carries none — which is the
    // property a deny-list test actually wants, because the tag is what
    // fillAnswersByQid resolves a field through.
    out.qids[field.label] = group.map((el) => el._qid).filter(Boolean);
  });
  emit(out);
});
"""


def norm_label(label: str) -> str:
    """Mirror of autofill.js's norm() — labelFor lowercases and collapses space."""
    return " ".join(label.lower().split())


def _run(tmp_path: Path, mode: str, fields: list[dict], **spec) -> dict:
    result = run_node(
        _DRIVER_JS, {"mode": mode, "fields": fields, **spec}, tmp_path,
        source=_content_source(FORM_MODULE_SOURCES),
    )
    # labelFor() lowercases, so observations come back normalized. Map them to
    # the labels the fixture declared so assertions read the way they were
    # written.
    declared = {norm_label(field["label"]): field["label"] for field in fields}
    for observation in result.get("observations", []):
        label = observation["label"]
        if label in declared:
            observation["label"] = declared[label]
            continue
        # A composite label — a radio button reports "<option> | <question> |
        # <group name>", because labelFor() joins every source it can find.
        # Attribute it to the question the fixture declared. Longest match wins
        # so a short declared label cannot steal a longer one's observation.
        contained = sorted(
            (d for d in declared if d in label), key=len, reverse=True
        )
        if contained:
            observation["label"] = declared[contained[0]]
    return result


def run_profile_fill(
    tmp_path: Path,
    *,
    fields: list[dict],
    profile: dict | None = None,
    employment: list | None = None,
    eeo_enabled: bool = False,
    skills: list | None = None,
    freeze_frames: bool = False,
    consent_forms: bool = False,
) -> dict:
    """Run fillFormFromProfile over `fields` and return what it reported.

    Each field is a dict: `label` and `kind` plus any FakeElement flag —
    `value`, `checked`, `clickCancelled`, `hidden`, `disabled`, `reverts`,
    `detaches`, `normalizesTo`, `tokenizes`, `type`.

    `tokenizes` makes the control a TOKEN input: Enter turns the text in its box
    into a chip and empties the box. `tokens` reports the chips.

    `dateWidget` makes the control a SECTION of a split date widget (Workday's
    month/year boxes), and `datePart` names which section ("Month"/"Year").
    Sections sharing a `dateWidget` are one date: blurring any of them while
    another is still empty makes the widget discard the blurred one, which is
    the live failure the deferred blur exists for.

    `listbox` gives the control a popup of `[role="option"]` nodes that render
    only once the control is engaged (focused, typed into, or clicked open),
    and `listboxDelay` (ms) makes them arrive late, the way a remote list does.
    `listboxVia: "aria-controls"` serves them through the attribute branch of
    `listboxOptions` instead of the bare `[role="option"]` fallback. A combobox
    with no `listbox` keeps the old behaviour: nothing renders and the poll
    loop times out into `combobox_snap_failed`.

    `type` is the raw HTML input type, for the native date controls
    (`{"kind": "text", "type": "month"}`) whose value format the browser fixes
    regardless of their label. `kind` stays "text" because that is what
    `kindOf()` reports for them, and therefore what telemetry records.

    `kind: "radio"` declares a whole group: `options` is a list of option TEXTS
    ("Yes", "No"), `name` optionally overrides the group name, and
    `checkedOption` names the one option that arrives already selected — the
    group's answer to `checked`, which cannot say it because it is per-field.
    The group's entry in `values` is the option that ended up selected, or "".

    `checked` reports the ticked state per field, for the controls that have
    one; `values` reports it for a radio group as the selected option text.
    """
    return _run(
        tmp_path,
        "profile",
        fields,
        profile=profile or {},
        employment=employment or [],
        eeoEnabled=eeo_enabled,
        skills=skills or [],
        freezeFrames=freeze_frames,
        consentForms=consent_forms,
    )


def run_ai_fill(
    tmp_path: Path, *, fields: list[dict], pairs: list[dict]
) -> dict:
    """Run fillAnswersByQid — the second copy of the commit ladder."""
    return _run(tmp_path, "ai", fields, pairs=pairs)


def run_guided_write(
    tmp_path: Path, *, fields: list[dict], items: list[dict],
    rerender_after_option: dict | None = None,
    freeze_frames: bool = False,
) -> dict:
    """Run the public value-directed, sequential write contract."""
    return _run(
        tmp_path,
        "guided",
        fields,
        items=items,
        rerenderAfterOption=rerender_after_option,
        freezeFrames=freeze_frames,
    )


def run_open_questions(
    tmp_path: Path, *, fields: list[dict], known_values: dict | None = None,
    profile: dict | None = None, harness: dict | None = None,
) -> dict:
    """Run collectOpenQuestions — the AI path's gate, one step before the LLM.

    `collected` is what it returned: `questions` (what is sent to the model),
    `excluded` (label/kind/reason for everything a gate turned away) and
    `host`. `qids` reports the data-rt-qid actually stamped on each field, so a
    test can assert a control was never even made addressable.

    `routed` is the essay / ChooseField split (`routeOpenQuestions`).
    `known_values` is an optional qid-or-label map of profile candidates that
    failed the rule pass, forwarded onto matching ChooseFields.

    A field may declare `legend`, which wraps it in a <fieldset> carrying that
    text — the shape where a radio button's own label ("Yes") and the question
    it answers are different strings.
    """
    controls = harness or {}
    extra = {} if not known_values else {"knownValues": known_values}
    if profile is not None:
        extra["profile"] = profile
        extra["eeoEnabled"] = controls.get("eeo_enabled", False)
        extra["employment"] = controls.get("employment", [])
    if controls.get("released_labels"):
        extra["releasedLabels"] = controls["released_labels"]
    return _run(tmp_path, "questions", fields, **extra)


def collected_labels(result: dict) -> list[str]:
    """The labels collectOpenQuestions is offering the model, in order."""
    return [q["label"] for q in result["collected"]["questions"]]


def rejection_reasons(result: dict) -> dict[str, str]:
    """label → reason for everything a gate turned away."""
    return {e["label"]: e["reason"] for e in result["collected"]["excluded"]}


def outcome_pairs(result: dict) -> list[tuple[str, str]]:
    """Label/outcome pairs in DOM order. A list, not a dict: repeated-block
    scenarios produce several observations for one label and the order is the
    thing under test."""
    return [(o["label"], o["outcome"]) for o in result["observations"]]


def outcome_for(result: dict, label: str) -> str:
    """The single outcome reported for `label`, asserting there is exactly one."""
    hits = [outcome for lab, outcome in outcome_pairs(result) if lab == label]
    assert len(hits) == 1, f"expected one observation for {label}, got {hits}"
    return hits[0]


# ---------- the control-shape fixture corpus ----------

# Metadata is provenance, not scenario. It is split from `scenario` in the file
# so the loader cannot mistake one for the other — a `"reproduces"` key sitting
# beside `"fields"` would either be forwarded into run_profile_fill as an
# unknown kwarg or silently dropped, and neither is a good way to find out you
# misspelled `"employment"`.
_FIXTURE_META_KEYS = frozenset(
    {"reproduces", "vendor", "changed_by", "telemetry_verbatim", "reconstructed"}
)
# Exactly the keyword arguments of run_profile_fill that a fixture may fix.
# `freeze_frames` is deliberately absent: it models a backgrounded tab, which
# is a property of the RUN, not of the control shape.
_FIXTURE_SCENARIO_KEYS = frozenset(
    {"fields", "profile", "employment", "eeo_enabled", "skills"}
)


# The directory holds two kinds of fixture so that ONE PII guard covers both:
# `detect_*` files are page shapes for the detection gate and carry a `page`,
# everything else is a control shape for the fill engine and carries a
# `scenario`. Split by filename rather than by peeking inside, so a misfiled
# fixture fails in its own corpus's validator — `read_fixture` rejects a `page`
# as an unknown top-level key and `read_detect_fixture` rejects a `scenario` —
# rather than being silently skipped by both.
_DETECT_PREFIX = "detect_"


def fixture_names() -> list[str]:
    """Every control-shape fixture, sorted. Iterate this rather than hardcoding
    a list, so a fixture added later is guarded and round-tripped for free.

    Defined by EXCLUSION, which is why every other corpus in this directory
    needs a prefix: a page shape landing in this list would be handed to
    `run_profile_fill` as a form."""
    return sorted(
        path.stem for path in FIXTURE_DIR.glob("*.json")
        if not path.stem.startswith(_DETECT_PREFIX)
    )


def fixture_paths() -> list[Path]:
    """The raw files, for the PII guard — which has to scan the TEXT, not the
    parsed scenario, or a real value pasted into a metadata string walks past
    it."""
    return sorted(FIXTURE_DIR.glob("*.json"))


def read_fixture(name: str) -> dict:
    """The whole fixture file, metadata included, validated.

    Validation lives here rather than in a test so a malformed fixture fails
    the moment it is loaded, naming itself, instead of surfacing as a confusing
    assertion three tasks later.
    """
    path = FIXTURE_DIR / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"no autofill fixture named {name!r}; have {fixture_names()}"
        )
    data = json.loads(path.read_text(encoding="utf-8"))

    unknown = set(data) - _FIXTURE_META_KEYS - {"scenario"}
    assert not unknown, f"{name}: unknown top-level keys {sorted(unknown)}"
    for key in ("reproduces", "changed_by", "telemetry_verbatim", "reconstructed"):
        assert key in data, f"{name}: fixture is missing {key!r}"
    scenario = data.get("scenario")
    assert isinstance(scenario, dict), f"{name}: scenario must be an object"
    unknown = set(scenario) - _FIXTURE_SCENARIO_KEYS
    assert not unknown, f"{name}: unknown scenario keys {sorted(unknown)}"

    fields = scenario.get("fields")
    assert isinstance(fields, list) and fields, f"{name}: fields must be non-empty"
    seen: set[str] = set()
    for i, field in enumerate(fields):
        assert isinstance(field, dict), f"{name}: field {i} is not an object"
        label = field.get("label")
        assert isinstance(label, str) and label, f"{name}: field {i} has no label"
        assert field.get("kind"), f"{name}: field {i} ({label!r}) has no kind"
        # The harness keys `values`, `events` and `checked` by label, and
        # `_run` remaps observations through a label→label dict. Two fields
        # sharing a label collapse into one entry and the second silently
        # disappears from every assertion made about it.
        assert label not in seen, f"{name}: duplicate field label {label!r}"
        seen.add(label)
    # Provenance has to be checkable, not merely claimed: a verbatim label that
    # no longer appears in `fields` means someone edited the reconstruction and
    # left the citation behind.
    for label in data["telemetry_verbatim"]:
        assert label in seen, (
            f"{name}: {label!r} is cited as verbatim telemetry but no field "
            f"carries it"
        )
    return data


def load_fixture(name: str) -> dict:
    """A fixture's scenario as run_profile_fill keyword arguments.

    Returns the kwargs rather than a bare field list so a consumer gets the
    profile and employment the shape needs along with the shape — a
    block-scoped employment test that had to restate two employment entries
    beside `fields=load_fixture(...)` would be restating exactly the structure
    the corpus exists to hold. Splat it, or use `run_fixture`:

        result = run_profile_fill(tmp_path, **load_fixture("oracle_opaque_year"))
    """
    scenario = read_fixture(name)["scenario"]
    return {
        "fields": scenario["fields"],
        "profile": scenario.get("profile") or {},
        "employment": scenario.get("employment") or [],
        "eeo_enabled": scenario.get("eeo_enabled", False),
        "skills": scenario.get("skills") or [],
    }


def run_fixture(tmp_path: Path, name: str, **overrides) -> dict:
    """Run a fixture. `overrides` REPLACE the fixture's values, never merge —
    a half-merged profile is a scenario nobody declared."""
    return run_profile_fill(tmp_path, **{**load_fixture(name), **overrides})


# ---------- the detection gate ----------

# The PAGE half of the fake DOM: a real (small) selector engine, kept separate
# from the form fakes above because it models a document rather than a set of
# controls. (It once served two drivers — the detection gate and the retired
# applied-detection watcher — which is why it is a standalone block and not
# inlined into `_DETECT_DRIVER_JS`.)
_PAGE_DOM_JS = r"""
// A real matcher for the selector subset these modules use — tag, #id and
// attribute tests — rather than a lookup keyed on the exact selector string.
// The gate IS its selectors, so a harness that answered them by string
// equality would be asserting that detect.js still contains the strings this
// file contains, and nothing about what they match.
const parseCompound = (text) => {
  let rest = text.trim();
  const compound = { tag: null, id: null, attrs: [] };
  const tag = /^[a-zA-Z][\w-]*/.exec(rest);
  if (tag) { compound.tag = tag[0].toLowerCase(); rest = rest.slice(tag[0].length); }
  while (rest.length) {
    const id = /^#([\w-]+)/.exec(rest);
    if (id) { compound.id = id[1]; rest = rest.slice(id[0].length); continue; }
    const attr = /^\[([\w-]+)(?:(\*?=)(?:"([^"]*)"|([^\]\s]+))(\s+i)?)?\]/.exec(rest);
    // Loud on purpose. An unsupported fragment — a descendant combinator, a
    // pseudo-class — would otherwise match nothing and read as "the page has
    // no such element", turning a detection test green for the wrong reason.
    if (!attr) throw new Error(`selector this harness cannot match: ${text}`);
    compound.attrs.push({
      name: attr[1],
      op: attr[2] ?? null,
      value: attr[3] !== undefined ? attr[3] : (attr[4] ?? null),
      fold: attr[5] !== undefined,
    });
    rest = rest.slice(attr[0].length);
  }
  return compound;
};

const matchesCompound = (node, compound) => {
  if (compound.tag !== null && node.tag !== compound.tag) return false;
  if (compound.id !== null && node.attrs.id !== compound.id) return false;
  return compound.attrs.every(({ name, op, value, fold }) => {
    const actual = node.attrs[name];
    if (actual === undefined || actual === null) return false;
    if (op === null) return true;
    const [have, want] = fold
      ? [String(actual).toLowerCase(), value.toLowerCase()]
      : [String(actual), value];
    return op === "*=" ? have.includes(want) : have === want;
  });
};

const matchesSelector = (node, selector) =>
  selector.split(",").some((part) => matchesCompound(node, parseCompound(part)));
"""

# `detectPage` reads things the control-shaped DOM above cannot express: the
# URL, the ld+json scripts, a handful of attribute selectors and the body text.
# So this driver installs its own `document`/`location` over the prelude's
# rather than teaching one fake DOM two jobs — the fill drivers are untouched,
# and neither model has to carry a branch for the other's queries.
_DETECT_DRIVER_JS = _PAGE_DOM_JS + r"""
const page = spec.page;

// A JSON-LD document is built here, from a declared SHAPE, because a fixture
// may not contain one: the corpus PII guard rejects "@" outright (it is how it
// catches an email address), and every JSON-LD key starts with one. So the
// fixture says "graph" and the harness writes the @graph.
const buildJsonLd = (entry) => {
  if (entry.malformed === true) return "{ this is not json";
  const nodes = (entry.types ?? []).map((type) => ({ "@type": type }));
  if (entry.shape === "array") return JSON.stringify(nodes);
  if (entry.shape === "graph") {
    return JSON.stringify({ "@context": "https://schema.org", "@graph": nodes });
  }
  if (nodes.length !== 1) {
    throw new Error(`the "bare" shape holds exactly one node, got ${nodes.length}`);
  }
  return JSON.stringify({ "@context": "https://schema.org", ...nodes[0] });
};

const makeNode = ({ tag, attrs = {}, text = "" }) => ({
  tag: tag.toLowerCase(),
  attrs,
  textContent: text,
  // An input carries its visible text in `value`, a button between its tags.
  // Both are declared as attributes in a fixture, so both are read off here.
  value: attrs.value ?? "",
});

const nodes = [
  ...(page.jsonLd ?? []).map((entry) => makeNode({
    tag: "script",
    attrs: { type: "application/ld+json" },
    text: buildJsonLd(entry),
  })),
  ...(page.elements ?? []).map(makeNode),
];

// Every read the gate makes of the page, in order. What Tier 0 costs on a page
// it cannot help with is a behaviour of this module, not an implementation
// detail — "no DOM scan beyond a single querySelector" is only assertable if
// the reads are counted.
const queries = [];
global.document = {
  querySelector: (selector) => {
    queries.push(selector);
    return nodes.find((node) => matchesSelector(node, selector)) ?? null;
  },
  querySelectorAll: (selector) => {
    queries.push(selector);
    return nodes.filter((node) => matchesSelector(node, selector));
  },
  // `textContent` only, deliberately. The gate reads the page's text that way
  // rather than through `innerText` — see detect.js for why — and a body that
  // also answered `innerText` would let that decision be reversed without a
  // test noticing.
  //
  // A page's `text` is a SEPARATE CHANNEL from its elements: this returns what
  // the fixture declared and nothing an element carries, where a browser would
  // return the concatenation. So a fixture cannot express "the wording lives
  // inside a <label>" — declare it in `text` as well when that is the shape
  // under test. Kept flat because composing it would mean modelling a tree,
  // and the gate never walks one.
  body: {
    get textContent() { queries.push("body.textContent"); return page.text ?? ""; },
  },
};
global.location = { href: page.url, hostname: new URL(page.url).hostname };

main(async () => {
  const ns = loadModules();
  const detected = ns.detectPage();
  // The return contract, pinned where every detection test inherits it.
  const keys = Object.keys(detected).sort().join(",");
  if (keys !== "form,score,signals,tier") {
    throw new Error(`detectPage must return {tier, score, signals, form}; got {${keys}}`);
  }
  emit({ ...detected, queries });
});
"""


_DETECT_META_KEYS = frozenset({"reproduces", "vendor", "reconstructed"})
_DETECT_PAGE_KEYS = frozenset({"url", "jsonLd", "text", "elements"})
_DETECT_ELEMENT_KEYS = frozenset({"tag", "attrs", "text"})
_DETECT_JSONLD_KEYS = frozenset({"shape", "types", "malformed"})
_DETECT_JSONLD_SHAPES = frozenset({"bare", "array", "graph"})


def run_detect(tmp_path: Path, *, page: dict) -> dict:
    """Run detectPage against `page` and return `{tier, score, signals, queries}`.

    A page is a dict of:

    * `url` — what `location.href`/`location.hostname` report;
    * `elements` — `{"tag", "attrs", "text"}` specs, matched by a real (small)
      selector engine, so `attrs` are the page's actual attributes;
    * `jsonLd` — `{"shape": "bare"|"array"|"graph", "types": [...]}` entries,
      each becoming one `<script type="application/ld+json">`. The shape is
      declared rather than written out because the corpus PII guard rejects
      `@`, and `@type`/`@graph` are made of it. `{"malformed": true}` makes one
      script hold text that is not JSON.
    * `text` — what `document.body` reports as its text.

    `queries` is every selector the gate asked for, in order, plus
    `body.textContent` when it read the page's text — cost is a behaviour of
    this module, so the reads are counted rather than assumed.
    """
    return run_node(
        _DETECT_DRIVER_JS, {"page": page}, tmp_path,
        source=_content_source(DETECTION_MODULE_SOURCES),
    )


def detect_fixture_names() -> list[str]:
    """Every detection fixture, sorted. Same reason as `fixture_names`."""
    return sorted(path.stem for path in FIXTURE_DIR.glob(f"{_DETECT_PREFIX}*.json"))


def read_detect_fixture(name: str) -> dict:
    """A detection fixture, metadata included, validated.

    Its metadata is provenance, like the control-shape corpus's, minus
    `telemetry_verbatim`: autofill telemetry records field LABELS, and a page
    shape has none, so citing it would be citing a source that cannot say
    anything about this fixture. `reconstructed` therefore carries the whole
    provenance claim and has to name where every part of the shape came from.
    """
    path = FIXTURE_DIR / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"no detection fixture named {name!r}; have {detect_fixture_names()}"
        )
    data = json.loads(path.read_text(encoding="utf-8"))

    unknown = set(data) - _DETECT_META_KEYS - {"page"}
    assert not unknown, f"{name}: unknown top-level keys {sorted(unknown)}"
    for key in sorted(_DETECT_META_KEYS):
        assert key in data, f"{name}: fixture is missing {key!r}"
    page = data.get("page")
    assert isinstance(page, dict), f"{name}: page must be an object"
    unknown = set(page) - _DETECT_PAGE_KEYS
    assert not unknown, f"{name}: unknown page keys {sorted(unknown)}"
    assert isinstance(page.get("url"), str) and page["url"], f"{name}: page has no url"

    for i, element in enumerate(page.get("elements") or []):
        assert isinstance(element, dict), f"{name}: element {i} is not an object"
        unknown = set(element) - _DETECT_ELEMENT_KEYS
        assert not unknown, f"{name}: element {i} has unknown keys {sorted(unknown)}"
        assert element.get("tag"), f"{name}: element {i} has no tag"
    for i, entry in enumerate(page.get("jsonLd") or []):
        assert isinstance(entry, dict), f"{name}: jsonLd {i} is not an object"
        unknown = set(entry) - _DETECT_JSONLD_KEYS
        assert not unknown, f"{name}: jsonLd {i} has unknown keys {sorted(unknown)}"
        if entry.get("malformed") is not True:
            assert entry.get("shape") in _DETECT_JSONLD_SHAPES, (
                f"{name}: jsonLd {i} needs a shape in "
                f"{sorted(_DETECT_JSONLD_SHAPES)}"
            )
    return data


def load_detect_page(name: str) -> dict:
    """A detection fixture's page, ready to splat into `run_detect`."""
    return read_detect_fixture(name)["page"]


def run_detect_fixture(tmp_path: Path, name: str) -> dict:
    """Run a detection fixture. Vary it by loading the page and editing it —
    `{**load_detect_page(name), "jsonLd": [...]}` — so the variation is visible
    at the call site rather than buried in an override dict."""
    return run_detect(tmp_path, page=load_detect_page(name))


def run_node(driver_js: str, spec: dict, tmp_path: Path, source: str | None = None) -> dict:
    """Run `driver_js` against the fake DOM and return what it emitted.

    `source` overrides what `extract` reads. It exists for `extension/sw.js`,
    which is NOT in EXTENSION_SOURCES: that list is the files the page
    functions may live in, and the service worker never runs in a page.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")

    harness = tmp_path / "extension-harness.cjs"
    harness.write_text(PRELUDE_JS + driver_js, encoding="utf-8")
    spec_file = tmp_path / "extension-harness-spec.json"
    spec_file.write_text(json.dumps(spec), encoding="utf-8")
    # The source may span several files now, so what argv[2] names is the
    # CONCATENATION rather than one of them. Spilling it to a file keeps
    # PRELUDE_JS's `fs.readFileSync(process.argv[2])` contract intact — and
    # keeps the text off the command line, which has a length limit.
    source_file = tmp_path / "extension-source.js"
    source_file.write_text(extension_source() if source is None else source, encoding="utf-8")

    completed = subprocess.run(
        [node, str(harness), str(source_file), str(spec_file)],
        check=False,
        capture_output=True,
        text=True,
        # Belt and braces for a genuinely wedged process (a busy loop, a timer
        # that keeps rescheduling itself). It does NOT catch a promise that
        # never settles: node drains its event loop and exits 0, which is what
        # the empty-stdout assert below is for.
        timeout=60,
    )
    # check=False so a broken harness surfaces its JS stack trace instead of a
    # bare non-zero exit status.
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout, (
        "driver produced no output: a promise in the injected function never "
        f"settled, so emit() was never reached.\nstderr:\n{completed.stderr}"
    )
    return json.loads(completed.stdout)
