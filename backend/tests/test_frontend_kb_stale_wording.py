"""Source pins for the claims-with-wordings surfaces: the wordings popover and
the Tidy bullets dialog call their pure modules and say the designed words.
Behaviour lives in frontend/lib/*.test.ts (node --test)."""

from __future__ import annotations

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


def test_points_list_hides_combined_bullets_and_opens_the_wordings_popover():
    src = _read("components/career/points-list.tsx")
    assert "visibleClaims(" in src
    row = src[src.index("function PointRow(") :]
    for needle in ("wordingsChip(", "wordingActions(", "splitRequest(",
                   "Wordings of this bullet", "Use as the main wording", "Make its own bullet",
                   "Combined from another bullet", "PopoverTrigger", '"Bullet updated"', "Now its own bullet",
                   "splitKbWording(", "unmerge: true",
                   # Undo puts the old line back, or combines the split bullet back in.
                   "undoText: point.text", "combineKbPoints(point.id, [newId])",
                   # Adopting would drop the editor's typed text; a Not used bullet offers no split.
                   "chip !== null && !editing", "wordingActions(w, { retired",
                   # A chip the refetch removes hands focus on after that commit, not before.
                   "focusNext(actionRef)"):
        assert needle in row, needle
    assert "useFocusOnNextCommit()" in row
    assert "Wording differs" not in src, "the Drifted badge is now the wordings chip"
