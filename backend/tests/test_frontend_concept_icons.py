"""One concept, one glyph (visual-language plan, Task 1).

An icon can only take over from a word if it means one thing. `lib/concept-icons.ts` is the ONE map from
a concept to its Lucide icon, the way `status-chip.tsx` is the one status vocabulary. These pins keep the
map one-to-one, keep the deprecated aliases and the drifted glyphs out, and keep text glyphs from standing
in for icons.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_REGISTER = _FRONTEND / "lib" / "concept-icons.ts"
_SOURCES = sorted(
    p
    for folder in ("app", "components", "hooks", "lib")
    for pattern in ("*.tsx", "*.ts")
    for p in (_FRONTEND / folder).rglob(pattern)
    if "node_modules" not in p.parts and not p.name.endswith(".test.ts")
)

# name -> what to use instead. Aliases first, then the glyphs whose one meaning went to another icon.
_BANNED = {
    "AlertTriangle": "TriangleAlert (same glyph, canonical name)",
    "CheckCircle2": "CircleCheck (same glyph, canonical name)",
    "MoreHorizontal": "Ellipsis (same glyph, canonical name)",
    "EllipsisVertical": "Ellipsis: More actions is drawn one way",
    "Library": "BriefcaseBusiness: the sidebar's Career history icon",
    "Briefcase": "Bot for the Agent inbox, Layers for the job-facts row",
}

_TEXT_GLYPHS = "⚠▲▼✓✅🟡⏸📎▾▸↗"


def _lucide_names(text: str) -> list[str]:
    names: list[str] = []
    for match in re.finditer(r'import\s*\{([^}]*)\}\s*from\s*"lucide-react"', text, re.S):
        for part in match.group(1).split(","):
            part = part.strip()
            if part and not part.startswith("type "):
                names.append(part.split(" as ")[0].strip())
    return names


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(^|[^:])//[^\n]*", r"\1", text)


def _register_entries() -> dict[str, str]:
    text = _REGISTER.read_text()
    body = text.split("export const CONCEPT_ICONS", 1)[1].split("} as const", 1)[0]
    body = re.sub(r"//[^\n]*", "", body)
    entries = dict(re.findall(r"^\s+(\w+):\s*(\w+),", body, re.M))
    keys = re.findall(r"^\s+\w+:", body, re.M)
    assert len(entries) == len(keys), f"{len(keys)} entries in the register, {len(entries)} parsed"
    return entries


def test_no_banned_or_alias_icon_is_imported():
    hits = [
        f"{p.relative_to(_FRONTEND)}: {name} -> {_BANNED[name]}"
        for p in _SOURCES
        for name in _lucide_names(p.read_text())
        if name in _BANNED
    ]
    assert hits == [], "\n".join(hits)


def test_the_register_maps_each_concept_to_its_own_icon():
    entries = _register_entries()
    assert len(entries) >= 25, entries
    by_icon: dict[str, list[str]] = {}
    for concept, icon in entries.items():
        by_icon.setdefault(icon, []).append(concept)
    shared = {icon: concepts for icon, concepts in by_icon.items() if len(concepts) > 1}
    assert shared == {}, f"one icon, two concepts: {shared}"


def test_the_sidebar_draws_its_sections_from_the_register():
    sidebar = (_FRONTEND / "components" / "app-sidebar.tsx").read_text()
    for concept in ("jobs", "agentInbox", "careerHistory", "baseResume", "assistant"):
        assert f"CONCEPT_ICONS.{concept}" in sidebar, concept


# Stored data, not display: the importer prefixes a career-history notes line with "⚠ stale?" and
# notes-editor.tsx parses that marker out (it never renders it).
_GLYPH_DATA_MARKERS = {"components/career/notes-editor.tsx"}


def test_no_text_glyph_stands_in_for_an_icon():
    hits = []
    for p in _SOURCES:
        if str(p.relative_to(_FRONTEND)) in _GLYPH_DATA_MARKERS:
            continue
        code = _strip_comments(p.read_text())
        for ch in _TEXT_GLYPHS:
            if ch in code:
                hits.append(f"{p.relative_to(_FRONTEND)}: {ch!r}")
    assert hits == [], "\n".join(hits)


_MUST_NOT_IMPORT = [
    ("components/career/inbox-panel.tsx", "Inbox"),
    ("components/chat/kb-capture-card.tsx", "Inbox"),
    ("components/career/entity-card.tsx", "BookOpen"),
    ("components/job-extracted-fields.tsx", "ShieldCheck"),
    ("components/job-extracted-fields.tsx", "Sparkles"),
]


def test_drifted_glyphs_are_gone_from_their_old_homes():
    hits = [f"{f}: {n}" for f, n in _MUST_NOT_IMPORT if n in _lucide_names((_FRONTEND / f).read_text())]
    assert hits == [], hits


def test_queue_and_approve_are_not_drawn_as_a_check():
    page = (_FRONTEND / "app/jobs/[id]/page.tsx").read_text()
    row = (_FRONTEND / "components/proposals/proposals-section.tsx").read_text()
    for text in (page, row):
        assert "CONCEPT_ICONS.queue" in text and "CONCEPT_ICONS.approve" in text
    assert 'label="Queue"\n                  icon={<Check />}' not in row


def test_the_career_history_add_pill_does_not_say_refresh():
    pill = (_FRONTEND / "components/kb-sync-pill.tsx").read_text()
    assert "CONCEPT_ICONS.addToCareerHistory" in pill
