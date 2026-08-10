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
// `fileInputs` is a list of {visible} — enough for attach, which only reads
// `accept`, the box, and `files`.
const fileInputs = (spec.fileInputs ?? []).map((f) => ({
  getAttribute: () => null,
  offsetWidth: f.visible ? 120 : 0,
  offsetHeight: f.visible ? 24 : 0,
  getClientRects: () => (f.visible ? [{}] : []),
  parentElement: null,
  files: null,
  dispatchEvent: () => {},
}));
global.document = {
  title: "",
  body: { innerText: "" },
  querySelectorAll: (sel) => (String(sel).includes("file") ? fileInputs : []),
  querySelector: () => null,
  createElement: () => ({ set innerHTML(_v) {}, get innerText() { return ""; } }),
};
// Node has File but no DataTransfer; attach_resume_pdf builds one before it
// ever looks at the DOM, so the ALLOWED path needs it to reach the loop.
global.DataTransfer = class { constructor() { this.items = { add: () => {} }; this.files = []; } };
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

main(async () => {
  const handler = ns.pageHandlers[spec.type];
  const data = await handler({
    type: spec.type, profile: { personal: { email: "a@b.test" } }, employment: [],
    skills: [], pairs: [], b64: "", filename: "resume.pdf",
  });
  emit({ calls, data });
});
"""


def _run(tmp_path, *, type_, top_frame, form=False, detect_throws=False, file_inputs=()):
    return run_node(
        _GATE_DRIVER_JS,
        {
            "type": type_, "topFrame": top_frame, "form": form,
            "detectThrows": detect_throws, "fileInputs": list(file_inputs),
        },
        tmp_path,
        source=page_runtime_source(),
    )


FAN_OUT_TYPES = ["profile_fill", "collect_open_questions", "fill_answers"]


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


def test_extract_job_posting_is_not_gated(tmp_path):
    """It reads the page it already runs on and returns nothing derived from the
    user, so gating it would cost the JSON-LD walk for no privacy gain."""
    out = _run(tmp_path, type_="extract_job_posting", top_frame=False, form=False)

    assert out["data"]["url"] is not None
