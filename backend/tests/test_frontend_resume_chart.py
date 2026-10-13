"""The chart split by base resume draws each series in its resume's color (resume-colour plan, Task 9)."""

import re
from pathlib import Path

from tests._jsx_pins import open_tag, squash

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_CHART = (_FRONTEND / "components/charts/fit-distribution-chart.tsx").read_text(encoding="utf-8")
_TONES = (_FRONTEND / "hooks/use-resume-swatch-tones.ts").read_text(encoding="utf-8")
_CHARTS_DIR = _FRONTEND / "components/charts"


def test_each_series_is_filled_with_its_resumes_swatch_color():
    bar = open_tag(_CHART, "Bar")
    assert "fill={resumeSwatchColor(colorOf(row.base_resume), tones)}" in bar
    assert "const colorOf = useBaseResumeColor();" in _CHART
    # Its colour no longer comes from the categorical palette.
    assert "COLORS" not in _CHART


def test_the_legend_is_the_resumes_squares_beside_their_names():
    legend = squash(_CHART[_CHART.index("<Legend") : _CHART.index("{drawn.map")])
    assert "<ResumeTag hue={colorOf(String(entry.dataKey))}>{entry.value}</ResumeTag>" in legend


def test_the_tones_are_read_from_the_css_variables_not_redeclared():
    """globals.css is the one home of the tones, light and dark: no 0.52 or 0.76 here."""
    assert 'getPropertyValue("--resume-swatch-l")' in _TONES
    assert 'getPropertyValue("--resume-swatch-c")' in _TONES
    assert "getComputedStyle(document.documentElement)" in _TONES
    assert not re.search(r"\b0\.\d\d\b", _TONES)


def test_the_chart_re_renders_when_the_theme_changes():
    """next-themes swaps `.dark` on <html>: the hook re-reads when the class changes, so the bars follow."""
    assert 'attributeFilter: ["class"]' in _TONES
    assert "new MutationObserver(onChange)" in _TONES
    assert "useSyncExternalStore(subscribe, readTones" in _TONES
    assert "useResumeSwatchTones()" in _CHART


def test_every_other_chart_keeps_the_categorical_palette():
    """Only a chart split by base resume takes resume colors (design-system README, Color)."""
    others = [p for p in sorted(_CHARTS_DIR.glob("*.tsx")) if p.name != "fit-distribution-chart.tsx"]
    assert others
    assert [p.name for p in others if "resumeSwatchColor" in p.read_text(encoding="utf-8")] == []
