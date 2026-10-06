"""Small motion that confirms (visual-language plan, Task 15; owner's motion budget D9)."""

import re
from pathlib import Path

from tests.node_ts import run_node_test

_CSS = (Path(__file__).resolve().parents[2] / "frontend/app/globals.css").read_text()
_UTILITIES = _CSS.split("@layer utilities", 1)[1].split("@media (prefers-reduced-motion", 1)[0]


def test_count_up_node_suite():
    result = run_node_test("lib/count-up.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr


def test_motion_utilities_exist_and_stay_within_budget():
    for name in ("animate-confirm", "collapse-exit"):
        assert f".{name}" in _CSS
    assert ".animate-row-exit" not in _CSS
    assert "[data-leaving]" in _UTILITIES
    for ms in re.findall(r"(\d+)ms", _UTILITIES):
        assert int(ms) <= 400 or int(ms) == 1400, ms  # 1400 is the existing shimmer


def test_no_bounce_curve_is_introduced():
    assert "cubic-bezier(0.34, 1.56" not in _CSS and "bounce" not in _CSS.lower()
