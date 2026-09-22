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


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


_CSS = _read("app/globals.css")
_BUTTON = _read("components/ui/button.tsx")
_BADGE = _read("components/ui/badge.tsx")
_HEALTH = _read("components/resume-health/health-report-page.tsx")
_STUDIO = _read("components/resume-editor/tailored-resume-studio.tsx")

_OKLCH_DECL = re.compile(r"--([\w-]+):\s*oklch\(([^)]*)\)")
_LCH = re.compile(r"([\d.]+)\s+([\d.]+)\s+([\d.]+)")


def _block(selector: str) -> str:
    start = _CSS.index(f"{selector} {{")  # first block: the palette
    return _CSS[start : _CSS.index("}", start)]


def _tokens(selector: str) -> tuple[set[str], dict[str, tuple[float, float, float]]]:
    """Every custom property the block declares, and its plain oklch values.

    Loud on an oklch() it cannot read: skipping one used to let DARK fall back
    to the LIGHT value and pass on the wrong colour. Alpha values (`.dark`'s
    --border and --input) are skipped on purpose; a test that asks for one
    gets a KeyError, not a stand-in.
    """
    block = _block(selector)
    parsed = {}
    for m in _OKLCH_DECL.finditer(block):
        name, value = m.group(1), m.group(2).strip()
        if "/" in value:
            continue
        lch = _LCH.fullmatch(value)
        assert lch, f"{selector} --{name}: cannot read oklch({value}) as `L C H`"
        parsed[name] = tuple(float(v) for v in lch.groups())
    return set(re.findall(r"--([\w-]+):", block)), parsed


_, LIGHT = _tokens(":root")
_DARK_DECLARED, _DARK_OWN = _tokens(".dark")
# .dark inherits a :root value only for a name it does not declare at all.
DARK = {
    **{k: v for k, v in LIGHT.items() if k not in _DARK_DECLARED},
    **_DARK_OWN,
}
_MODES = {"light": LIGHT, "dark": DARK}

