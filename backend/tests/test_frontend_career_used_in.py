"""The "In N resumes" row on a Career history card (resume-colour plan, Task 12).

Source pins, as in test_frontend_jobs_where.py: the frontend has no component runner.
"""

from pathlib import Path

from tests._jsx_pins import open_tag, squash, tokens

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_CARD = (_FRONTEND / "components/career/entity-card.tsx").read_text(encoding="utf-8")
_ROW = _CARD[_CARD.index("function UsedIn(") : _CARD.index("/** A count and its noun")]


def test_the_row_comes_last_and_reads_the_summary_field():
    assert "<UsedIn slugs={entity.used_in_bases ?? []} href={`/career/${entity.id}`} />" in _CARD
    assert _CARD.index("Updated {formatTimeAgo") < _CARD.index("<UsedIn ") < _CARD.index("<MergeEntityDialog")
    assert "used_in_bases?: string[];" in (_FRONTEND / "lib/types.ts").read_text(encoding="utf-8")


def test_nothing_shows_for_an_item_on_no_resume():
    assert "if (slugs.length === 0) return null;" in _ROW


def test_the_words_agree_and_are_small_and_muted():
    row = open_tag(_ROW, "div")
    assert {"text-muted-foreground", "text-body-small"} <= tokens(row)
    assert 'In {resumes.length} {resumes.length === 1 ? "resume" : "resumes"}' in squash(_ROW)


def test_up_to_eight_squares_then_a_count_of_the_rest():
    assert "const MAX_SQUARES = 8;" in _CARD
    assert "resumes.slice(0, MAX_SQUARES).map" in _ROW and "<ResumeSwatch key={slug} hue={colorOf(slug)} />" in _ROW
    assert "resumes.length > MAX_SQUARES ?" in _ROW and "+{resumes.length - MAX_SQUARES}" in squash(_ROW)


def test_squares_and_names_go_by_display_name_not_slug():
    assert ".sort((a, b) => a.name.localeCompare(b.name))" in squash(_ROW)


def test_the_names_ride_in_the_squares_title_and_an_sr_only_list():
    row = squash(_ROW)
    assert 'className="relative z-20 flex cursor-pointer items-center gap-1"' in row
    assert 'title={resumes.map((r) => r.name).join(", ")}' in row and 'aria-hidden="true"' in row
    assert tokens(open_tag(_ROW, "ul")) == {"sr-only"}
    assert "nameOf" in _ROW and "useBaseResumeLabel" in _CARD and "useBaseResumeColor" in _CARD


def test_a_click_on_the_squares_opens_the_card_like_the_link_under_them():
    assert "onClick={() => router.push(href)}" in _ROW and "useRouter()" in _ROW


def test_only_the_squares_sit_above_the_cards_link():
    """The card's link covers the face at z-10, so a title under it never shows; the squares lift to
    z-20 (as GalleryCardActions does) and the row's words stay under the link, so the card still opens."""
    assert _ROW.count('className="relative z-20') == 1 and "title=" in _ROW and _ROW.count("title=") == 1


def test_the_hover_is_one_surface_step_and_the_chips_stay_visible_on_it():
    assert "hover:bg-surface-container " in _CARD and "bg-primary/" not in _CARD
    assert "bg-surface-container px-2 group-hover/card:bg-surface-container-highest" in _CARD


def test_what_changes_the_usage_refreshes_the_cards():
    send = (_FRONTEND / "components/career/send-to-resume-dialog.tsx").read_text(encoding="utf-8")
    assert send.count('queryKey: ["kb", "entities"]') == 1
    page = (_FRONTEND / "app/base-resumes/page.tsx").read_text(encoding="utf-8")
    assert 'qc.invalidateQueries({ queryKey: ["kb", "entities"] })' in page
    assert "const invalidate = () => {" in page  # delete, archive and its undo all call it
    pill = (_FRONTEND / "components/kb-sync-pill.tsx").read_text(encoding="utf-8")
    assert 'void queryClient.invalidateQueries({ queryKey: ["kb", "entities"] });' in pill


def test_the_agent_tools_say_what_the_new_field_is():
    server = (_FRONTEND.parent / "backend/mcp_server/server.py").read_text(encoding="utf-8")
    note = "used_in_bases, the base resumes it is on (archived included, deleted excluded)."
    assert server.count(note) == 2  # kb_list_entities and kb_get_entity
