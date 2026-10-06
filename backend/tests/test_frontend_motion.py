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


_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _ms(var: str) -> int:
    return int(re.search(rf"--{var}:\s*(\d+)ms", _CSS).group(1))


def _motion() -> str:
    return (_FRONTEND / "lib/motion.ts").read_text()


def _const(name: str) -> int:
    return int(re.search(rf"export const {name} = (\d+);", _motion()).group(1))


def test_motion_module_holds_the_budget_and_matches_the_tokens():
    assert _const("CONFIRM_HOLD_MS") == 1200
    assert _const("CONFIRM_MS") == _ms("duration-medium4")
    assert _const("ROW_EXIT_MS") == _ms("duration-short4")


def test_motion_constants_are_imported_not_redeclared():
    for rel, name in {
        "hooks/use-copy.ts": "CONFIRM_HOLD_MS",
        "hooks/use-saved-hold.ts": "CONFIRM_HOLD_MS",
        "components/status-chip.tsx": "CONFIRM_MS",
        "components/proposals/proposals-section.tsx": "ROW_EXIT_MS",
    }.items():
        src = (_FRONTEND / rel).read_text()
        assert f'import {{ {name} }} from "@/lib/motion"' in src, rel
        assert not re.search(r"\b(1200|400|200)\b", re.sub(r"//.*|/\*.*?\*/", "", src)), rel
    assert "SAVED_HOLD_MS" not in (_FRONTEND / "components/settings/autosave-status.tsx").read_text()
    page = (_FRONTEND / "app/jobs/[id]/tailor/[sessionId]/page.tsx").read_text()
    assert "useSavedHold(" in page and "SAVED_HOLD_MS" not in page
    assert "export const ROW_EXIT_MS" not in (_FRONTEND / "components/proposals/triage-actions.tsx").read_text()


def test_every_motion_token_is_within_budget():
    root = _CSS.split(":root", 1)[1]
    used = set(re.findall(r"var\(--(duration-[\w-]+)\)", _UTILITIES))
    used |= set(re.findall(r"var\(--(duration-[\w-]+)\)", re.search(r"@utility animate-confirm\s*\{[^}]*\}", _CSS).group(0)))
    assert "duration-medium4" in used and "duration-short4" in used
    for token in used:
        assert re.search(rf"--{token}:\s*(\d+)ms", _CSS), token
        assert _ms(token) <= 400, token
    assert root


def test_count_up_default_is_within_budget_and_continues_from_the_screen():
    hook = (_FRONTEND / "hooks/use-count-up.ts").read_text()
    assert int(re.search(r"ms = (\d+)", hook).group(1)) <= 400
    step = hook[hook.index("const step"): hook.index("frame = requestAnimationFrame(step);\n    return")]
    assert "from.current = v" in step  # the value on screen, written inside the frame callback
    effect = hook[hook.index("useEffect("): hook.index("const reduce")]
    assert "setShown" not in effect and "from.current = target" not in hook
