"""The visual language applied to real screens (visual-language plan, Wave 4). Each surface task adds its pins here."""

from __future__ import annotations

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


# --- Task 16: the knock-out check strip --------------------------------------------


def test_knockout_pass_is_quiet_and_conflict_is_loud():
    src = _read("components/job-knockout-card.tsx")
    assert "bg-success-container" not in src  # a pass is not a filled band any more
    assert "bg-error-container" in src  # a conflict is
    assert "SUMMARY_BY_RESULT" in src
    for icon in ("CircleX", "TriangleAlert", "Minus", "CircleDashed"):
        assert icon in src, icon
    for word in ("OK", "Conflict", "Warning", "Add answer", "Not listed", "Not run"):
        assert f'"{word}"' in src, word


def test_knockout_rows_use_their_result_icon():
    assert "AlertTriangle" not in _read("components/job-knockout-card.tsx")


def test_knockout_chip_text_is_label_then_word():
    src = _read("components/job-knockout-card.tsx")
    assert "`${label}: ${word}`" in src
    for label in ("Work auth", "OPT", "Pay", "Experience", "On-site"):
        assert f'"{label}"' in src, label


def test_knockout_requirements_not_stated_is_a_minus_not_a_question():
    src = _read("components/job-knockout-card.tsx")
    assert "\"No requirements listed\"" in src
    assert "CircleHelp" in src  # only the profile_missing chip and the incomplete banner
    assert "That doesn't mean you qualify." in src  # the safety meaning rides in the line's accessible text
