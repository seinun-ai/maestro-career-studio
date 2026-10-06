"""Eight visual primitives with one accessible-text contract each (visual-language plan, Task 14)."""

from pathlib import Path

from tests.node_ts import run_node_test

_VISUAL = Path(__file__).resolve().parents[2] / "frontend/components/visual"
_PRIMITIVES = {
    "dot-meter.tsx": 'role="img"',
    "score-bar.tsx": 'role="meter"',
    "segmented-bar.tsx": "legend",
    "progress-count.tsx": 'role="progressbar"',
    "delta-chip.tsx": "aria-label",
    "actor-chip.tsx": "CONCEPT_ICONS",
    "sparkline.tsx": 'role="img"',
}


def test_visual_helpers_node_suite():
    result = run_node_test("lib/visual.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr


def test_each_primitive_carries_its_accessible_text():
    for name, marker in _PRIMITIVES.items():
        assert marker in (_VISUAL / name).read_text(), name


def test_status_dot_takes_its_colour_from_the_status_vocabulary():
    chip = (_VISUAL.parent / "status-chip.tsx").read_text()
    assert "export function StatusDot" in chip and "STATUS_STYLES" in chip.split("export function StatusDot", 1)[1]


def test_lane_dot_and_every_proposal_status_carry_a_dot_role():
    chip = (_VISUAL.parent / "status-chip.tsx").read_text()
    assert "export function LaneDot" in chip
    table = chip.split("export const PROPOSAL_STATUS_CHIP", 1)[1].split("> = {", 1)[1].split("};", 1)[0]
    entries = [line for line in table.splitlines() if "label:" in line or "NEEDS_YOU" in line]
    assert len(entries) == 9
    needs_you = chip.split("const NEEDS_YOU", 1)[1].split("};", 1)[0]
    assert "dot:" in needs_you
    assert table.count("dot:") == 7  # the two NEEDS_YOU entries share one object


def test_no_status_dot_is_the_invisible_neutral_secondary():
    chip = (_VISUAL.parent / "status-chip.tsx").read_text()
    assert "dot: \"bg-secondary\"" not in chip  # --secondary is a neutral grey: ~1:1 on the chip surfaces


def test_agent_and_ai_actors_use_the_register():
    actor = (_VISUAL / "actor-chip.tsx").read_text()
    for concept in ("CONCEPT_ICONS.ai", "CONCEPT_ICONS.agentInbox"):
        assert concept in actor
    assert "showText" in (_VISUAL / "progress-count.tsx").read_text()


def test_primitives_use_roles_not_shades():
    for path in _VISUAL.glob("*.tsx"):
        text = path.read_text()
        assert "bg-muted/" not in text and "#" not in text.replace("#!", ""), path.name
