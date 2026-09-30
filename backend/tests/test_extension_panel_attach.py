"""The Fill stage's ATTACH beyond the button: the offer following a wizard's
in-page steps, and Autofill attaching the resume itself.

A fill sub-concern with its OWN drivers, which is the trigger
`test_extension_panel.py`'s map names for cutting it out of
`test_extension_panel_fill.py`. The button's own contract (the offer, the
press, the proof, the refusals) stays there; this file reuses its world
(`_attach`) and adds two drivers: a wizard step changing the tab's url, and
an Autofill run that ends with an attach.
"""

import pytest

from tests.extension_fixtures import LIGHTNING_APPLY_URL, entry
from tests.extension_harness import run_node
from tests.extension_panel_harness import (
    BASE_RESUMES,
    PANEL_SOURCE,
    SCORES,
    SETTINGS_REPLY,
    _armed_entry,
    _by_class,
    _PANEL_FAKES_JS,
    _reply,
)
from tests.test_extension_panel_fill import (
    _LOOP_DRIVER_JS,
    _TAILORED_DETAIL,
    ATTACH_NONE,
    ATTACH_ONE,
    COLLECT_FRAMES,
    LOOP_REPORT,
    PROFILE_FRAMES,
    _attach,
    _attach_text,
    _rows_of,
)

# ---------- the offer follows the wizard's steps ----------
#
# THE LIVE BUG (CarMax Workday, 2026-09-30): My Experience, which has a
# Resume/CV upload box, showed no attach offer; the NEXT step, Voluntary
# Disclosures, which has none, did. One step late in both directions.
#
# WHY: a Workday step change is a same-document url change, so `tabs.onUpdated`
# rebinds the panel at once, while the page still shows the step being LEFT.
# Every Workday apply step answers `form: true` (the apply route), so the retry
# ladder, which only runs on a no, never started: the upload count was taken
# once, off the old step's DOM, and held for the whole new step.

_STEP_DRIVER_JS = _PANEL_FAKES_JS + r"""
loadModules();
const attachBox = () => withClass(REGIONS.rail, "attach")[0] ?? null;
main(async () => {
  await settle();
  const offered = [attachBox() !== null];
  for (const url of spec.steps) {
    await onUpdated(7, { url });
    await settle();
    offered.push(attachBox() !== null);
  }
  emit({ offered, settled: regions(), sent, delays });
});
"""

STEP_2 = f"{LIGHTNING_APPLY_URL}/step2"


def _detect(file_inputs):
    return _reply({"tier": "B", "form": True, "score": 2, "fileInputs": file_inputs})


def _detects(out):
    return [msg for msg in out["sent"] if msg["type"] == "panel_frame0"
            and (msg.get("message") or {}).get("type") == "detect_page"]


def test_the_offer_appears_once_the_step_with_the_upload_box_has_rendered(tmp_path):
    """My Information (no box) → My Experience (one box). The first read after
    the url change sees the step being left; a later look sees the box."""
    out = _attach(tmp_path, driver=_STEP_DRIVER_JS, steps=[STEP_2],
                  page={"detect_page": [_detect(0), _detect(0), _detect(1)]})
    assert out["offered"] == [False, True]
    assert "tailored-resume.pdf" in _attach_text(out["settled"])


def test_the_offer_goes_once_the_step_without_one_has_rendered(tmp_path):
    """My Experience (one box) → Voluntary Disclosures (none): the other half
    of the live report, where the panel offered an attach on a step with
    nowhere to put it."""
    out = _attach(tmp_path, driver=_STEP_DRIVER_JS, steps=[STEP_2],
                  page={"detect_page": [_detect(1), _detect(1), _detect(0)]})
    assert out["offered"] == [True, False]


def test_a_step_change_looks_again_on_the_ladders_schedule_and_then_stops(tmp_path):
    """Bounded like every other re-ask here: the first look and three more on
    `PAGE_RETRY_MS`, then nothing."""
    out = _attach(tmp_path, driver=_STEP_DRIVER_JS, steps=[STEP_2],
                  page={"detect_page": [_detect(0)]})
    # One at boot, then one at the url change and three on the schedule.
    assert len(_detects(out)) == 5
    assert len(out["delays"]) == 3
    assert out["delays"] == sorted(out["delays"])


