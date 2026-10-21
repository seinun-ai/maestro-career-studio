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
