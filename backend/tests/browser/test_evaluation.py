"""The oracle gate and the cold/warm measurement (fill-engine revision Task 12).

- A run cut short by its clock (`RUN_MS`) on the real end-to-end page ends
  inside that clock, says it timed out, leaves nothing open, and holds the
  oracle line: nothing it reports verified is anything but what the app
  holds, and no field holds a value the profile did not give.
- Cold vs warm: the end-to-end page filled twice over one recipe book, with
  the engine's gestures counted (pointer presses, Enter, other keys, typed
  text inserts) and the wall time. Printed as a table (`pytest -s`); the numbers
  go in the evaluation report. Asserted only in the direction a book may
  move them: a warm run never needs more gestures, and fills the same.
"""

import re
from collections import Counter

import pytest

from tests.browser.pages import oracle
from tests.browser.test_fill_end_to_end import FIXTURES, MAP, _finish, _open_popups, _page_of, _run, _start
from tests.browser.test_recipes import DAY, KEYBOARD_ONLY, TRAVEL, URL

# The e2e page's fields that keep an oracle: question -> (key, what the app
# holds before the run, what the profile gives). Skills may be part-filled.
ORACLE_OF = {
    "City": ("city", None, "Springfield"),
    "Postal Code": ("zip", None, "12345"),
    "Are you legally authorized to work in the United States?": ("auth", "", "Yes"),
    "Degree": ("degree", "", "Masters"),
    "How Did You Hear About Us?": ("heard", "", "LinkedIn"),
    "School or University": ("school", "", "The University of Texas at Arlington"),
    "Type to Add Skills": ("skills", ["SQL"], ["SQL", "Python", "Tableau"]),
    "Field of study": ("fos", "", "Information Systems"),
    "Country": ("country", "", ""),   # react-select: no fact, never written
}


def assert_the_oracle_line(page, out):
    """Zero false "verified", zero wrong writes."""
    for question, (key, before, given) in ORACLE_OF.items():
        held = oracle(page, key)
        if key == "skills":
            assert held[:1] == ["SQL"] and set(held) <= set(given), (question, held)
        else:
            assert held in (before, given), (question, held)
        r = out["by_question"].get(question)
        if r and r["status"] == "verified":
            assert held == given, (question, held, r)


@pytest.fixture
def e2e_page(page):
    page.set_default_timeout(60000)
    return page


@pytest.mark.parametrize("run_ms", [1500, 5000])
def test_a_run_cut_by_its_clock_ends_inside_it_and_claims_nothing_false(e2e_page, run_ms):
    page = e2e_page
    out = _run(page, limits={"RUN_MS": run_ms})
    assert out["report"]["timedOut"] is True and out["report"]["stopped"] is False
    # The clock, plus the cleanup a timed-out run may still do (closing what
    # it opened, one bounded outside click): never another field's work. A
    # WALL-CLOCK bound, measured in the page: a loaded machine can stretch the
    # cleanup, hence the wide margin (a run that ignored its clock takes ~17 s).
    assert out["ms"] < run_ms + 5000, out["ms"]
    assert _open_popups(page) == []
    assert_the_oracle_line(page, out)
    # What the clock cut is said to be the clock's, never "no answer".
    cut = [r for r in out["report"]["fields"] if r["status"] != "verified" and r["question"] in ORACLE_OF
           and r["question"] != "Country"]
    assert all(r["lastOutcome"] == "timeout" for r in cut), cut


def test_the_full_run_holds_the_oracle_line(e2e_page):
    page = e2e_page
    out = _run(page)
    assert out["report"]["timedOut"] is False
    assert_the_oracle_line(page, out)
    for question, (key, _before, given) in ORACLE_OF.items():
        if key != "country":
            assert out["by_question"][question]["status"] == "verified" and oracle(page, key) == given, question


# ---------- cold vs warm, over one recipe book


# The engine's gestures, counted where the page sees them (capture, on the
# window). Presses and keys count UNTRUSTED events: the engine's own dispatches
# (it has no other input), and any a page script dispatched — the composed
# fixtures dispatch none of these types. Typing counts `insertText` input
# events whatever their isTrusted: execCommand("insertText"), which the
# engine types with, fires TRUSTED input events.
GESTURES = """() => {
  window.__gestures = { press: 0, enter: 0, keys: 0, typed: 0 };
  addEventListener("pointerdown", (e) => { if (!e.isTrusted) window.__gestures.press += 1; }, true);
  addEventListener("keydown", (e) => {
    if (e.isTrusted) return;
    if (e.key === "Enter") window.__gestures.enter += 1; else window.__gestures.keys += 1;
  }, true);
  addEventListener("input", (e) => { if (e.inputType === "insertText") window.__gestures.typed += 1; }, true);
}"""
WITH_KEYBOARD_WIDGET = _page_of(FIXTURES) + f"\n<div>{KEYBOARD_ONLY}</div>"
SCENARIOS = {"e2e": (_page_of(FIXTURES), MAP), "e2e+keyboard-only": (WITH_KEYBOARD_WIDGET, MAP | TRAVEL)}


def one_run(page, html, mapping, book):
    _start(page, page_js=GESTURES, html=html, url=URL, map=mapping, book=book, today=DAY)
    out = _finish(page)
    return out, page.evaluate("window.__gestures")


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_cold_then_warm_over_one_recipe_book(e2e_page, scenario):
    page = e2e_page
    html, mapping = SCENARIOS[scenario]
    ids = Counter(re.findall(r"""(?<![\w-])id=["']([^"'$]+)["']""", html))
    assert [i for i, n in ids.items() if n > 1] == []
    runs = []
    book = None
    for name in ("cold", "warm"):
        out, gestures = one_run(page, html, mapping, book)
        assert out["report"]["timedOut"] is False
        assert_the_oracle_line(page, out)
        book = out["book"]
        runs.append({"run": name, **gestures, "ms": out["ms"],
                     "verified": sum(r["status"] == "verified" for r in out["report"]["fields"]),
                     "book": dict(Counter(e["state"] for e in (book or {"entries": {}})["entries"].values()))})
    print(f"\nCOLD-WARM {scenario}")
    print("| run | presses | Enter | other keys | typed | wall ms | verified | book after |")
    for r in runs:
        print(f"| {r['run']} | {r['press']} | {r['enter']} | {r['keys']} | {r['typed']} | {r['ms']} | {r['verified']} "
              f"| {r['book'] or '{}'} |")
    cold, warm = runs
    assert warm["verified"] == cold["verified"]
    assert warm["press"] + warm["enter"] + warm["keys"] <= cold["press"] + cold["enter"] + cold["keys"]
    if scenario == "e2e+keyboard-only":
        assert warm["press"] < cold["press"]   # the learned keyboard open skips the presses it ignores
