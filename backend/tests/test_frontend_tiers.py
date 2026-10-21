"""The Lead / Also / Folded tiers (design refresh, Phase 0)."""

from pathlib import Path

from tests._jsx_pins import squash

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _src(path: str) -> str:
    return (_FRONTEND / path).read_text(encoding="utf-8")


def test_fold_is_a_real_disclosure_with_a_summary():
    src = squash(_src("components/ui/fold.tsx"))
    assert "aria-expanded={open}" in src and "aria-controls={panelId}" in src
    assert "summary" in src and "ChevronRight" in src
    assert "transition-[rotate]" in src  # names the property, never `transform`
    assert "hidden={!open}" in src  # a closed panel leaves the tab order and the accessibility tree
    # Tailwind v4 compiles an unknown theme name to nothing: the M3 durations live in :root, so they are
    # read with the `(--var)` form (`duration-short3` alone draws no transition).
    assert "duration-(--duration-short3)" in src and "duration-short3 " not in src


def test_next_step_has_one_look_for_a_move_and_one_for_waiting():
    """Owner rule D3: your move is a blue text link with a chevron, their move grey text; the tonal fill
    shows only while the row (`group/row`) is hovered."""
    src = squash(_src("components/visual/next-step.tsx"))
    assert "text-primary" in src and "ChevronRight" in src  # your move
    assert "text-muted-foreground" in src  # their move
    assert "bg-secondary-container" not in src.split("group-hover")[0]  # no fill at rest
    assert "group-hover/row:bg-secondary-container" in src
    assert "group-hover/row:text-on-secondary-container" in src
    assert 'export { NextStep } from "./next-step";' in _src("components/visual/index.ts")