# `--X-hover: color-mix(in oklab, var(--X), var(--on-X) N%)`, read from the
# CSS so the test blends what the browser blends.
_HOVER_MIX = {
    m.group(1): (m.group(2), m.group(3), float(m.group(4)) / 100)
    for m in re.finditer(
        r"--([\w-]+)-hover:\s*color-mix\(in oklab,\s*var\(--([\w-]+)\),"
        r"\s*var\(--([\w-]+)\)\s+([\d.]+)%\)",
        _block(":root"),
    )
}


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
    l_lin, m_lin, s_lin = l_**3, m_**3, s_**3
    linear = (
        4.0767416621 * l_lin - 3.3077115913 * m_lin + 0.2309699292 * s_lin,
        -1.2684380046 * l_lin + 2.6097574011 * m_lin - 0.3413193965 * s_lin,
        -0.0041960863 * l_lin - 0.7034186147 * m_lin + 1.7076147010 * s_lin,
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


def _hover(tokens, container, on, weight):
    # `color-mix(in oklab, container, on N%)`: N% on-colour, blended in OKLab.
    c, o = _oklab(tokens[container]), _oklab(tokens[on])
    return _srgb(tuple((1 - weight) * x + weight * y for x, y in zip(c, o)))


_PAIRS = [
    ("primary-container", "on-primary-container"),
    ("secondary-container", "on-secondary-container"),
]


@pytest.mark.parametrize("mode", list(_MODES))
@pytest.mark.parametrize("container,on", _PAIRS)
def test_container_text_meets_aa_at_rest_and_on_hover(mode, container, on):
    t = _MODES[mode]
    mix = _HOVER_MIX.get(container)
    assert mix, f"--{container}-hover is not `color-mix(in oklab, var(), var() N%)`"
    assert mix[:2] == (container, on), f"--{container}-hover mixes {mix[:2]}"
    assert _contrast(_rgb(t, on), _rgb(t, container)) >= 4.5
    assert _contrast(_rgb(t, on), _hover(t, container, on, mix[2])) >= 4.5


# Blue text sits on blue tints at ~20 hand-rolled sites. Light mode is safe up
# to /15 at tone 40; /20 is dark-mode only (the scan below holds both).
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


def test_primary_text_tints_stay_under_the_ceiling():
    offenders = []
    for root in ("app", "components"):
        for path in (_FRONTEND / root).rglob("*.tsx"):
            lines = path.read_text(encoding="utf-8").splitlines()
            for n, line in enumerate(lines, 1):
                if not re.search(r"text-primary(?![-\w])", line):
                    continue
                for tok, pct in re.findall(r"([\w:\[\]&-]*bg-primary/(\d+))\b", line):
                    mode = "dark" if "dark:" in tok else "light"
                    if int(pct) / 100 > _TINT_CEILING[mode]:
                        offenders.append(f"{path.relative_to(_FRONTEND)}:{n}: {tok}")
    assert offenders == [], offenders


def _variant(source: str, name: str, where: str) -> str:
    m = re.search(rf'\b{name}:\s*"([^"]+)"', source)
    assert m, f"{where}: no `{name}` variant written as one string literal"
    return m.group(1)


def test_tonal_variants_use_secondary_container():
    for where, source in (("button.tsx", _BUTTON), ("badge.tsx", _BADGE)):
        tonal = _variant(source, "tonal", where)
        assert "bg-secondary-container" in tonal
        assert "text-on-secondary-container" in tonal
        assert "bg-primary/" not in tonal
        assert "text-primary" not in tonal


def test_fab_variant_uses_primary_container():
    fab = _variant(_BUTTON, "fab", "button.tsx")
    assert "bg-primary-container" in fab
    assert "text-on-primary-container" in fab


def test_selected_tonal_toggles_show_a_check():
    # The secondary container is a quiet fill (1.16:1 against the light page)
    # and its text is lighter than an outline button's, so `tonal` alone no
    # longer reads as "on". M3's selected filter chip leads with a check.
    assert "aria-pressed={filter === f.id}" in _HEALTH
    assert "{filter === f.id && <Check />}" in _HEALTH
    assert "{review ? <Check /> : <GitCompare />}" in _STUDIO
    source = _read("components/source-toggle.tsx")
    assert "{value === s && <Check" in source
    proposals = _read("components/proposals/proposals-section.tsx")
    assert 'variant={active ? "tonal" : "outline"}' in proposals
    assert "{active && <Check" in proposals


def test_active_chat_session_is_current():
    chat = _read("components/chat/chat-page.tsx")
    assert 'aria-current={activeId === s.id ? "true" : undefined}' in chat


def test_segmented_controls_and_entity_cards_expose_pressed():
    formatting = _read("components/resume-editor/formatting-panel.tsx")
    assert "aria-pressed={current === o.value}" in formatting
    dialog = _read("components/career/new-entity-dialog.tsx")
    assert dialog.count('aria-pressed={sectionType === "') == 2


def test_primary_tint_pairs_do_not_spread():
    """bg-primary/10 text-primary is retired as a component fill. What remains
    is the historical comment in button.tsx plus decorative avatars and status
    chips the plan leaves alone. The count must not rise."""
    count = 0
    for path in (_FRONTEND / "components").rglob("*.tsx"):
        count += path.read_text(encoding="utf-8").count("bg-primary/10 text-primary")
    assert count <= 7, count


_RING_SURFACES = ("background", "card", "sidebar", "canvas", "muted", "secondary-container")


@pytest.mark.parametrize("mode", list(_MODES))
def test_focus_ring_meets_non_text_contrast(mode):
    t = _MODES[mode]
    for surface in _RING_SURFACES:
        ratio = _contrast(_rgb(t, "ring"), _rgb(t, surface))
        assert ratio >= 3.0, f"{mode}: --ring on --{surface} is {ratio:.2f}:1"


def test_browser_focus_outline_is_the_solid_ring():
    # outline-style:auto paints in outline-color: ring/50 was ~1.6:1.
    assert "outline-ring/50" not in _CSS


# Destructive text sits on its own tints. Worst alpha per surface: Button hover
# /20 light, /30 dark; the render-error banner and compile error are /10 on canvas.
_DESTRUCTIVE_WORST = {
    "light": {"card": 0.20, "background": 0.20, "canvas": 0.10, "muted": 0.10},
    "dark": {"card": 0.30, "background": 0.30, "canvas": 0.30, "muted": 0.20},
}


@pytest.mark.parametrize("mode", list(_MODES))
def test_destructive_text_on_its_tints_meets_aa(mode):
    t = _MODES[mode]
    destructive = _rgb(t, "destructive")
    for surface, worst in _DESTRUCTIVE_WORST[mode].items():
        bg = _rgb(t, surface)
        assert _contrast(destructive, bg) >= 4.5, f"{mode}: plain on --{surface}"
        for pct in (5, 10, 15, 20, 30):
            if pct / 100 > worst:
                continue
            ratio = _contrast(destructive, _over(destructive, bg, pct / 100))
            assert ratio >= 4.5, (
                f"{mode}: destructive on /{pct} over --{surface} is {ratio:.2f}:1"
            )


@pytest.mark.parametrize("mode", list(_MODES))
def test_muted_foreground_meets_aa_on_page_and_card(mode):
    """Placeholders use this token. Task 17's deviation cites the pin."""
    t = _MODES[mode]
    fg = _rgb(t, "muted-foreground")
    for surface in ("background", "card"):
        ratio = _contrast(fg, _rgb(t, surface))
        assert ratio >= 4.5, f"{mode}: --muted-foreground on --{surface} is {ratio:.2f}:1"


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
