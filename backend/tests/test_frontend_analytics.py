"""CI pins for the Analytics labels and colours. Node tests are not in CI, so
the behaviour of lib/analytics-series.ts and lib/humanize-slug.ts is pinned
here at the source, alongside the call sites that must use them. One pin per
case, so a revert names exactly what it broke."""

import re
from pathlib import Path

import pytest

from app.services import role_categories

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


_SERIES = "lib/analytics-series.ts"
_ATS = "components/charts/ats-over-time-chart.tsx"
_MIX = "components/charts/role-mix-chart.tsx"
_FIT = "components/charts/fit-distribution-chart.tsx"
_HEATMAP = "components/charts/heatmap-chart.tsx"
_LIFT = "components/charts/tailoring-lift-chart.tsx"
_OVERVIEW = "components/explore/explore-overview.tsx"
_GAPS = "components/analytics/gap-tiers-panel.tsx"
_PICKER = "components/role-category-picker.tsx"
_CHIP = "components/status-chip.tsx"
_CAREER = "app/career/page.tsx"
_DRAWER = "components/resume-editor/kb-import-drawer.tsx"

_PRESENT = {
    # lib/analytics-series.ts: heaviest first, key ascending on ties, then cap.
    "series-cap": (_SERIES, "export const MAX_ROLE_SERIES = 4"),
    "series-rank": (_SERIES, ".sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))"),
    "series-split": (_SERIES, "shown: ranked.slice(0, max), hidden: ranked.slice(max)"),
    # Charts draw the head and name the tail; they never cycle the palette.
    "ats-split": (_ATS, "splitTopSeries(data, (row) => row.role_category, (row) => row.n)"),
    "ats-hidden-caption": (_ATS, "Pick a role above to see the other ${hidden.length}."),
    "mix-split": (_MIX, "splitTopSeries("),
    "mix-more-roles": (_MIX, 'name={cat === MORE_ROLES ? "More roles" : label(cat)}'),
    "fit-cap-at-palette": (_FIT, "(row) => row.n,\n      COLORS.length,"),
    "fit-hidden-caption": (_FIT, '${hidden.length} more ${hidden.length === 1 ? "is" : "are"} not shown.'),
    # The legend says the resume's own name; the slug stays the dataKey
    # because two resumes may share a display name.
    "fit-name": (_FIT, "name={row.display_name ?? baseResumeLabel(row.base_resume)}"),
    "fit-datakey": (_FIT, "dataKey={row.base_resume}"),
    # Role text comes from the catalog label, never the slug.
    "heatmap-label": (_HEATMAP, "{label(role)}"),
    "overview-salary-label": (_OVERVIEW, "{label(r.role_category)}"),
    "overview-mix-label": (_OVERVIEW, "label: label(row.key),"),
    "lift-label": (_LIFT, "role: label(r.role_category),"),
    # The Skill-gaps panel renders the server's words.
    "gaps-server-label": (_GAPS, "row.category_label ?? null"),
    # Label fallback while the catalog loads or fails: the acronym-safe humanizer.
    "picker-fallback": (_PICKER, "return hit ? hit.label : humanizeSlug(key);"),
    "resume-fallback": ("lib/types.ts", "return name || humanizeSlug(slug);"),
    "humanizer-slash-pair": ("lib/humanize-slug.ts", 'SLASH_PAIRS = new Set(["ai_ml"'),
    # "Needs you" is one object; the KB section is Basics everywhere.
    "needs-decision": (_CHIP, "needs_decision: NEEDS_YOU,"),
    "needs-human": (_CHIP, "needs_human: NEEDS_YOU,"),
    "career-tab-default": (_CAREER, 'useState("basics")'),
    "career-tab": (_CAREER, '<TabsTrigger value="basics">Basics</TabsTrigger>'),
    "drawer-tab": (_DRAWER, '<TabsTrigger value="basics">Basics</TabsTrigger>'),
}

# Regexes, matched per line.
_ABSENT = {
    "heatmap-raw-role": (_HEATMAP, r"^\s*\{role\}$"),
    "heatmap-raw-title": (_HEATMAP, r"· \$\{role\}"),
    "overview-raw-role": (_OVERVIEW, r"^\s*\{r\.role_category\}$"),
    "gaps-local-map": (_GAPS, "CATEGORY_LABEL"),
    "resume-acronym-map": ("lib/types.ts", "SLUG_ACRONYMS"),
    "career-profile-tab": (_CAREER, ">Profile<"),
    "drawer-profile-tab": (_DRAWER, ">Profile<"),
}


@pytest.mark.parametrize("rel,snippet", list(_PRESENT.values()), ids=list(_PRESENT))
def test_source_pin_present(rel, snippet):
    assert snippet in _read(rel)


@pytest.mark.parametrize("rel,pattern", list(_ABSENT.values()), ids=list(_ABSENT))
def test_source_pin_absent(rel, pattern):
    assert not re.search(pattern, _read(rel), re.M)


_ROLE_LABEL_USERS = (_HEATMAP, _OVERVIEW, _LIFT, _ATS, _MIX, "app/analytics/page.tsx")


@pytest.mark.parametrize("rel", _ROLE_LABEL_USERS)
def test_analytics_role_text_uses_the_catalog_label(rel):
    assert "useRoleLabel()" in _read(rel)


def test_charts_never_index_the_palette_modulo():
    cycling = [
        f"{path.name}: {m.group(0)}"
        for path in sorted((_FRONTEND / "components/charts").glob("*.tsx"))
        for m in re.finditer(r"COLORS\[[^\]]*%", path.read_text())
    ]
    assert cycling == [], cycling


def test_the_humanizer_replaced_lib_format():
    assert not (_FRONTEND / "lib/format.ts").exists()


def test_needs_you_sits_above_the_proposal_chip_doc():
    # The JSDoc ends right on the constant it documents.
    assert "*/\nexport const PROPOSAL_STATUS_CHIP" in _read(_CHIP)


def test_humanizer_cases_every_catalog_acronym():
    """While /api/role-categories loads or fails, labels come from the slug.
    Every token the catalog spells other than Title Case must be in TOKEN_CASE,
    so "AI/ML Engineer" never reads "Ai Ml Engineer"."""
    source = _read("lib/humanize-slug.ts")
    block = source[source.index("const TOKEN_CASE") : source.index("};")]
    cased = dict(re.findall(r'^\s*(\w+): "([^"]+)",$', block, re.M))
    missing = []
    for key, label in role_categories.labels().items():
        words = {word.lower(): word for word in re.split(r"[\s/]+", label)}
        for token in key.split("_"):
            word = words.get(token)
            if word and word != token.capitalize() and cased.get(token) != word:
                missing.append(f"{key}: {token} -> {word}")
    assert missing == [], missing
