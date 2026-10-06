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
    assert "@utility animate-confirm" in _CSS and ".collapse-exit" in _CSS
    assert "confirm-ring var(--duration-medium4)" in _CSS
    assert ".animate-row-exit" not in _CSS
    assert "[data-leaving]" in _UTILITIES
    for ms in re.findall(r"(\d+)ms", _UTILITIES):
        assert int(ms) <= 400 or int(ms) == 1400, ms  # 1400 is the existing shimmer


def test_no_bounce_curve_is_introduced():
    assert "cubic-bezier(0.34, 1.56" not in _CSS and "bounce" not in _CSS.lower()


def test_collapse_exit_clips_only_while_leaving():
    # At rest the child must not clip focus rings, shadows or popovers.
    rest = re.search(r"\.collapse-exit > \*\s*\{([^}]*)\}", _UTILITIES).group(1)
    assert "overflow" not in rest and "min-height: 0" in rest
    leaving = re.search(r"\.collapse-exit\[data-leaving\] > \*\s*\{([^}]*)\}", _UTILITIES)
    assert leaving and "overflow: hidden" in leaving.group(1)
