"""No decision site compares a response with its module's ABSTAIN.

`==` compares the trace too, so a Picked or StepResponse that carries one never equals ABSTAIN:
ask the module's `abstained`. (A `!=` once read every traced abstain as an answer, and the step's
second opinion never ran.) This reads every module and script, so a comparison cannot come back
anywhere, by `==`, `!=`, `is`, `is not` or `in`."""

import re
from pathlib import Path

import pytest

COMPARISON = re.compile(
    r"(?:[!=]=|\bis(?:\s+not)?\s|\bin\s*[(\[{][^)\]}]*?)\s*(?:\w+\.)*_?ABSTAIN\b"
    r"|\b_?ABSTAIN\s*(?:[!=]=|is\b)")
BACKEND = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("line", ["x == ABSTAIN", "ABSTAIN != x", "x is ABSTAIN", "x is not mod.ABSTAIN",
                                  "x in (ABSTAIN, y)", "_ABSTAIN == x"])
def test_the_pattern_finds_a_comparison(line):
    assert COMPARISON.search(line)


@pytest.mark.parametrize("line", ["return ABSTAIN", "ABSTAIN = Picked(", "{f: ABSTAIN for f in g}"])
def test_the_pattern_leaves_a_use_alone(line):
    assert not COMPARISON.search(line)


def test_no_module_or_script_compares_with_abstain():
    files = [*(BACKEND / "app").rglob("*.py"), *(BACKEND / "scripts").rglob("*.py")]
    found = [f"{f.relative_to(BACKEND)}:{n}: {line.strip()}" for f in files
             for n, line in enumerate(f.read_text().splitlines(), 1) if COMPARISON.search(line)]
    assert len(files) > 50 and found == []
