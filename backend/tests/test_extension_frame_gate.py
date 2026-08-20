"""The extension's fan-out reaches every frame; this is what stops it filling ads.

`sw.js` authorizes a broadcast at the SENDER — top frame only, same tab,
allow-listed message type — but its targets come from
`chrome.webNavigation.getAllFrames`, i.e. every frame in the tab. A job page
carries ad, analytics and chat-widget iframes, and the ISOLATED world does not
help: it protects the message in transit, not the DOM the fill engine then
writes into. A frame owns its DOM, so a profile value written into a
third-party frame's input is readable by that frame's own script at once.

`agent.js` therefore gates the four fan-out handlers on
`frameMayReceiveUserData()`. These tests drive the real modules through that
boundary (`ns.pageHandlers`), because the gate is about frame IDENTITY and page
EVIDENCE rather than about any one field rule — the form drivers cannot reach
it.

Added 2026-08-04 with the extension security audit (findings E1 and E2).
"""

import pytest

from tests.extension_harness import page_runtime_source, run_node


# Loads the real dependency-ordered modules through agent.js, then replaces the
# two collaborators the gate consults so each test states one thing: was this
# frame allowed, and did the engine get called. `chrome` is stubbed because
# agent.js registers a message listener as it loads.
_GATE_DRIVER_JS = """
global.chrome = {
  runtime: { id: "test-extension", onMessage: { addListener() {} } },
};
// `fileInputs` is a list of {visible, accept?, refuses?, discards?, detaches?}
// — enough for attach, which reads `accept`, the box, `files` and `isConnected`.
//
// `files` IS A REAL PROPERTY, not a null that swallows the assignment, and that
// is load-bearing rather than tidy: `attachResumePdf` re-reads `input.files`
// after writing it and counts only the boxes that really took the file, so a
// fake that reported nothing back would make every attach count zero — and a
// fake that ACCEPTED everything would make the readback untestable. `refuses`
// models the case the readback exists for: a control whose `files` setter does
// nothing (a framework-owned input, a redefined property).
const fileInputs = (spec.fileInputs ?? []).map((f) => {
  const input = {
    getAttribute: (name) => (name === "accept" ? (f.accept ?? null) : null),
    offsetWidth: f.visible ? 120 : 0,
    offsetHeight: f.visible ? 24 : 0,
    getClientRects: () => (f.visible ? [{}] : []),
    parentElement: null,
    // A REAL PROPERTY, like `files` below and for the same reason: the readback
    // refuses to count a node the widget re-rendered away, so a fake without
    // one reports `undefined` and every attach counts zero. `detaches` models
    // the uploader that replaces its own input after taking the file.
    isConnected: true,
    dispatchEvent: () => {},
  };
  let held = null;
  Object.defineProperty(input, "files", {
    get() { return held; },
    set(value) {
      if (f.refuses) return;
      held = value;
      // The controlled uploader this settle exists for: it takes the file and
      // throws it away on a LATER render, which a same-tick read cannot see.
      if (f.discards) setTimeout(() => { held = null; }, 20);
      if (f.detaches) setTimeout(() => { input.isConnected = false; }, 20);
    },
  });
  return input;
});
global.document = {
  title: "",
  body: { innerText: "" },
  querySelectorAll: (sel) => (String(sel).includes("file") ? fileInputs : []),
  querySelector: () => null,
  createElement: () => ({ set innerHTML(_v) {}, get innerText() { return ""; } }),
};
// Node has File but no DataTransfer; attach_resume_pdf builds one before it
// ever looks at the DOM, so the ALLOWED path needs it to reach the loop.
// A DataTransfer that really COLLECTS, for the reason the `files` property
// above is real: `attachResumePdf` checks `input.files?.length === 1` — exactly
// one file, the one we put in — so a stub whose `add` dropped the file on the
// floor would report every attach as refused.
global.DataTransfer = class {
  constructor() { this.files = []; this.items = { add: (file) => this.files.push(file) }; }
};
global.location = { ...global.location, href: "https://jobs.example.test/x" };
global.window.top = spec.topFrame ? global.window : { other: true };
global.window.self = global.window;

eval(source);

const ns = global.window.careerStudioCompanion;
const calls = [];
ns.detectPage = () => {
  if (spec.detectThrows) throw new Error("no body in this frame yet");
  return { tier: spec.form ? "B" : "none", score: spec.form ? 2 : 0, signals: [], form: spec.form };
};
ns.fillFormFromProfile = (...args) => {
  calls.push(["fillFormFromProfile", args.length]);
  return { filled: [{ label: "Email" }], eeoFilled: [], corrected: [], already: [], seen: 1,
           observations: [] };
};
ns.collectOpenQuestions = () => { calls.push(["collectOpenQuestions", 0]); return { questions: [{ qid: "q1" }], excluded: [], host: "x" }; };
ns.fillAnswersByQid = () => { calls.push(["fillAnswersByQid", 0]); return ["q1"]; };
ns.applyGuidedChoices = () => { calls.push(["applyGuidedChoices", 0]); return []; };

main(async () => {
  const handler = ns.pageHandlers[spec.type];
  const data = await handler({
    type: spec.type, profile: { personal: { email: "a@b.test" } }, employment: [],
    skills: [], pairs: [], b64: "", filename: "resume.pdf",
    // Only when the fixture states one — `undefined` is the shape the floating
    // card sends, and it must keep meaning "unchecked".
    ...(spec.expect === null ? {} : { expect: spec.expect }),
  });
  emit({ calls, data });
});
"""