def test_a_panel_opened_on_a_settled_page_still_asks_once(tmp_path):
    """Opening the panel, or switching to the tab, reads a page that is already
    there, so a yes at once is still the whole answer there."""
    out = _attach(tmp_path, driver=_STEP_DRIVER_JS, steps=[],
                  page={"detect_page": [_detect(1)]})
    assert len(_detects(out)) == 1
    assert out["delays"] == []
    assert _by_class(out["settled"]["rail"], "attach") != []


# ---------- Autofill attaches the resume ----------
#
# THE OWNER'S REQUEST (2026-09-30): "can't AI autofill detect the resume upload
# field and trigger an upload there?" Attach resume was a separate press so a
# document never went out without one; the press is now Autofill's. It
# attaches only the application's tailored PDF (the button's own source), only
# to a page whose one upload box reads as a resume box (`uploads`, from a
# FRESH detect after the run), never over a file already there, once per run
# and AFTER the fields, and it reports what it did as its own line.

EMPTY_RESUME_BOX = {"kind": "resume", "occupied": False}
ATTACHED = "Resume attached: tailored-resume.pdf. Check the upload before you submit."

_AUTOFILL_DRIVER_JS = _PANEL_FAKES_JS + r"""
loadModules();
const attachButton = () => {
  const box = withClass(REGIONS.rail, "attach")[0];
  return box ? withClass(box, "save")[0] ?? null : null;
};
const autofill = async () => {
  withClass(REGIONS.foot, "cta")[0].click();
  await settle();
  const during = regions();
  release();
  await settle();
  return during;
};
main(async () => {
  await settle();
  const during = await autofill();
  let again = null;
  if (spec.again) {
    // A run that finished ticked Fill: reopen it, as a wizard's next page does.
    const door = findById(REGIONS.rail, "stg-open-fill");
    if (door) { door.click(); await settle(); }
    again = await autofill();
  }
  emit({ during, again, settled: regions(), sent, writes, broadcasts,
         button: attachButton() ? { disabled: attachButton().disabled } : null });
});
"""


def _page(*uploads, file_inputs=None):
    verdict = {"tier": "B", "form": True, "score": 2,
               "fileInputs": len(uploads) if file_inputs is None else file_inputs}
    if file_inputs is None:
        verdict["uploads"] = list(uploads)
    return {"detect_page": _reply(verdict)}


def _autofill(tmp_path, *uploads, **spec):
    spec.setdefault("page", _page(*uploads))
    # Fields left open, so the step stays on Fill and its body is on screen.
    spec.setdefault("frames", {"profile_fill": PROFILE_FRAMES,
                               "collect_open_questions": COLLECT_FRAMES,
                               "guided_write": True})
    return _attach(tmp_path, driver=_AUTOFILL_DRIVER_JS, **spec)


def _attach_asks(out):
    return [msg for msg in out["sent"] if msg["type"] == "attach_pdf"]


def _note(regions):
    return _by_class(regions["foot"], "note")[0]["text"]


def test_autofill_attaches_the_resume_to_an_empty_resume_box(tmp_path):
    out = _autofill(tmp_path, EMPTY_RESUME_BOX)
    [ask] = _attach_asks(out)
    # The button's own path and source, plus Autofill's stricter write.
    assert ask["path"] == "/api/applications/app-remembered/pdf"
    assert ask["filename"] == "tailored-resume.pdf"
    assert (ask["expect"], ask["resumeOnly"]) == (1, True)
    assert _note(out["settled"]).endswith(ATTACHED)
    rows = dict(_rows_of(out["settled"]["rail"]))
    assert rows["Resume attached"] == "tailored-resume.pdf · 1 upload box"
    # Attached once, so there is no second offer.
    assert out["button"] is None


