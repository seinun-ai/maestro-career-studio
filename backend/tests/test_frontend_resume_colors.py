"""Pins the base resume colour recipe in frontend/app/globals.css.

A base resume stores one hue. The stylesheet turns it into three colours
(`resume`, `resume-container`, `on-resume-container`) from per-theme tone
numbers, so a custom hue clears contrast the same way a preset does. This
file computes the result for every preset and for a sweep of hues, in both
themes, with the arithmetic test_frontend_color_roles uses.
"""

from __future__ import annotations

import re

import pytest

from tests.test_frontend_color_roles import (
    _CSS,
    _FRONTEND,
    _MODES,
    _block,
    _contrast,
    _oklab,
    _rgb,
    _srgb,
)
from tests.test_frontend_design_tokens import _linear_srgb

_TONES = (
    "resume-swatch-l",
    "resume-swatch-c",
    "resume-container-l",
    "resume-container-c",
    "on-resume-container-l",
    "on-resume-container-c",
)
_CUSTOM_CHROMA = 0.1


def _tones(selector: str) -> dict[str, float]:
    block = _block(selector)
    found = {}
    for name in _TONES:
        match = re.search(rf"--{name}:\s*([\d.]+);", block)
        assert match, f"{selector} declares no --{name}"
        found[name] = float(match.group(1))
    return found


def _presets() -> list[tuple[int, float]]:
    """The (hue, chroma) pairs the app ships, read from the table the app imports."""
    source = (_FRONTEND / "lib/resume-color.ts").read_text(encoding="utf-8")
    pairs = re.findall(r"hue:\s*(\d+),\s*chroma:\s*([\d.]+)", source)
    assert len(pairs) == 10, pairs
    return [(int(h), float(c)) for h, c in pairs]


def _derived(mode: str, hue: float, chroma: float) -> dict[str, tuple[float, float, float]]:
    """The three colours as a browser computes them: oklch(L, hue chroma x C-factor, hue)."""
    t = _tones(":root" if mode == "light" else ".dark")
    return {
        "resume": (t["resume-swatch-l"], chroma * t["resume-swatch-c"], hue),
        "resume-container": (t["resume-container-l"], chroma * t["resume-container-c"], hue),
        "on-resume-container": (t["on-resume-container-l"], chroma * t["on-resume-container-c"], hue),
    }


def _hues():
    for hue, chroma in _presets():
        yield pytest.param(hue, chroma, id=f"preset-{hue}")
    for hue in range(0, 360, 5):
        yield pytest.param(hue, _CUSTOM_CHROMA, id=f"sweep-{hue}")


@pytest.mark.parametrize("mode", list(_MODES))
@pytest.mark.parametrize("hue,chroma", list(_hues()))
def test_the_text_on_the_container_meets_aa(mode, hue, chroma):
    c = _derived(mode, hue, chroma)
    ratio = _contrast(_srgb(_oklab(c["on-resume-container"])), _srgb(_oklab(c["resume-container"])))
    assert ratio >= 4.5, f"{mode} hue {hue}: on-resume-container on resume-container is {ratio:.2f}:1"


@pytest.mark.parametrize("mode", list(_MODES))
@pytest.mark.parametrize("hue,chroma", list(_hues()))
def test_what_the_picker_draws_on_the_square_reads(mode, hue, chroma):
    """The selected Check (primary-foreground) and the taken marker (card) sit ON a preset's square."""
    square = _srgb(_oklab(_derived(mode, hue, chroma)["resume"]))
    for mark in ("primary-foreground", "card"):
        ratio = _contrast(_rgb(_MODES[mode], mark), square)
        assert ratio >= 3, f"{mode} hue {hue}: {mark} on resume is {ratio:.2f}:1"


@pytest.mark.parametrize("mode", list(_MODES))
@pytest.mark.parametrize("hue,chroma", list(_hues()))
def test_the_square_reads_on_the_page_and_on_a_card(mode, hue, chroma):
    """A graphic that sits beside its name needs 3:1 (WCAG 1.4.11)."""
    square = _srgb(_oklab(_derived(mode, hue, chroma)["resume"]))
    for surface in ("card", "background"):
        ratio = _contrast(square, _rgb(_MODES[mode], surface))
        assert ratio >= 3, f"{mode} hue {hue}: resume on {surface} is {ratio:.2f}:1"


# The approved presets and the light tones sit a hair outside sRGB at some hues (the
# worst overshoot is 0.017 in linear light: a teal square at L 0.52, a blue container).
# A browser clips that to the nearest displayable colour, which is what the contrast
# tests above measure (`_srgb` clamps). The design-tokens test allows 1e-4 because every
# status role fits; this recipe is a sweep of ALL hues, so the bound is 0.02, enough to
# fail a tone change that pushes a hue visibly past the edge.
_GAMUT_SLACK = 0.02


@pytest.mark.parametrize("mode", list(_MODES))
@pytest.mark.parametrize("hue,chroma", list(_hues()))
def test_every_derived_colour_stays_near_srgb(mode, hue, chroma):
    """`_srgb` clamps silently, so the gamut is checked on the unclamped linear values."""
    for name, lch in _derived(mode, hue, chroma).items():
        channels = _linear_srgb(_oklab(lch))
        assert all(-_GAMUT_SLACK <= v <= 1 + _GAMUT_SLACK for v in channels), (
            f"{mode} hue {hue}: --{name} is outside sRGB: {channels}"
        )


# These three live in `@theme inline` and nowhere else. A custom property declared on
# :root resolves its var()s there, where no resume's hue exists, so every child would
# inherit grey; `inline` makes the utility carry the expression and resolve it on the
# element that sets --resume-h. They also cannot move to :root/.dark because
# test_frontend_color_roles._tokens parses those blocks with `oklch\(([^)]*)\)` and
# asserts on any oklch() it cannot read as `L C H`.
_EXPECTED_THEME_LINES = {
    "resume": "--color-resume: oklch(var(--resume-swatch-l) calc(var(--resume-c, 0) * var(--resume-swatch-c)) var(--resume-h, 0));",
    "resume-container": "--color-resume-container: oklch(var(--resume-container-l) calc(var(--resume-c, 0) * var(--resume-container-c)) var(--resume-h, 0));",
    "on-resume-container": "--color-on-resume-container: oklch(var(--on-resume-container-l) calc(var(--resume-c, 0) * var(--on-resume-container-c)) var(--resume-h, 0));",
}


def test_the_three_colours_are_theme_inline_lines():
    theme = _CSS[_CSS.index("@theme inline {") : _CSS.index("\n}\n", _CSS.index("@theme inline {"))]
    for name, expected in _EXPECTED_THEME_LINES.items():
        assert expected in theme, f"@theme inline lacks the {name} line, exactly as written"
    for selector in (":root", ".dark"):
        assert "--color-resume" not in _block(selector), f"{selector} must not declare the resume colours"


def test_the_tones_are_the_recipe():
    assert _tones(":root") == {
        "resume-swatch-l": 0.52, "resume-swatch-c": 1.0,
        "resume-container-l": 0.93, "resume-container-c": 0.36,
        "on-resume-container-l": 0.38, "on-resume-container-c": 0.82,
    }
    assert _tones(".dark") == {
        "resume-swatch-l": 0.76, "resume-swatch-c": 0.9,
        "resume-container-l": 0.33, "resume-container-c": 0.45,
        "on-resume-container-l": 0.90, "on-resume-container-c": 0.40,
    }