def _run(tmp_path, *, type_, top_frame, form=False, detect_throws=False, file_inputs=(),
         expect=None):
    return run_node(
        _GATE_DRIVER_JS,
        {
            "type": type_, "topFrame": top_frame, "form": form,
            "detectThrows": detect_throws, "fileInputs": list(file_inputs),
            "expect": expect,
        },
        tmp_path,
        source=page_runtime_source(),
    )


FAN_OUT_TYPES = ["profile_fill", "collect_open_questions", "fill_answers", "guided_write"]


@pytest.mark.parametrize("type_", FAN_OUT_TYPES)
def test_the_top_frame_is_always_allowed(tmp_path, type_):
    """The frame the user is looking at, whose button they clicked.

    Never gated on detection: the widget also mounts on pages recognised only by
    Tier C (`/api/jobs/match`), which short-circuits `detectPage` entirely, so a
    detection gate here would break autofill on exactly those pages.
    """
    out = _run(tmp_path, type_=type_, top_frame=True, form=False)

    assert out["calls"] != [], f"{type_} did not reach the engine in the top frame"


@pytest.mark.parametrize("type_", FAN_OUT_TYPES)
def test_a_subframe_without_form_evidence_is_refused(tmp_path, type_):
    """The ad iframe case. `detectPage().form` is false, so the engine never runs."""
    out = _run(tmp_path, type_=type_, top_frame=False, form=False)

    assert out["calls"] == [], f"{type_} ran the engine in an unqualified subframe"


@pytest.mark.parametrize("type_", FAN_OUT_TYPES)
def test_a_subframe_holding_an_application_form_is_allowed(tmp_path, type_):
    """The reason fan-out exists: Greenhouse and Lever put the form in a subframe."""
    out = _run(tmp_path, type_=type_, top_frame=False, form=True)

    assert out["calls"] != [], f"{type_} was refused in a real application subframe"


def test_a_refused_frame_returns_an_empty_result_not_an_error(tmp_path):
    """`broadcastToFrames` turns a throw into a per-frame `error`, which the
    widget's reconciliation strip would report as "didn't stick" for a frame
    that was never a target. Nothing to do here is not a failure."""
    out = _run(tmp_path, type_="profile_fill", top_frame=False, form=False)

    assert out["data"]["filled"] == []
    assert out["data"]["seen"] == 0


def test_the_gate_fails_closed_when_detection_throws(tmp_path):
    """A frame with no body yet still must not receive the profile."""
    out = _run(tmp_path, type_="profile_fill", top_frame=False, detect_throws=True)

    assert out["calls"] == []


