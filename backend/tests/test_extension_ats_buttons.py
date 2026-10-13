"""The known-button table (queued-run plan Task 14): a few ATS navigation buttons named by their
own stable markers, for the cases where the TEXT alone cannot say what a button is.

`extension/shared/ats-buttons.js` is pure, so node drives it. What these tests hold:
the table can only ever make a button MORE stopped (every shipped verdict is "submit"), a marker
counts only on its own vendor's host, and an unknown host has no say at all. A Submit word in a
button's text still beats a "next" verdict; that half lives in `shared/page-kind.js` and is pinned
in test_extension_page_kind.py and, end to end, in tests/browser/test_page_reader.py.
"""

import json
import re
from pathlib import Path

import pytest

from tests.extension_harness import run_node

EXTENSION = Path(__file__).resolve().parents[2] / "extension"
ATS_BUTTONS_JS = (EXTENSION / "shared" / "ats-buttons.js").read_text(encoding="utf-8")
DETECT_JS = (EXTENSION / "content" / "detect.js").read_text(encoding="utf-8")

_DRIVER = r"""
const ns = loadModules();
emit({
  known: (spec.cases || []).map(([host, attrs]) => ns.atsButtons.knownSort(host, attrs)),
  hosts: Object.fromEntries(Object.entries(ns.atsButtons.HOSTS).map(([v, re]) => [v, re.source])),
  verdicts: ns.atsButtons.RULES.flatMap((r) => r.buttons.map((b) => b.verdict)),
});
"""


def _run(tmp_path, cases=()):
    return run_node(_DRIVER, {"cases": [list(c) for c in cases]}, tmp_path, source=ATS_BUTTONS_JS)


def known(tmp_path, host, **attrs):
    return _run(tmp_path, [(host, attrs)])["known"][0]


def test_greenhouses_submit_marker_is_a_submit_whatever_its_text(tmp_path):
    """The case the text cannot catch: a submit button that reads "Done". The id is the evidence."""
    for host in ["boards.greenhouse.io", "job-boards.greenhouse.io", "greenhouse.io", "Boards.Greenhouse.IO"]:
        assert known(tmp_path, host, id="submit_app") == "submit"


def test_levers_submit_marker_is_a_submit_by_id_or_by_data_qa(tmp_path):
    assert known(tmp_path, "jobs.lever.co", id="btn-submit") == "submit"
    assert known(tmp_path, "jobs.lever.co", qa="btn-submit") == "submit"


def test_a_marker_counts_only_on_its_own_vendors_host(tmp_path):
    out = _run(tmp_path, [
        ("jobs.lever.co", {"id": "submit_app"}),          # Greenhouse's marker on Lever
        ("boards.greenhouse.io", {"id": "btn-submit"}),   # Lever's marker on Greenhouse
        ("acme-careers.example.com", {"id": "submit_app"}),
        ("greenhouse.io.example.com", {"id": "submit_app"}),
        ("evilgreenhouse.io", {"id": "submit_app"}),
        ("jobs.lever.co.example.com", {"id": "btn-submit"}),
    ])
    assert out["known"] == [None] * 6


def test_an_unknown_host_or_marker_has_no_say(tmp_path):
    out = _run(tmp_path, [
        ("example.com", {}),
        ("boards.greenhouse.io", {}),
        ("boards.greenhouse.io", {"id": "next"}),
        ("boards.greenhouse.io", {"id": "submit_app_2"}),
        ("acme.wd5.myworkdayjobs.com", {"automationId": "pageFooterNextButton"}),
        ("", {"id": "submit_app"}),
        (None, {"id": "submit_app"}),
        ("boards.greenhouse.io", None),
    ])
    assert out["known"] == [None] * 8


def test_the_table_can_only_ever_say_submit(tmp_path):
    """A "next" entry would be a button the run clicks on a marker's word alone, so none ships
    without a recorded fixture that shows the marker (and then this pin is changed on purpose)."""
    verdicts = _run(tmp_path)["verdicts"]
    assert verdicts and set(verdicts) == {"submit"}


def test_the_hosts_are_detect_jss_hosts(tmp_path):
    """Copied, not imported (detect.js publishes no table), so a vendor whose host pattern drifts
    in either file fails here."""
    detect = dict(re.findall(r'\["(\w+)", /(.+?)/\],', DETECT_JS))
    ours = _run(tmp_path)["hosts"]
    assert ours and set(ours) <= set(detect)
    for vendor, source in ours.items():
        assert source == detect[vendor].replace("\\/", "/"), vendor


def test_the_module_publishes_exactly_its_surface(tmp_path):
    out = run_node("const ns = loadModules(); emit({keys: Object.keys(ns.atsButtons).sort()});",
                   {}, tmp_path, source=ATS_BUTTONS_JS)
    assert out["keys"] == ["HOSTS", "RULES", "knownSort"]
    assert json.dumps(out)  # plain data