def test_the_attach_comes_after_the_fields(tmp_path):
    """Workday re-renders the upload section after an upload, so the fields
    are written first and the attach is the run's last page write."""
    out = _autofill(tmp_path, EMPTY_RESUME_BOX)
    order = [msg["type"] for msg in out["sent"]
             if msg["type"] in ("attach_pdf", "page_broadcast")]
    assert order[-1] == "attach_pdf"
    assert order.count("page_broadcast") >= 2


def test_saved_answers_and_ai_attaches_too(tmp_path):
    out = _loop_with_pdf(tmp_path)
    [ask] = _attach_asks(out)
    assert ask["resumeOnly"] is True
    assert _note(out["settled"]).endswith(ATTACHED)


def test_a_box_that_already_lists_a_file_is_left_alone(tmp_path):
    out = _autofill(tmp_path, {"kind": "resume", "occupied": True})
    assert _attach_asks(out) == []
    assert _note(out["settled"]).endswith(
        "A file is already attached; the Companion left it.")
    rows = dict(_rows_of(out["settled"]["rail"]))
    assert rows["Resume not attached"] == "A file is already attached; the Companion left it."
    # The button stays: the user may still want theirs replaced by hand.
    assert out["button"] == {"disabled": False}


def test_a_cover_letter_box_is_never_auto_attached(tmp_path):
    out = _autofill(tmp_path, {"kind": "other", "occupied": False})
    assert _attach_asks(out) == []
    assert _note(out["settled"]).endswith(
        "The upload box isn't for a resume, so the Companion left it.")


def test_a_box_of_unknown_kind_is_left_to_the_button(tmp_path):
    out = _autofill(tmp_path, {"kind": "unknown", "occupied": False})
    assert _attach_asks(out) == []
    assert _note(out["settled"]).endswith(
        "Couldn't tell if the upload box is for a resume. Attach it yourself if it is.")
    assert out["button"] == {"disabled": False}


COVER_LETTER_BOX = {"kind": "other", "occupied": False}
UNKNOWN_BOX = {"kind": "unknown", "occupied": False}


def test_beside_a_cover_letter_box_the_resume_box_is_attached(tmp_path):
    """Greenhouse's shape: a resume box and a cover-letter box. The write names
    the page's two boxes (`expect`) and the frame picks the one resume box."""
    out = _autofill(tmp_path, EMPTY_RESUME_BOX, COVER_LETTER_BOX)
    [ask] = _attach_asks(out)
    assert (ask["expect"], ask["resumeOnly"]) == (2, True)
    assert _note(out["settled"]).endswith(ATTACHED)


@pytest.mark.parametrize("boxes, said", [
    ([UNKNOWN_BOX, COVER_LETTER_BOX],
     "Couldn't tell which upload box is for a resume. Attach it yourself."),
    ([EMPTY_RESUME_BOX, EMPTY_RESUME_BOX],
     "Couldn't tell which upload box is for a resume. Attach it yourself."),
    ([COVER_LETTER_BOX, COVER_LETTER_BOX],
     "None of the upload boxes is for a resume, so the Companion left them."),
    ([{"kind": "resume", "occupied": True}, COVER_LETTER_BOX],
     "A file is already attached; the Companion left it."),
])
def test_several_boxes_without_one_empty_resume_box_are_left(tmp_path, boxes, said):
    out = _autofill(tmp_path, *boxes)
    assert _attach_asks(out) == []
    assert _note(out["settled"]).endswith(said)
    # The button's own refusal sentence is still under the line.
    assert "This page has 2 upload boxes" in _attach_text(out["settled"])


def test_no_pdf_no_attach_and_nothing_said(tmp_path):
    out = _autofill(tmp_path, EMPTY_RESUME_BOX,
                    detail={"id": "app-remembered", "status": "draft",
                            "applied_at": None, "pdf_path": None})
    assert _attach_asks(out) == []
    assert "resume" not in _note(out["settled"]).lower()


def test_a_base_used_as_is_has_no_pdf_to_attach(tmp_path):
    out = _autofill(tmp_path, EMPTY_RESUME_BOX, stored={"widget.session": _armed_entry()})
    assert _attach_asks(out) == []