def test_attach_is_gated_by_frame(tmp_path):
    """A file input's `files` is readable by the page with no submit and no
    gesture, so an unqualified frame receiving the PDF is a silent copy of the
    whole résumé — name, address, phone and history."""
    visible = [{"visible": True}]
    refused = _run(tmp_path, type_="attach_resume_pdf", top_frame=False, form=False,
                   file_inputs=visible)
    allowed = _run(tmp_path, type_="attach_resume_pdf", top_frame=True, file_inputs=visible)

    assert refused["data"] == 0, "an unqualified subframe received the resume PDF"
    assert allowed["data"] == 1, "the real uploader did not receive the resume PDF"


def test_attach_skips_an_invisible_file_input(tmp_path):
    """Even in an allowed frame. A real uploader is on screen when you are asked
    to upload; an off-screen one is a collector."""
    out = _run(tmp_path, type_="attach_resume_pdf", top_frame=True,
               file_inputs=[{"visible": False}, {"visible": True}])

    assert out["data"] == 1


def test_an_input_that_refuses_the_file_is_not_counted_as_attached(tmp_path):
    """THE READBACK. `input.files = …` is an assignment a page can refuse — a
    framework-owned control, a redefined property — and the old loop counted the
    attempt. The count is the whole of what the side panel tells the user
    ("Attached … to this page"), so counting a write that did not land is the
    surface claiming an upload that is not there."""
    out = _run(tmp_path, type_="attach_resume_pdf", top_frame=True,
               file_inputs=[{"visible": True, "refuses": True}, {"visible": True}])

    assert out["data"] == 1


def test_a_box_that_appeared_since_the_offer_refuses_the_whole_write(tmp_path):
    """THE REFUSAL, CHECKED WHERE IT CAN HOLD.

    The side panel offers an attach only when the page reports exactly ONE box
    and refuses with a sentence when it reports several — but that count is
    frame 0's, taken at DETECT time, while the write runs at PRESS time in every
    gated frame. Workday reveals a cover-letter uploader when the résumé section
    expands, so the page moves from one box to two in between; without this the
    write put the résumé in BOTH and the report was honest about it afterwards,
    which is not the same as the refusal having held.

    WHOLE, not partial: a frame that has grown a box cannot know which of them
    the offer was about, and writing to "the one that was there before" is the
    guess the refusal exists to prevent.
    """
    out = _run(tmp_path, type_="attach_resume_pdf", top_frame=True, expect=1,
               file_inputs=[{"visible": True}, {"visible": True}])

    assert out["data"] == 0


def test_a_page_that_still_looks_the_way_it_did_takes_the_file(tmp_path):
    """The other direction, without which the test above passes on an engine
    that refuses everything."""
    out = _run(tmp_path, type_="attach_resume_pdf", top_frame=True, expect=1,
               file_inputs=[{"visible": True}])

    assert out["data"] == 1


def test_a_caller_that_claims_nothing_is_checked_against_nothing(tmp_path):
    """`expect` ABSENT MEANS UNCHECKED, which is what keeps the floating card on
    the behaviour it has always had: it makes its user no promise about how many
    boxes it found, so it passes no claim and none is invented for it."""
    out = _run(tmp_path, type_="attach_resume_pdf", top_frame=True,
               file_inputs=[{"visible": True}, {"visible": True}])

    assert out["data"] == 2


def test_a_claim_of_zero_boxes_still_refuses(tmp_path):
    """`Number.isInteger`, not a truthiness test. `expect: 0` is a real claim —
    "this page had no box" — and folding it into the unchecked branch would make
    the one count that should never write the one count that always does."""
    out = _run(tmp_path, type_="attach_resume_pdf", top_frame=True, expect=0,
               file_inputs=[{"visible": True}])

    assert out["data"] == 0


def test_a_box_that_discards_the_file_on_a_later_render_is_not_counted(tmp_path):
    """`valueHolds`' banner, applied to the one writer that did not have it.

    Reading `input.files` on the tick that assigned it reads back our own write
    and says "stuck" almost always. A controlled uploader (React/Angular) that
    rejects the file does it on a LATER render — exactly as a controlled text
    input does — so the count was claiming uploads that were not there.
    """
    out = _run(tmp_path, type_="attach_resume_pdf", top_frame=True,
               file_inputs=[{"visible": True, "discards": True}, {"visible": True}])

    assert out["data"] == 1


