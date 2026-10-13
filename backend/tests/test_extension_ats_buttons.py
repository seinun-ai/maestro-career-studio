"""The known-button table (queued-run plan Task 14): a few ATS navigation buttons named by their
own stable markers, for the cases where the TEXT alone cannot say what a button is.

`extension/shared/ats-buttons.js` is pure, so node drives it. What these tests hold:
the table can only ever make a button MORE stopped (every shipped verdict is "text", never
"next"), a marker counts only on its own vendor's host, and an unknown host has no say at all. A Submit word in a
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
ATS_HOSTS_JS = (EXTENSION / "shared" / "ats-hosts.js").read_text(encoding="utf-8")

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


def test_workdays_footer_marker_names_the_navigation_button_and_leaves_the_verdict_to_its_text(tmp_path):
    """Recorded in test_extension_detection.py (`_WORKDAY_MY_INFORMATION`). The verdict is "text",
    never "next": Workday's last step relabels the same button "Submit"."""
    for host in ["acme.wd5.myworkdayjobs.com", "myworkdayjobs.com", "Acme.WD1.MyWorkdayJobs.com"]:
        assert known(tmp_path, host, automationId="pageFooterNextButton") == "text"
    out = _run(tmp_path, [
        ("acme.wd5.myworkdayjobs.com", {"automationId": "pageFooterNextButton2"}),
        ("acme.wd5.myworkdayjobs.com", {"id": "pageFooterNextButton"}),
        ("acme.wd5.myworkdayjobs.com", {"automationId": "add-button"}),
        ("boards.greenhouse.io", {"automationId": "pageFooterNextButton"}),   # another vendor's host
        ("acme-careers.example.com", {"automationId": "pageFooterNextButton"}),
        ("myworkdayjobs.com.example.com", {"automationId": "pageFooterNextButton"}),
        ("evilmyworkdayjobs.com", {"automationId": "pageFooterNextButton"}),
    ])
    assert out["known"] == [None] * 7


def test_an_unknown_host_or_marker_has_no_say(tmp_path):
    out = _run(tmp_path, [
        ("example.com", {}),
        ("boards.greenhouse.io", {}),
        ("boards.greenhouse.io", {"id": "next"}),
        ("boards.greenhouse.io", {"id": "submit_app"}),   # a host with no rows, whatever the id
        ("jobs.lever.co", {"id": "btn-submit", "qa": "btn-submit"}),
        ("acme.wd5.myworkdayjobs.com", {}),
        ("", {"id": "submit_app"}),
        (None, {"id": "submit_app"}),
        ("acme.wd5.myworkdayjobs.com", None),
    ])
    assert out["known"] == [None] * 9


def test_the_table_never_says_next(tmp_path):
    """A "next" entry would be a button the run clicks on a marker's word alone, so none ships
    without a recorded fixture that shows the marker (and then this pin is changed on purpose).
    "text" hands the verdict back to the button's own label."""
    verdicts = _run(tmp_path)["verdicts"]
    assert verdicts and set(verdicts) == {"text"}


def test_an_unknown_verdict_string_is_a_submit_and_text_is_a_known_one(tmp_path):
    out = run_node(
        """const ns = loadModules();
        ns.atsButtons.HOSTS.acme = /^ats\\.acme-example\\.test$/;
        const at = (verdict) => { ns.atsButtons.RULES.push({vendor: "acme", buttons: [{id: "b", verdict}]});
          return ns.atsButtons.knownSort("ats.acme-example.test", {id: "b"}); };
        emit({text: at("text"), odd: (ns.atsButtons.RULES.pop(), at("maybe"))});""",
        {}, tmp_path, source=ATS_BUTTONS_JS)
    assert out == {"text": "text", "odd": "submit"}


def test_the_hosts_are_the_shared_ats_hosts(tmp_path):
    """Copied, not imported (the table is in its own module), so a vendor whose host pattern
    drifts in either file fails here."""
    detect = dict(re.findall(r'\["(\w+)", /(.+?)/\],', ATS_HOSTS_JS))
    ours = _run(tmp_path)["hosts"]
    assert ours and set(ours) <= set(detect)
    for vendor, source in ours.items():
        assert source == detect[vendor].replace("\\/", "/"), vendor


def test_the_module_publishes_exactly_its_surface(tmp_path):
    out = run_node("const ns = loadModules(); emit({keys: Object.keys(ns.atsButtons).sort()});",
                   {}, tmp_path, source=ATS_BUTTONS_JS)
    assert out["keys"] == ["HOSTS", "RULES", "knownSort"]
    assert json.dumps(out)  # plain data