def test_a_page_whose_scripts_predate_the_kinds_is_left_alone(tmp_path):
    """An old content script answers the count and no `uploads`: no kind, no
    attach, and nothing said about a box the panel knows nothing of."""
    out = _autofill(tmp_path, page=_page(file_inputs=1))
    assert _attach_asks(out) == []
    assert out["button"] == {"disabled": False}


def test_an_attach_it_could_not_confirm_is_hedged_and_keeps_the_button(tmp_path):
    out = _autofill(tmp_path, EMPTY_RESUME_BOX, attach_reply=ATTACH_NONE)
    hedged = ("Couldn't confirm the upload. Check the upload box, and attach "
              "your resume only if it isn't listed.")
    assert _note(out["settled"]).endswith(hedged)
    rows = dict(_rows_of(out["settled"]["rail"]))
    assert "Resume attached" not in rows
    assert rows["Resume upload"] == hedged
    assert out["button"] == {"disabled": False}


def test_a_second_autofill_never_attaches_a_second_copy(tmp_path):
    """Even when the page's row went unseen: this panel attached here once."""
    out = _autofill(tmp_path, EMPTY_RESUME_BOX, again=True)
    assert len(_attach_asks(out)) == 1


def test_a_second_autofill_after_an_unconfirmed_attach_does_not_retry_it(tmp_path):
    """The hedged zero may be a file the page took without either proof: a
    second automatic copy is the thing the hedge exists to prevent."""
    out = _autofill(tmp_path, EMPTY_RESUME_BOX, attach_reply=ATTACH_NONE, again=True)
    assert len(_attach_asks(out)) == 1


def test_the_attach_holds_the_run_busy(tmp_path):
    """Autofill's span covers its attach: the primary spins and the button is
    out of reach while the PDF is read and sent."""
    out = _autofill(tmp_path, EMPTY_RESUME_BOX,
                    hold=["/api/applications/app-remembered"], holdSkip=1)
    [cta] = _by_class(out["during"]["foot"], "cta")
    assert (cta["class"], cta["disabled"]) == ("cta spin", True)
    assert all(button["disabled"] for button in _by_class(out["during"]["rail"], "save"))
    assert len(_attach_asks(out)) == 1


def test_a_stopped_run_attaches_nothing(tmp_path):
    out = _loop_with_pdf(tmp_path, holdRun=True, pressStop=True)
    assert _attach_asks(out) == []


def test_a_run_whose_tab_was_left_attaches_nothing(tmp_path):
    """To the wizard's next step, whose own application and box would
    otherwise take the run's attach."""
    out = _loop_with_pdf(tmp_path, holdRun=True, switchTo=9, tabUrls={"9": STEP_2})
    assert _attach_asks(out) == []


def _loop_with_pdf(tmp_path, **spec):
    """The loop's panel world (its `runFill` stubbed), on a tailored
    application's apply page with one empty resume box."""
    spec.setdefault("tabs", [{"id": 7, "url": LIGHTNING_APPLY_URL}])
    spec.setdefault("stored", {"widget.session": entry(touched=False)})
    spec.setdefault("page", _page(EMPTY_RESUME_BOX))
    replies = {"read_settings": SETTINGS_REPLY,
               "panel_prepare": _reply({"injected": True}),
               "attach_pdf": ATTACH_ONE,
               "telemetry": _reply({"posted": 0})}
    api = {"lightningai": _reply({"match": "none", "job": None, "application": None}),
           "/api/base-resumes": _reply(BASE_RESUMES),
           "/api/ats-scores": _reply(SCORES),
           "GET /api/applications/app-remembered": _reply(_TAILORED_DETAIL)}
    frames = {"fill_inventory": [], "fill_focus": [{"frameId": 0, "result": True}],
              "fill_cancel": [{"frameId": 0, "result": True}]}
    return run_node(_LOOP_DRIVER_JS, {**spec, "report": LOOP_REPORT, "api": api,
                                      "replies": replies, "frames": frames},
                    tmp_path, source=PANEL_SOURCE)
