"""The chart split by base resume draws each series in its resume's color (resume-colour plan, Task 9)."""

from pathlib import Path

from tests._jsx_pins import open_tag, squash

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_LIB = (_FRONTEND / "lib/resume-color.ts").read_text(encoding="utf-8")
_GLOBALS = (_FRONTEND / "app/globals.css").read_text(encoding="utf-8")
_CHART = (_FRONTEND / "components/charts/fit-distribution-chart.tsx").read_text(encoding="utf-8")
_CHARTS_DIR = _FRONTEND / "components/charts"


def test_each_series_is_filled_with_its_resumes_swatch_color():
    bar = open_tag(_CHART, "Bar")
    assert "fill={resumeFill(colorOf(row.base_resume))}" in bar
    assert "const colorOf = useBaseResumeColor();" in _CHART
    # Its colour no longer comes from the categorical palette.
    assert "COLORS" not in _CHART


def test_the_legend_is_the_resumes_squares_beside_their_names():
    legend = squash(_CHART[_CHART.index("<Legend") : _CHART.index("{drawn.map")])
    assert "<ResumeTag hue={colorOf(String(entry.dataKey))}>{entry.value}</ResumeTag>" in legend


def test_the_fill_leaves_the_tones_to_css_so_the_theme_follows_with_no_js():
    """globals.css is the one home of the tones, light and dark; the fill names them as var()s, as chart-kit's palette does."""
    assert not (_FRONTEND / "hooks/use-resume-swatch-tones.ts").exists()
    fill = _LIB[_LIB.index("export function resumeFill") :]
    assert "oklch(var(--resume-swatch-l) calc(${chroma} * var(--resume-swatch-c)) ${hue ?? 0})" in fill
    css = _GLOBALS
    assert css.count("--resume-swatch-l:") == 2 and css.count("--resume-swatch-c:") == 2  # :root and .dark
    # The same recipe as the `resume` colour.
    assert "oklch(var(--resume-swatch-l) calc(var(--resume-c, 0) * var(--resume-swatch-c)) var(--resume-h, 0))" in css


def test_every_other_chart_keeps_the_categorical_palette():
    """Only a chart split by base resume takes resume colors (design-system README, Color)."""
    others = [p for p in sorted(_CHARTS_DIR.glob("*.tsx")) if p.name != "fit-distribution-chart.tsx"]
    assert others
    assert [p.name for p in others if "resumeFill" in p.read_text(encoding="utf-8")] == []
