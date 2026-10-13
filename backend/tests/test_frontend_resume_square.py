"""The base resume's square wherever a resume is named (resume-colour plan, Task 8).

Source pins in the style of test_frontend_resume_swatch.py: the frontend has no component runner.
"""

import re
from pathlib import Path

import pytest

from tests._jsx_pins import open_tag, squash, tokens

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

# Every site that names a base resume and has its slug or its summary. `career/points-list.tsx` and
# `use-resume-key-label.ts` are left out on purpose: their keys can be application ids.
_SITES = [
    "app/applications/page.tsx",
    "components/ats-score-panel.tsx",
    "app/jobs/[id]/tailor/[sessionId]/page.tsx",
    "components/resume-editor/editable-title.tsx",
    "components/proposals/proposals-section.tsx",
    "components/chat/proposal-card.tsx",
    "components/chat/edit-proposal-card.tsx",
    "components/chat/change-card.tsx",
    "components/application-panel.tsx",
    "app/jobs/[id]/page.tsx",
    "components/chat/chat-page.tsx",
    "components/base-resumes/new-base-resume-dialog.tsx",
    "components/resume-editor/project-port-dialog.tsx",
    "components/career/send-to-resume-dialog.tsx",
    "components/career/resume-import-dialog.tsx",
    "components/analytics/base-summary-cards.tsx",
]


def _src(path: str) -> str:
    return (_FRONTEND / path).read_text(encoding="utf-8")


@pytest.mark.parametrize("path", _SITES)
def test_the_site_draws_the_square_from_a_hue(path):
    src = _src(path)
    assert re.search(r"import \{[^}]*\bResume(Swatch|Tag)\b[^}]*\} from \"@/components/visual", src), path
    # A hue goes in: from the row, the summary or the slug's lookup, never a literal.
    assert re.search(r"<Resume(Swatch|Tag)\s+hue=\{[^}]*[A-Za-z]", src), path


@pytest.mark.parametrize("path", ["components/career/points-list.tsx", "components/career/use-resume-key-label.ts"])
def test_a_key_that_can_be_an_application_id_gets_no_square(path):
    assert "ResumeSwatch" not in _src(path) and "ResumeTag" not in _src(path)


def test_the_jobs_resume_cell_names_the_resume_in_foreground_and_keeps_the_dash_for_a_saved_job():
    page = _src("app/applications/page.tsx")
    assert "const colorOf = useBaseResumeColor();" in squash(page)
    at = page.index("colorOf(r.app.base_resume)")
    cell = page[page.rindex("<TableCell", 0, at) : page.index("</TableCell>", at)]
    assert 'r.kind === "saved"' in cell and "—" in cell
    name = open_tag(cell, "span", after="<ResumeTag")
    assert "text-foreground" in tokens(name) and "text-muted-foreground" not in tokens(name)
    # The cell itself is no longer muted: only the dash is.
    assert "text-muted-foreground" not in tokens(open_tag(cell, "TableCell"))


def test_a_score_card_carries_its_resumes_color_as_a_top_band_and_a_square_beside_the_title():
    panel = _src("components/ats-score-panel.tsx")
    card = panel[panel.index("function AtsScoreCard(") :]
    root = open_tag(card, "Card")
    # The band is the card's first child, so the card's own top padding goes.
    assert re.search(r'className=\{cn\(\s*"[^"]*\bpt-0\b', root)
    assert "...resumeColorStyle(resume?.color_hue)" in squash(card)
    band = open_tag(card, "div", after="<Card")
    assert {"h-1.5", "bg-resume"} <= tokens(band) and 'aria-hidden="true"' in band
    # The card stands for one resume, so only the band: the body is not tinted.
    assert "bg-resume-container" not in card
    title = squash(card[card.index("<CardTitle") : card.index("</CardTitle>")])
    assert "<ResumeTag hue={resume?.color_hue}" in title and "baseName(score.target_id)" in title
    assert "<AnchorPills resume={resume} />" in squash(card)


def test_the_best_pill_hides_the_square_with_the_name():
    page = _src("app/jobs/[id]/page.tsx")
    tag = open_tag(page[page.index("<ResumeTag hue={colorOf(best.target_id)}") :], "ResumeTag")
    assert "hidden" in tokens(tag) and "2xl:inline-flex" in tokens(tag)


def test_the_studio_title_keeps_its_square_while_the_name_is_edited():
    title = _src("components/resume-editor/editable-title.tsx")
    assert title.count("<ResumeSwatch hue={colorHue}") == 2
    assert "colorHue={(live ?? initial).color_hue}" in squash(_src("components/resume-editor/editor-body.tsx"))
