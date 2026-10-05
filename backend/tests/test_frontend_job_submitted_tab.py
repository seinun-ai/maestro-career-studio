"""Pins: the job page's What was submitted tab (docs/entities/filled-answers.md).

Read-only: every answer the Companion or a connected agent filled, the latest per question, a
source pill each, the warn-only flags, the voluntary (EEO) answers shown on demand. There is no
frontend test runner, so the branches that matter are pinned from the source.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


_PAGE = _read("app/jobs/[id]/page.tsx")
_TAB = _read("components/job-submitted-tab.tsx")
_LIB = _read("lib/filled-answers.ts")
_TYPES = _read("lib/types.ts")


def test_the_tab_is_deep_linkable_and_shown_once_something_was_filled():
    assert 'const JOB_TABS = ["jd", "fit", "output", "qa", "submitted"] as const;' in _PAGE
    assert '<TabsTrigger value="submitted">What was submitted</TabsTrigger>' in _PAGE
    assert 'Boolean(data?.has_filled_answers) || submittedSeen' in _PAGE
    assert "has_filled_answers: boolean;" in _TYPES


def test_the_trigger_stays_once_the_tab_was_opened():
    """The job's own flag may predate a fill, so a visit keeps the trigger in the row."""
    assert 'const [submittedSeen, setSubmittedSeen] = useState(tab === "submitted");' in _PAGE
    assert 'if (tab === "submitted" && !submittedSeen) setSubmittedSeen(true);' in _PAGE


def test_the_tab_is_not_locked_behind_an_application():
    trigger = _PAGE[_PAGE.index('<TabsTrigger value="submitted">'):]
    assert "lockedProps" not in trigger.split("</TabsTrigger>")[0]
    content = _PAGE.index('<TabsContent value="submitted"')
    assert content < _PAGE.index("{application ? (")


def test_the_receipt_is_fetched_only_while_its_tab_is_open_and_never_from_a_stale_cache():
    assert "apiFetch<FilledAnswers>(`/api/jobs/${jobId}/filled-answers`)" in _TAB
    assert 'queryKey: ["filled-answers", jobId]' in _TAB
    assert "enabled: active," in _TAB
    assert "staleTime: 0," in _TAB
    assert 'active={tab === "submitted"}' in _PAGE


@pytest.mark.parametrize(("source", "word"), [
    ("profile", "Profile"), ("resume", "Resume"), ("custom", "Custom"), ("written", "Written"),
    ("inferred", "Inferred"), ("you", "You"), ("upload", "Upload"),
])
def test_each_source_has_its_pill_word(source, word):
    assert f'  {source}: "{word}",' in _LIB


def test_the_header_names_the_host_the_pages_and_the_count_to_check():
    assert '`Filled on ${receipt.host ?? "the employer\'s site"}`' in _LIB
    assert '`${receipt.flag_count} to check`' in _TAB
    assert "document.getElementById(first)?.focus()" in _TAB


def test_the_header_counts_the_page_blocks_shown_not_the_backends_pages():
    """A page of only voluntary questions has no block; the header must agree with the blocks."""
    assert "receiptHeading(receipt, steps.length, date)" in _TAB
    assert "shown > 0 ?" in _LIB
    assert "receipt.pages" not in _LIB
    assert "receipt.pages" not in _TAB


@pytest.mark.parametrize("words", [
    "Nothing filled yet.",
    "When the Companion or a connected agent fills this job's form, every answer shows here.",
    "Couldn't load what was submitted.",
    "Diversity questions (voluntary)",
    '"Hide answers" : "Show answers"',
    "Answer hidden",
    "Edited by you",
    "Answered. Not kept without your consent.",
    "`Resume attached: ${name}",
    "(version ${field.version})",
    "`Cover letter attached: ${name}`",
])
def test_the_tabs_words(words):
    assert words in _TAB


def test_voluntary_answers_are_hidden_until_asked_for_each_visit():
    assert "const [open, setOpen] = useState(false);" in _TAB
    assert "hidden={!open}" in _TAB
    assert "localStorage" not in _TAB and "sessionStorage" not in _TAB


def test_a_flag_is_a_warning_mark_with_its_reason_never_color_alone():
    assert re.search(r'text-warning">\s*<AlertTriangle', _TAB)
    assert "{flag.reason}" in _TAB


def test_uploads_link_to_the_resume_and_q_and_a_tabs_only_when_those_tabs_are_open():
    assert "if (!onOpenTab) return <p" in _TAB
    assert 'onOpenTab(resume ? "output" : "qa")' in _TAB
    assert "onOpenTab={application ? setTab : undefined}" in _PAGE


def test_the_knockout_card_points_an_on_site_gap_at_the_preferences():
    assert '  on_site: "preferences",' in _read("components/job-knockout-card.tsx")
    assert '"experience" | "on_site";' in _TYPES
