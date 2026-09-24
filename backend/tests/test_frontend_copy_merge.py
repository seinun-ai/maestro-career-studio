"""Words that two wave-3 copy lanes each owned half of, pinned at the merge
(docs/plans/2026-09-23-ux-ia-copy.md, the lane docs' "Deferred to merge").
Each pin reads both sides of a seam, so one side moving alone fails here."""

from __future__ import annotations

import re
from pathlib import Path

from app.schemas import resume as resume_schema

_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND = _ROOT / "frontend"
_GAP_PAGE = "app/jobs/[id]/tailor/[sessionId]/page.tsx"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


def test_the_coverage_warning_is_said_once():
    # The server's coverage_warning already says "Your resume shows only 1 of
    # this job's 8 skills (13%)."; a second line restating it went.
    for rel in ("components/ats-score-panel.tsx", _GAP_PAGE):
        src = _read(rel)
        assert "recognized only" not in src, rel
        assert "coverage_ratio" not in src, rel
    assert "<p className=\"font-medium\">{gapsJson.coverage_warning}</p>" in _read(_GAP_PAGE)


def test_a_stale_reason_is_a_clause_the_frame_finishes():
    page = _read(_GAP_PAGE)
    assert "This gap analysis is out of date because {staleReason}.{\" \"}" in page
    src = (_ROOT / "backend/app/services/tailoring_session.py").read_text(encoding="utf-8")
    body = src[src.index("def staleness_reason(") : src.index("\ndef ", src.index("def staleness_reason("))]
    reasons = re.findall(r'"(the [^"]+)"', body)
    assert len(reasons) == 4, reasons
    assert all(r[-1].isalpha() for r in reasons), reasons


def test_the_blocklist_refusal_names_the_setting_as_labelled():
    label = re.search(r'<Label htmlFor="aa-blocklist">([^<]+)</Label>', _read("components/settings/auto-apply-section.tsx"))
    assert label and label.group(1) == "Companies to skip"
    router = (_ROOT / "backend/app/routers/proposals.py").read_text(encoding="utf-8")
    assert f"your {label.group(1)} list in Settings › " in router
    tab = re.search(r'value: "agents",\s*label: "([^"]+)"', _read("lib/settings-tabs.ts"))
    assert tab and f'"{tab.group(1)}.")' in router


def test_the_section_name_clash_says_the_same_on_both_sides():
    ts = re.search(r"export const TITLE_COLLISION_MESSAGE =\s*\"([^\"]+)\";", _read("lib/resume-schema.ts"))
    assert ts and ts.group(1) == resume_schema.TITLE_COLLISION_MESSAGE
    assert resume_schema.TITLE_COLLISION_MESSAGE == "A section with this name already exists. Choose another name."


def test_new_base_resume_counts_approved_bullets_from_the_server():
    dialog = _read("components/base-resumes/new-base-resume-dialog.tsx")
    assert "(approvedCount(e) > 0 || rendersWithoutPoints(e.kind))" in dialog
    assert "const approvedCount = (e: KBEntitySummary) => e.approved_count;" in dialog
    assert "point_count - e.draft_count" not in dialog
    assert re.search(r"\n  approved_count: number;\n", _read("lib/types.ts"))


def test_a_left_out_part_reads_as_sentences():
    dialog = _read("components/base-resumes/new-base-resume-dialog.tsx")
    assert 'toast.warning(`Imported. ${created.parse_warnings.join(" ")} Check the resume in the editor.`);' in dialog
    assert 'join("; ")' not in dialog


def test_import_hints_name_what_their_picker_takes():
    one = _read("components/base-resumes/new-base-resume-dialog.tsx")
    assert "hint={`${acceptedTypesLabel(RESUME_FILE_ACCEPT)}. Up to 10 MB.`}" in one
    many = _read("components/career/resume-import-dialog.tsx")
    assert "hint={`${acceptedTypesLabel(ACCEPT)}. Up to ${MAX_FILES} files, 10 MB each.`}" in many
    for src in (one, many):
        assert "own JSON" not in src and "Word or text file" not in src


def test_a_button_that_opens_the_import_dialog_says_its_title():
    title = re.search(r"<DialogTitle>([^<]+)</DialogTitle>", _read("components/setup/upload-dialog.tsx"))
    assert title and title.group(1) == "Import resumes and documents"
    for rel in ("app/career/page.tsx", "components/ats-score-panel.tsx"):
        src = _read(rel)
        assert "<UploadDialog" in src, rel
        assert re.search(rf">\s*(?:<Upload aria-hidden=\"true\" /> )?{title.group(1)}\s*<", src), rel
