"""Pins the M3 colour roles in frontend/app/globals.css.

Contrast is COMPUTED from the tokens: OKLCH -> OKLab -> linear sRGB -> WCAG
relative luminance, with alpha composited in gamma-encoded sRGB, which is how
a browser blends `bg-primary/10` over a surface. Not a browser measurement,
but the same arithmetic, and it fails CI the moment a token slips below WCAG
1.4.3's 4.5:1 for normal-size text.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_CSS = (_FRONTEND / "app/globals.css").read_text()
_BUTTON = (_FRONTEND / "components/ui/button.tsx").read_text()
_BADGE = (_FRONTEND / "components/ui/badge.tsx").read_text()

_OKLCH = re.compile(r"--([\w-]+):\s*oklch\(([\d.]+)\s+([\d.]+)\s+([\d.]+)\)")


def _tokens(selector: str) -> dict[str, tuple[float, float, float]]:
    start = _CSS.index(f"{selector} {{")  # first block: the palette
    block = _CSS[start : _CSS.index("}", start)]
    return {
        m.group(1): (float(m.group(2)), float(m.group(3)), float(m.group(4)))
        for m in _OKLCH.finditer(block)
    }


LIGHT = _tokens(":root")
DARK = {**LIGHT, **_tokens(".dark")}
_MODES = {"light": LIGHT, "dark": DARK}


def _oklab(lch):
    lightness, chroma, hue = lch
    return (
        lightness,
        chroma * math.cos(math.radians(hue)),
        chroma * math.sin(math.radians(hue)),
    )


def _srgb(lab):
    lightness, a, b = lab
    l_ = lightness + 0.3963377774 * a + 0.2158037573 * b
    m_ = lightness - 0.1055613458 * a - 0.0638541728 * b
    s_ = lightness - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_**3, m_**3, s_**3
    linear = (
        4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    )

    def encode(x: float) -> float:
        x = max(0.0, x)
        return 12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055

    return tuple(min(1.0, encode(v)) for v in linear)


def _luminance(rgb) -> float:
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a, b) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _rgb(tokens, name):
    return _srgb(_oklab(tokens[name]))


def _over(fg, bg, alpha):
    return tuple(alpha * f + (1 - alpha) * b for f, b in zip(fg, bg))


def _hover(tokens, container, on):
    # Mirrors `color-mix(in oklab, container, on 8%)` in globals.css.
    c, o = _oklab(tokens[container]), _oklab(tokens[on])
    return _srgb(tuple(0.92 * x + 0.08 * y for x, y in zip(c, o)))


_PAIRS = [
    ("primary-container", "on-primary-container"),
    ("secondary-container", "on-secondary-container"),
]


@pytest.mark.parametrize("mode", list(_MODES))
@pytest.mark.parametrize("container,on", _PAIRS)
def test_container_text_meets_aa_at_rest_and_on_hover(mode, container, on):
    t = _MODES[mode]
    assert _contrast(_rgb(t, on), _rgb(t, container)) >= 4.5
    assert _contrast(_rgb(t, on), _hover(t, container, on)) >= 4.5


# Blue text sits on blue tints at ~20 hand-rolled sites. Light mode is safe up
# to /15 at tone 40; /20 is dark-mode only (see the scan below).
_TINT_CEILING = {"light": 0.15, "dark": 0.20}


@pytest.mark.parametrize("mode", list(_MODES))
def test_primary_text_on_primary_tints_meets_aa(mode):
    t = _MODES[mode]
    primary = _rgb(t, "primary")
    for surface in ("card", "background", "sidebar", "muted"):
        bg = _rgb(t, surface)
        for pct in (5, 10, 15, 20):
            if pct / 100 > _TINT_CEILING[mode]:
                continue
            ratio = _contrast(primary, _over(primary, bg, pct / 100))
            assert ratio >= 4.5, (
                f"{mode}: text-primary on bg-primary/{pct} over --{surface} "
                f"is {ratio:.2f}:1"
            )


def test_light_primary_is_m3_tone_40():
    lightness, _, _ = LIGHT["primary"]
    assert lightness <= 0.49, (
        "light --primary is M3 tone 40 (about oklch 0.48); any lighter and blue "
        "text fails AA on its own tints again"
    )


def test_no_light_mode_primary_20_tint_under_primary_text():
    offenders = []
    for root in ("app", "components"):
        for path in (_FRONTEND / root).rglob("*.tsx"):
            for n, line in enumerate(path.read_text().splitlines(), 1):
                if not re.search(r"text-primary(?![-\w])", line):
                    continue
                for tok in re.findall(r"[\w:\[\]&-]*bg-primary/20\b", line):
                    if "dark:" not in tok:
                        offenders.append(f"{path.relative_to(_FRONTEND)}:{n}: {tok}")
    assert offenders == [], offenders


def test_tonal_variants_use_secondary_container():
    for source in (_BUTTON, _BADGE):
        tonal = re.search(r'tonal:\s*"([^"]+)"', source).group(1)
        assert "bg-secondary-container" in tonal
        assert "text-on-secondary-container" in tonal
        assert "bg-primary/" not in tonal


def test_fab_variant_uses_primary_container():
    fab = re.search(r'fab:\s*"([^"]+)"', _BUTTON).group(1)
    assert "bg-primary-container" in fab
    assert "text-on-primary-container" in fab


def test_theme_exposes_role_utilities():
    for role in (
        "primary-container",
        "on-primary-container",
        "primary-container-hover",
        "secondary-container",
        "on-secondary-container",
        "secondary-container-hover",
        "canvas",
    ):
        assert f"--color-{role}: var(--{role});" in _CSS