def test_a_box_the_widget_re_rendered_away_is_not_counted(tmp_path):
    """`valueHolds`' FIRST check, and the same argument: a detached node keeps
    whatever we assigned it forever, so `files` alone would report a box the
    user cannot see. The known cost is written on `attachResumePdf` — an
    uploader that accepts the file and then replaces its own input is
    under-counted, and the panel then says "attach it by hand" over a page where
    it worked. That is the safe direction; over-counting is the claim this
    readback exists to stop.
    """
    out = _run(tmp_path, type_="attach_resume_pdf", top_frame=True,
               file_inputs=[{"visible": True, "detaches": True}, {"visible": True}])

    assert out["data"] == 1


def test_attach_skips_a_box_that_wants_something_other_than_a_pdf(tmp_path):
    """A box declaring `accept="image/*"` is the profile-photo uploader, not the
    résumé one. An input declaring NOTHING still passes — drag-and-drop
    uploaders routinely declare no `accept` at all."""
    out = _run(tmp_path, type_="attach_resume_pdf", top_frame=True,
               file_inputs=[{"visible": True, "accept": "image/png,image/jpeg"},
                            {"visible": True, "accept": "application/pdf"},
                            {"visible": True}])

    assert out["data"] == 2


def test_extract_job_posting_is_not_gated(tmp_path):
    """It reads the page it already runs on and returns nothing derived from the
    user, so gating it would cost the JSON-LD walk for no privacy gain."""
    out = _run(tmp_path, type_="extract_job_posting", top_frame=False, form=False)

    assert out["data"]["url"] is not None


def test_detect_page_answers_the_verdict_and_nothing_of_the_page(tmp_path):
    """The side panel's only way to ask "does this tab hold a form?" — it runs
    in no page, so detection is not a function it can call.

    FOUR keys, pinned. `detectPage` also returns `signals`, which names the
    selectors, hosts and phrases that fired on this document; that is page
    content by another route, and the panel has no use for it. The smallest
    honest answer is the one that crosses the boundary.

    `fileInputs` is the fourth and it is the same KIND of fact as the other
    three — a count of controls this document renders, nothing derived from the
    user — which is what keeps this handler ungated. It is a COUNT and never the
    inputs: what the panel decides with it is whether to OFFER an attach.

    Ungated for `extract_job_posting`'s reason and no other: it reads the frame
    it already runs in and returns nothing derived from the user.
    """
    out = _run(tmp_path, type_="detect_page", top_frame=False, form=True)

    assert set(out["data"]) == {"tier", "form", "score", "fileInputs"}
    assert out["data"]["form"] is True
    # …and the verdict is the page's own, not re-derived from `score` here.
    assert _run(tmp_path, type_="detect_page", top_frame=True, form=False)["data"] == {
        "tier": "none", "form": False, "score": 0, "fileInputs": 0}


def test_the_offer_counts_exactly_the_boxes_the_attach_would_write_to(tmp_path):
    """ONE DEFINITION of "a box a résumé could go into", asserted as the
    agreement it is: the panel offers an attach on the strength of this count
    and the write picks its targets by the same predicate, so a count taken any
    other way would be an offer about a page other than the one being written
    to. Driven over a page whose boxes are deliberately mixed — one hidden, one
    wanting images, two real — so agreement cannot be a coincidence of both
    answering "all of them"."""
    boxes = [{"visible": False},
             {"visible": True, "accept": "image/png"},
             {"visible": True, "accept": "application/pdf"},
             {"visible": True}]
    counted = _run(tmp_path, type_="detect_page", top_frame=True, form=True,
                   file_inputs=boxes)["data"]["fileInputs"]
    written = _run(tmp_path, type_="attach_resume_pdf", top_frame=True,
                   file_inputs=boxes)["data"]

    assert counted == written == 2
