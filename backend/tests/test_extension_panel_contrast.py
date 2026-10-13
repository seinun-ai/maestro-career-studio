"""Every text-on-fill pair in the Companion panel's stylesheet clears WCAG, in both schemes.

panel.css names its own colours (`--cs-*`), and test_extension_status_roles.py pins them equal to the web
app's. This file computes what each pair READS as, with the arithmetic test_frontend_color_roles.py uses
(OKLCH -> OKLab -> linear sRGB -> relative luminance). The dark scheme is the light block with the
`prefers-color-scheme: dark` block laid over it, which is what the cascade does: a token the dark block does
not restate keeps its light value, so a missing restatement shows up here as a failing pair.
"""

from __future__ import annotations

import re

import pytest

from tests.test_extension_status_roles import _PANEL_CSS, _props
from tests.test_frontend_color_roles import _contrast, _oklab, _srgb

_LCH = re.compile(r"oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\)")


def _tokens(theme: str) -> dict[str, tuple[float, float, float]]:
    values = _props(_PANEL_CSS, ":root")
    if theme == "dark":
        dark = _PANEL_CSS.split("@media (prefers-color-scheme: dark)", 1)[1]
        values = {**values, **dict(re.findall(r"(--cs-[\w-]+):\s*([^;]+);", dark))}
    return {
        name: tuple(float(v) for v in m.groups())
        for name, value in values.items()
        if (m := _LCH.fullmatch(value.strip()))
    }


_THEMES = ("light", "dark")


def _rgb(tokens, name):
    return _srgb(_oklab(tokens[f"--cs-{name}"]))


def _mix(tokens, base, toward, weight):
    """`color-mix(in oklab, base, toward weight%)`, the hover rules' blend."""
    b, t = _oklab(tokens[f"--cs-{base}"]), _oklab(tokens[f"--cs-{toward}"])
    return _srgb(tuple((1 - weight) * x + weight * y for x, y in zip(b, t)))


# (text, fill, where it is used). Every `color:` the stylesheet puts on a fill that is not the panel's own
# surface is here, and so is every text token on the two surfaces.
_TEXT_PAIRS = [
    ("text", "surface", "body copy"),
    ("text", "surface-2", "body copy on the Next card"),
    ("muted", "surface", ".sub, .note, .ats .lbl, .qna"),
    ("muted", "surface-2", ".sub and .stg-sum inside the Next card"),
    ("muted", "muted-container", ".stg.active > button.stg-row:hover"),
    ("primary", "surface", ".linkish, .resid button"),
    ("primary", "surface-2", ".stg.active ::before (Next), .resid button in the card"),
    ("primary", "primary-tonal", ".chip.lib, .identity .linkish:hover"),
    ("on-primary", "primary", ".cta, .save"),
    ("good", "surface", ".prog .st.done, the done tick"),
    ("good", "surface-2", "the done tick inside the Next card"),
    ("good", "good-tonal", ".ats .delta, .baserow .score.good"),
    ("warn-text", "warn-tonal", ".sub.ko, .needs .opts, .needs .learn"),
    ("warn-text", "surface", ".prog .st.open, .resid.flags .kindmark"),
    ("warn-text", "surface-2", ".prog .st.open inside the Next card"),
    ("danger-text", "surface", ".note.error"),
    ("danger-text", "surface-2", ".note.error should it land in the Next card"),
    ("on-muted-container", "muted-container", ".chip.role-muted, .grp-n"),
    ("on-primary-container", "primary-container", ".chip.role-primary"),
    ("on-secondary-container", "secondary-container", ".fork .sel, .seg .on, .status-seg .on"),
    ("on-success-container", "success-container", ".chip.role-success"),
    ("on-warning-container", "warning-container", ".chip.role-warning"),
    ("on-tertiary-container", "tertiary-container", ".chip.role-tertiary"),
    ("on-error-container", "error-container", ".chip.role-error"),
]


@pytest.mark.parametrize("theme", _THEMES)
@pytest.mark.parametrize("text,fill,where", _TEXT_PAIRS, ids=[f"{t}-on-{f}" for t, f, _ in _TEXT_PAIRS])
def test_text_on_a_fill_meets_aa(theme, text, fill, where):
    tokens = _tokens(theme)
    ratio = _contrast(_rgb(tokens, text), _rgb(tokens, fill))
    assert ratio >= 4.5, f"{theme}: --cs-{text} on --cs-{fill} is {ratio:.2f}:1 ({where})"


@pytest.mark.parametrize("theme", _THEMES)
def test_the_primary_button_text_meets_aa_while_hovered(theme):
    """`.cta:hover` mixes 12% of the text colour into the fill."""
    tokens = _tokens(theme)
    ratio = _contrast(_rgb(tokens, "on-primary"), _mix(tokens, "primary", "on-primary", 0.12))
    assert ratio >= 4.5, f"{theme}: hovered .cta is {ratio:.2f}:1"


@pytest.mark.parametrize("theme", _THEMES)
def test_a_selected_segment_meets_aa_while_hovered(theme):
    """`.seg button.on:hover` and its twins mix 8% of the text colour into the fill."""
    tokens = _tokens(theme)
    fill = _mix(tokens, "secondary-container", "on-secondary-container", 0.08)
    ratio = _contrast(_rgb(tokens, "on-secondary-container"), fill)
    assert ratio >= 4.5, f"{theme}: hovered selected segment is {ratio:.2f}:1"


# Graphics that carry meaning without words need 3:1 (WCAG 1.4.11): the active bar, the radio dot and
# the focus ring in primary, the done bar in good, the radio's empty ring in muted.
_GRAPHIC_PAIRS = [
    ("primary", "surface"), ("primary", "surface-2"), ("good", "surface"), ("muted", "surface"),
    ("muted", "surface-2"),
]


@pytest.mark.parametrize("theme", _THEMES)
@pytest.mark.parametrize("graphic,surface", _GRAPHIC_PAIRS)
def test_a_graphic_meets_non_text_contrast(theme, graphic, surface):
    tokens = _tokens(theme)
    ratio = _contrast(_rgb(tokens, graphic), _rgb(tokens, surface))
    assert ratio >= 3, f"{theme}: --cs-{graphic} on --cs-{surface} is {ratio:.2f}:1"
