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


def test_tidy_bullets_button_opens_the_groom_dialog_when_two_or_more_are_active():
    src = _read("components/career/points-list.tsx")
    assert "Tidy bullets" in src
    assert 'state !== "retired"' in src and ">= 2" in src
    assert "GroomDialog" in src


def test_groom_dialog_uses_the_pure_module_and_says_the_designed_words():
    src = _read("components/career/groom-dialog.tsx")
    for needle in (
        "otherIds(", "pairsOf(", "groomState(", "combinedToast(", "undoCombinePlan(", "KEEPER_RULE",
        "Similar bullets on", "Keep one as the bullet and fold the others into it as wordings.",
        "Nothing changes on your resumes.",
        "Keep this one", "Combine into one", "Stop using", "Not the same",
        "Won't suggest these again", "Won't be offered again",
        "No similar bullets here.", "Couldn't compare wording right now.",
        "combineKbPoints(", "forgetKeepApartKbPoints(", "bulkKbPointState(", "unmerge: true",
    ):
        assert needle in src, needle
    assert "Combine all" not in src, "each cluster is one decision"
