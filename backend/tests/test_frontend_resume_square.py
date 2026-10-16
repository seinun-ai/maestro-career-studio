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
# The Jobs list is not one: its Resume column went, and only its Match score names a resume, on hover.
_SITES = [
    "components/resume-chips.tsx",
    "components/score-summary.tsx",
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


# Files that draw the square in more than one place, with how many: a picker draws it in its trigger and in each
# item, the studio title in its reading and its editing state.
_TWO_SITES = {
    "components/chat/chat-page.tsx",
    "components/resume-editor/editable-title.tsx",
    "components/base-resumes/new-base-resume-dialog.tsx",
    "components/resume-editor/project-port-dialog.tsx",
    "components/career/send-to-resume-dialog.tsx",
}


@pytest.mark.parametrize("path", _SITES)
def test_the_site_draws_the_square_from_a_hue(path):
    src = _src(path)
    assert re.search(r"import \{[^}]*\bResume(Swatch|Tag)\b[^}]*\} from \"@/components/visual", src), path
    # A hue goes in: from the row, the summary or the slug's lookup, never a literal.
    hued = re.findall(r"<Resume(?:Swatch|Tag)\s+hue=\{(?!null\}|undefined\})[^}]*[A-Za-z]", src)
    assert len(hued) == (2 if path in _TWO_SITES else 1), path


@pytest.mark.parametrize("path", [p for p in _SITES if p != "app/jobs/[id]/page.tsx"])  # its pill's own title names it
def test_a_name_that_truncates_beside_the_square_carries_its_whole_value_in_title(path):
    """A truncated base resume name has no other way to be read: not on hover, and a trigger shows only the value."""
    src = _src(path)
    for block in re.findall(r"<ResumeTag\b.*?</ResumeTag>", src, re.S):
        spans = [open_tag(block[m.start() :], "span") for m in re.finditer(r"<span\b", block)]
        for span in spans:
            assert "truncate" not in tokens(span) or "title={" in span, f"{path}: {span}"


@pytest.mark.parametrize("path", ["components/career/points-list.tsx", "components/career/use-resume-key-label.ts"])
def test_a_key_that_can_be_an_application_id_gets_no_square(path):
    assert "ResumeSwatch" not in _src(path) and "ResumeTag" not in _src(path)


def test_each_resume_chip_and_the_breakdown_carry_the_resumes_square():
    chips = _src("components/resume-chips.tsx")
    # The chip names one resume: its square, then its name, which truncates with its whole value on the chip.
    assert "<ResumeSwatch hue={r.hue} />" in chips
    assert "title={r.name}" in open_tag(chips[chips.index("<button") :], "button")
    assert "hue: allResumes?.find((r) => r.slug === row.target_id)?.color_hue," in _src("components/resume-step.tsx")
    summary = _src("components/score-summary.tsx")
    title = squash(summary[summary.index("<PopoverTitle") : summary.index("</PopoverTitle>")])
    assert "<ResumeTag hue={resume?.color_hue}" in title and 'title={name}' in title
    assert "{resume && <AnchorPills resume={resume} />}" in summary


def test_the_best_pill_hides_the_square_with_the_name():
    page = _src("app/jobs/[id]/page.tsx")
    tag = open_tag(page[page.index("<ResumeTag hue={colorOf(scoreResume)}") :], "ResumeTag")
    assert "hidden" in tokens(tag) and "2xl:inline-flex" in tokens(tag)


def test_the_studio_title_keeps_its_square_while_the_name_is_edited():
    title = _src("components/resume-editor/editable-title.tsx")
    assert title.count("<ResumeSwatch hue={colorHue}") == 2
    assert "colorHue={(live ?? initial).color_hue}" in squash(_src("components/resume-editor/editor-body.tsx"))
