"""The "In N resumes" row on a Career history card (resume-colour plan, Task 12).

Source pins, as in test_frontend_jobs_where.py: the frontend has no component runner.
"""

from pathlib import Path

from tests._jsx_pins import open_tag, squash, tokens

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_CARD = (_FRONTEND / "components/career/entity-card.tsx").read_text(encoding="utf-8")
_ROW = _CARD[_CARD.index("function UsedIn(") : _CARD.index("/** A count and its noun")]


def test_the_row_comes_last_and_reads_the_summary_field():
    assert "<UsedIn slugs={entity.used_in_bases ?? []} />" in _CARD
    assert _CARD.index("Updated {formatTimeAgo") < _CARD.index("<UsedIn ") < _CARD.index("<MergeEntityDialog")
    assert "used_in_bases?: string[];" in (_FRONTEND / "lib/types.ts").read_text(encoding="utf-8")


def test_nothing_shows_for_an_item_on_no_resume():
    assert "if (slugs.length === 0) return null;" in _ROW


def test_the_words_agree_and_are_small_and_muted():
    row = open_tag(_ROW, "div")
    assert {"text-muted-foreground", "text-body-small"} <= tokens(row)
    assert 'In {slugs.length} {slugs.length === 1 ? "resume" : "resumes"}' in squash(_ROW)


def test_up_to_eight_squares_then_a_count_of_the_rest():
    assert "const MAX_SQUARES = 8;" in _CARD
    assert "slugs.slice(0, MAX_SQUARES).map" in _ROW and "<ResumeSwatch key={slug} hue={colorOf(slug)} />" in _ROW
    assert "slugs.length > MAX_SQUARES ?" in _ROW and "+{slugs.length - MAX_SQUARES}" in squash(_ROW)


def test_the_names_ride_in_the_title_and_an_sr_only_list_not_beside_each_square():
    assert "title={names.join(\", \")}" in _ROW
    assert '<span className="flex items-center gap-1" aria-hidden="true">' in squash(_ROW)
    assert tokens(open_tag(_ROW, "ul")) == {"sr-only"}
    assert "nameOf" in _ROW and "useBaseResumeLabel" in _CARD and "useBaseResumeColor" in _CARD
