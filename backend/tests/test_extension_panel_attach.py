"""The Fill stage's ATTACH beyond the button: the offer following a wizard's
in-page steps, and Autofill attaching the resume itself.

A fill sub-concern with its OWN drivers, which is the trigger
`test_extension_panel.py`'s map names for cutting it out of
`test_extension_panel_fill.py`. The button's own contract (the offer, the
press, the proof, the refusals) stays there; this file reuses its world
(`_attach`) and adds two drivers: a wizard step changing the tab's url, and
an Autofill run that ends with an attach.
"""

from tests.extension_fixtures import LIGHTNING_APPLY_URL
from tests.extension_panel_harness import _PANEL_FAKES_JS, _by_class, _reply
from tests.test_extension_panel_fill import _attach, _attach_text

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
