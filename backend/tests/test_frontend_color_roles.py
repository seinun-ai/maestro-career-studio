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


def test_employment_types_carry_their_state():
    prefs = _read("components/settings/job-preferences-section.tsx")
    assert 'variant={selected ? "tonal" : "outline"}' in prefs
    assert "aria-pressed={selected}" in prefs
    assert "{selected && <Check" in prefs
    assert 'role="group" aria-labelledby={employmentLabelId}' in prefs


def test_section_presets_carry_their_state():
    dialog = _read("components/career/new-entity-dialog.tsx")
    assert 'variant={on ? "tonal" : "outline"} aria-pressed={on}' in dialog
    assert "{on && <Check" in dialog


_CHIP_SRC = _read("components/gap-analysis/resolution-controls.tsx")
_GAP_CHIP = _CHIP_SRC[_CHIP_SRC.index("export function Chip(") : _CHIP_SRC.index("const LOAD_ERROR_MESSAGE")]
_SELECTED_OR_NOT = re.compile(r'selected\s*\?\s*"([^"]*)"\s*:\s*"([^"]*)"')
_TOKEN_UTIL = re.compile(
    r"(?<![\w:/-])(bg|text)-(primary-foreground|primary|muted-foreground|muted|background)(?:/(\d+))?(?![\w/-])"
)


def _ink(tokens, classes, under):
    """(text, fill) of a class string drawn over `under`: its own bg tint
    composited first, then its text alpha over that fill."""
    util = {kind: (name, int(pct) / 100 if pct else 1.0) for kind, name, pct in _TOKEN_UTIL.findall(classes)}
    fill = under
    if "bg" in util:
        fill = _over(_rgb(tokens, util["bg"][0]), under, util["bg"][1])
    text = _over(_rgb(tokens, util["text"][0]), fill, util["text"][1])
    return text, fill


def test_gap_target_chips_are_pressed_whatever_the_caller_passes():
    assert "aria-pressed={selected ?? false}" in _GAP_CHIP


@pytest.mark.parametrize("mode", list(_MODES))
def test_gap_target_chip_text_meets_aa(mode):
    """The chip's fill, its date and its "recent" tag, selected and not: the
    10px date and tag once used alpha (2.96, 3.99 and 4.24:1 light). Computed
    from the classes the chip ships, so any alpha that slips under 4.5 fails."""
    t = _MODES[mode]
    fills, *inner = _SELECTED_OR_NOT.findall(_GAP_CHIP)
    assert len(inner) == 2, "expected the date and the recent tag"
    for side in (0, 1):
        _, chip = _ink(t, fills[side], _rgb(t, "background"))
        for classes in (fills[side], *(pair[side] for pair in inner)):
            ratio = _contrast(*_ink(t, classes, chip))
            assert ratio >= 4.5, f"{mode}: gap chip {classes!r} is {ratio:.2f}:1"


_GALLERY = _read("components/templates/template-gallery.tsx")
_PICKER_BRANCH = _GALLERY[_GALLERY.index("if (onSelect) {") : _GALLERY.index("</button>")]


def test_template_picker_focus_is_outside_and_selection_inside():
    # Focus: the button's ring, 2px off the card. Selection: an edge INSIDE the
    # card plus a Check. --card equals --popover, so an outside selection ring
    # and the offset focus ring merged into one blue band.
    assert "focus-visible:ring-offset-2 focus-visible:ring-offset-popover" in _PICKER_BRANCH
    assert "selected && SELECTED_CARD_EDGE" in _PICKER_BRANCH
    edge = re.search(r'const SELECTED_CARD_EDGE =\s*"([^"]*)"', _GALLERY).group(1)
    for part in ("after:absolute", "after:inset-0", "after:border-2", "after:border-primary"):
        assert part in edge, part
    assert "ring-primary" not in _GALLERY
    assert "{selected && <Check" in _GALLERY
    select = _read("components/templates/template-select.tsx")
    assert "{value === DEFAULT_TEMPLATE && <Check" in select
    assert "overflow-y-auto p-1" in select  # the offset ring is not clipped


def test_template_picker_button_states_choice_and_warnings():
    assert "aria-pressed={selected}" in _PICKER_BRANCH
    body = re.search(r"<TemplateCardBody\b[^>]*/>", _PICKER_BRANCH).group(0)
    # The Check and the hidden engine/status both depend on these two props.
    assert re.search(r"\bpicking\b", body) and "selected={selected}" in body, body
    # aria-label replaces the content, so the warnings ride on the description.
    assert "aria-label={t.display_name ?? t.id}" in _PICKER_BRANCH
    assert "${describedBy}-badges" in _PICKER_BRANCH
    assert "id={describedBy && `${describedBy}-badges`}" in _GALLERY
    assert "id={describedBy && `${describedBy}-default`}" in _GALLERY
    assert '<span className="sr-only">Default template</span>' in _GALLERY


def test_the_picker_hides_the_engine_and_status_chips():
    strip = _GALLERY[_GALLERY.index("function TemplateBadgeStrip(") : _GALLERY.index("function TemplateCardBody(")]
    chips = [line for line in strip.splitlines() if "ENGINE_LABEL[" in line or "STATUS_LABEL[" in line]
    assert len(chips) == 2, chips
    for line in chips:
        assert "{!picking && <Badge" in line, line


def test_nothing_prints_a_raw_engine_or_status():
    page = _read("app/templates/[id]/page.tsx")
    assert "{ENGINE_LABEL[tq.data.engine]}" in page
    assert "{STATUS_LABEL[status]}" in page
    raw = re.compile(r"(?:\{|\$\{|String\()\s*(?:tq\.data\.|template\.|t\.)?(?:engine|status)\s*[)}]")
    for rel, src in (("gallery", _GALLERY), ("editor", page)):
        assert not raw.search(src), rel


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
    # Current in a list is semibold, as the sidebar's active row is.
    assert "hover:bg-secondary-container-hover font-semibold" in chat


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


# A translucent ring or outline IS the focus indicator on most controls, and
# ring/50 or outline-ring/60 measures ~1.8 to 2.6:1, under WCAG 1.4.11's 3:1.
# The one exemption is a halo beside a SOLID 1px `focus-visible:border-ring`
# (Button, Input, Select, Badge...): the border carries the 3:1 (pinned above
# per surface) and the halo only decorates it. A cva variant's halo counts the
# base string's border. A translucent focus BORDER is never exempt: it is the
# part that has to carry the contrast.
_FOCUS_TOKEN = re.compile(r"[^\s\"'`]*(?:ring|outline|border)-(?:ring|primary|destructive)/\d+")
_SOLID_FOCUS_BORDER = re.compile(r"(?<![\w:-])focus-visible:border-(?:ring|destructive)(?![/\w-])")

def _tsx_files():
    for root in ("app", "components"):
        yield from sorted((_FRONTEND / root).rglob("*.tsx"))


def _translucent_focus_tokens(line: str, border_is_solid: bool):
    for tok in _FOCUS_TOKEN.findall(line):
        variants, _, utility = tok.rpartition(":")
        if "focus" not in variants:
            continue
        if utility.startswith("border-") or not border_is_solid:
            yield tok


def _translucent_focus_sites():
    for path in _tsx_files():
        rel = str(path.relative_to(_FRONTEND))
        text = path.read_text(encoding="utf-8")
        base = re.search(r'cva\(\s*"([^"]*)"', text)
        base_solid = bool(base and _SOLID_FOCUS_BORDER.search(base.group(1)))
        for n, line in enumerate(text.splitlines(), 1):
            solid = base_solid or bool(_SOLID_FOCUS_BORDER.search(line))
            for tok in _translucent_focus_tokens(line, solid):
                yield rel, f"{rel}:{n}: {tok}"


def test_focus_indicators_are_solid():
    offenders = [site for _, site in _translucent_focus_sites()]
    assert offenders == [], offenders


_TABS = _read("components/ui/tabs.tsx")
_PANEL = _TABS[_TABS.index("function TabsContent") : _TABS.index("export {")]


def test_tab_panels_draw_their_focus_ring_above_their_content():
    # An element paints its own outline BEFORE its positioned and transformed
    # descendants, so cards covered an inset outline. The ring is an ::after
    # overlay, last and on top, kept inside the panel by `isolate`.
    assert "relative isolate" in _PANEL
    overlay = "focus-visible:after:absolute focus-visible:after:-inset-1 focus-visible:after:z-50"
    assert overlay in _PANEL
    assert "focus-visible:after:border-2 focus-visible:after:border-ring" in _PANEL
    assert "focus-visible:outline-hidden" in _PANEL
    # outline-none zeroes --tw-outline-style, which outline-2 reads: no ring at all.
    assert "outline-none" not in _PANEL
    assert "[&[inert]]:hidden" in _PANEL


def test_a_self_scrolling_tab_panel_keeps_a_solid_inset_outline():
    # An absolute overlay scrolls away with a scroller's content.
    for part in ("after:hidden", "outline-2", "outline-solid", "-outline-offset-2", "outline-ring"):
        assert f"[&.overflow-y-auto]:focus-visible:{part}" in _PANEL, part


_TABS_CONTENT_TAG = re.compile(r"<TabsContent\b[^>]*>")


def test_no_tab_panel_call_site_undoes_the_ring():
    offenders = []
    for path in _tsx_files():
        for tag in _TABS_CONTENT_TAG.findall(path.read_text(encoding="utf-8")):
            bad = re.search(r"outline-(?:none|hidden|0)\b|after:hidden|\bisolation-auto\b", tag)
            # The scroller fallback keys on exactly `overflow-y-auto`.
            other_scroll = re.search(r"\boverflow-(?!y-auto\b)[\w-]+", tag)
            if bad or other_scroll:
                offenders.append(f"{path.relative_to(_FRONTEND)}: {tag}")
    assert offenders == [], offenders


def test_ring_offsets_name_their_surface():
    """A ring offset paints `--tw-ring-offset-color`, white by default: a white
    band around the focus ring in dark mode. Every offset names its surface."""
    offenders = [
        f"{path.relative_to(_FRONTEND)}:{n}"
        for path in _tsx_files()
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r"ring-offset-\d", line)
        and not re.search(r"ring-offset-(?:background|card|popover|sidebar|canvas)\b", line)
    ]
    assert offenders == [], offenders


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


_FATAL_GATE = '"border-destructive/50 bg-destructive/5"'


def test_fatal_gate_containers_use_the_destructive_token():
    for rel in (
        "components/resume-health/finding-cards.tsx",
        "components/resume-editor/diff-review.tsx",
    ):
        source = _read(rel)
        assert _FATAL_GATE in source, rel
        assert "red-500" not in source, rel


@pytest.mark.parametrize("mode", list(_MODES))
def test_text_on_a_fatal_gate_meets_aa(mode):
    """The gate's container is destructive/5; on it sit the Blocker badge
    (text-destructive on bg-destructive/10), the fix hint (muted) and body."""
    t = _MODES[mode]
    destructive = _rgb(t, "destructive")
    for surface in ("card", "background"):
        gate = _over(destructive, _rgb(t, surface), 0.05)
        badge = _over(destructive, gate, 0.10)
        for name, fg, bg in (
            ("badge", destructive, badge),
            ("muted", _rgb(t, "muted-foreground"), gate),
            ("body", _rgb(t, "foreground"), gate),
        ):
            ratio = _contrast(fg, bg)
            assert ratio >= 4.5, f"{mode}: fatal gate {name} over --{surface} is {ratio:.2f}:1"


@pytest.mark.parametrize("mode", list(_MODES))
def test_muted_foreground_meets_aa_on_page_and_card(mode):
    """Placeholders use this token. Task 17's deviation cites the pin."""
    t = _MODES[mode]
    fg = _rgb(t, "muted-foreground")
    for surface in ("background", "card"):
        ratio = _contrast(fg, _rgb(t, surface))
        assert ratio >= 4.5, f"{mode}: --muted-foreground on --{surface} is {ratio:.2f}:1"


# A link's colour is a ROLE, never a raw palette shade: the referral careers
# URL was `text-blue-600` with no dark variant, 3.77:1 on the dark page.
_PALETTE = (
    "red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|"
    "violet|purple|fuchsia|pink|rose|slate|gray|zinc|neutral|stone"
)
_RAW_TEXT = re.compile(rf"(?<![\w-])(?:[\w-]+:)*text-(?:{_PALETTE})-\d+\b")
_UNDERLINED = re.compile(r'className="([^"]*(?<![\w-])underline(?![\w-])[^"]*)"')


def test_underlined_links_take_a_colour_role():
    offenders = [
        f"{path.relative_to(_FRONTEND)}: {cls}"
        for root in ("app", "components")
        for path in sorted((_FRONTEND / root).rglob("*.tsx"))
        for cls in _UNDERLINED.findall(path.read_text(encoding="utf-8"))
        if _RAW_TEXT.search(cls)
    ]
    assert offenders == [], offenders


def _referral_link_class() -> str:
    src = _read("app/referrals/page.tsx")
    link = src[src.index("href={referral.careers_url}") :]
    return re.search(r'className="([^"]*)"', link).group(1)


@pytest.mark.parametrize("mode", list(_MODES))
def test_the_referral_link_meets_aa_on_its_row(mode):
    # Text on the page, a card, and a hovered or selected table row.
    assert _referral_link_class() == "text-primary underline underline-offset-2"
    t = _MODES[mode]
    muted, page = _rgb(t, "muted"), _rgb(t, "background")
    fg = _rgb(t, "primary")
    for name, bg in (
        ("--background", page),
        ("--card", _rgb(t, "card")),
        ("muted/50 on the page", _over(muted, page, 0.5)),
        ("--muted", muted),
    ):
        ratio = _contrast(fg, bg)
        assert ratio >= 4.5, f"{mode}: the referral link over {name} is {ratio:.2f}:1"

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


# Tailwind v4's palette is OKLCH (frontend/node_modules/tailwindcss/theme.css).
# CI's backend job installs no node_modules, so the shades these pins use are
# copied here and checked against the installed theme wherever it exists.
_TAILWIND = {
    "orange-400": (0.75, 0.183, 55.934),
    "orange-500": (0.705, 0.213, 47.604),
    "orange-800": (0.47, 0.157, 37.304),
    "blue-300": (0.809, 0.105, 251.813),
    "blue-400": (0.707, 0.165, 254.624),
    "blue-500": (0.623, 0.214, 259.815),
    "blue-600": (0.546, 0.245, 262.881),
    "blue-700": (0.488, 0.243, 264.376),
    "amber-300": (0.879, 0.169, 91.605),
    "amber-400": (0.828, 0.189, 84.429),
    "amber-500": (0.769, 0.188, 70.08),
    "amber-700": (0.555, 0.163, 48.998),
    "amber-800": (0.473, 0.137, 46.201),
    "violet-300": (0.811, 0.111, 293.571),
    "violet-400": (0.702, 0.183, 293.541),
    "violet-600": (0.541, 0.281, 293.009),
    "violet-700": (0.491, 0.27, 292.581),
    "green-300": (0.871, 0.15, 154.449),
    "green-400": (0.792, 0.209, 151.711),
    "green-600": (0.627, 0.194, 149.214),
    "green-700": (0.527, 0.154, 150.069),
    "green-800": (0.448, 0.119, 151.328),
    "rose-300": (0.81, 0.117, 11.638),
    "rose-400": (0.712, 0.194, 13.428),
    "rose-600": (0.586, 0.253, 17.585),
    "rose-800": (0.455, 0.188, 13.697),
    "cyan-300": (0.865, 0.127, 207.078),
    "cyan-400": (0.789, 0.154, 211.53),
    "cyan-600": (0.609, 0.126, 221.723),
    "cyan-800": (0.45, 0.085, 224.283),
    "red-300": (0.808, 0.114, 19.571),
    "red-400": (0.704, 0.191, 22.216),
    "red-600": (0.577, 0.245, 27.325),
    "red-700": (0.505, 0.213, 27.518),
    "sky-400": (0.746, 0.16, 232.661),
    "sky-500": (0.685, 0.169, 237.323),
    "sky-700": (0.5, 0.134, 242.749),
    "sky-800": (0.443, 0.11, 240.79),
    "emerald-300": (0.845, 0.143, 164.978),
    "emerald-400": (0.765, 0.177, 163.223),
    "emerald-500": (0.696, 0.17, 162.48),
    "emerald-600": (0.596, 0.145, 163.225),
    "emerald-700": (0.508, 0.118, 165.612),
    "emerald-800": (0.432, 0.095, 166.913),
}
_TAILWIND_THEME = _FRONTEND / "node_modules" / "tailwindcss" / "theme.css"


@pytest.mark.skipif(not _TAILWIND_THEME.exists(), reason="frontend/node_modules not installed")
def test_copied_tailwind_shades_match_the_installed_theme():
    theme = _TAILWIND_THEME.read_text(encoding="utf-8")
    for name, lch in _TAILWIND.items():
        m = re.search(rf"--color-{name}:\s*oklch\(([\d.]+)%\s+([\d.]+)\s+([\d.]+)\)", theme)
        assert m, name
        read = (float(m.group(1)) / 100, float(m.group(2)), float(m.group(3)))
        assert read == pytest.approx(lch), name


# Every tinted chip in the status vocabulary (and the KB entity chips, which
# copy its shape): text on its own tint, over the page, a card and --muted
# (a selected tracker row), both modes. A chip's dark text and tint fall back
# to the light ones when it declares none, as the browser does.
_CHIP_SOURCES = (
    "components/status-chip.tsx",
    "components/career/entity-card.tsx",
    "components/company-monogram.tsx",
)
# `chip: "..."` / `className: "..."` entries, or a bare string in a list
# (the monogram's TONES).
_CHIP_CLASS = re.compile(r'(?:(?:chip|className):\s*|^\s*)"([^"]*\bbg-[^"]*)"', re.M)
_CHIP_UTIL = re.compile(
    r"(?<![\w:/-])(dark:)?(bg|text)-([a-z]+-\d+|muted(?:-foreground)?)(?:/(\d+))?(?![\w/-])"
)
_CHIPS = [(rel, cls) for rel in _CHIP_SOURCES for cls in _CHIP_CLASS.findall(_read(rel))]


def test_every_tinted_chip_is_found():
    found = {rel: sum(1 for r, _ in _CHIPS if r == rel) for rel in _CHIP_SOURCES}
    # 7 application statuses + Needs you + 7 proposal entries; 3 KB states + fallback.
    assert found == {
        "components/status-chip.tsx": 15,
        "components/career/entity-card.tsx": 4,
        "components/company-monogram.tsx": 6,
    }, found


def _chip_surfaces(t):
    """Where chips and monograms sit: the page, a card, a selected row
    (--muted), and a hovered row (Table's muted/50 on the page, the Proposals
    row's muted/40 on its card)."""
    muted = _rgb(t, "muted")
    return {
        "--background": _rgb(t, "background"),
        "--card": _rgb(t, "card"),
        "--muted": muted,
        "muted/50 on the page": _over(muted, _rgb(t, "background"), 0.5),
        "muted/40 on a card": _over(muted, _rgb(t, "card"), 0.4),
    }


def _chip_colour(mode, name):
    if name.startswith("muted"):
        return _rgb(_MODES[mode], name)
    assert name in _TAILWIND, f"copy --color-{name} from tailwindcss/theme.css into _TAILWIND"
    return _srgb(_oklab(_TAILWIND[name]))


@pytest.mark.parametrize("mode", list(_MODES))
@pytest.mark.parametrize(
    "rel,chip", _CHIPS, ids=[f"{r.rsplit('/', 1)[-1]}:{i}" for i, (r, _) in enumerate(_CHIPS)]
)
def test_chip_text_meets_aa_on_its_tint(rel, chip, mode):
    utils = {
        (bool(dark), kind): (colour, int(pct) / 100 if pct else 1.0)
        for dark, kind, colour, pct in _CHIP_UTIL.findall(chip)
    }
    dark = mode == "dark"
    text = utils.get((dark, "text")) or utils[(False, "text")]
    tint = utils.get((dark, "bg")) or utils[(False, "bg")]
    for surface, under in _chip_surfaces(_MODES[mode]).items():
        fill = _over(_chip_colour(mode, tint[0]), under, tint[1])
        ratio = _contrast(_chip_colour(mode, text[0]), fill)
        assert ratio >= 4.5, f"{mode}: {rel} {chip!r} over {surface} is {ratio:.2f}:1"


# Decision 16: the three amber template labels, as text on the surfaces they
# sit on (the gallery's cards, the picker's popover, the editor's page).
_AMBER_LABELS = {
    "Requires TeX": ("components/templates/requires-tex-badge.tsx", "requires TeX"),
    "ATS spacing": ("components/templates/template-gallery.tsx", "⚠ ATS spacing"),
    "unsaved": ("app/templates/[id]/page.tsx", ">unsaved<"),
}


def _class_before(rel: str, marker: str) -> str:
    source = _read(rel)
    return re.findall(r'className="([^"]*)"', source[: source.index(marker)])[-1]


@pytest.mark.parametrize("mode", list(_MODES))
@pytest.mark.parametrize("label", list(_AMBER_LABELS))
def test_template_warning_labels_meet_aa(label, mode):
    utils = {(bool(d), k): c for d, k, c, _ in _CHIP_UTIL.findall(_class_before(*_AMBER_LABELS[label]))}
    text = _chip_colour(mode, utils.get((mode == "dark", "text")) or utils[(False, "text")])
    for surface in ("background", "card", "popover"):
        ratio = _contrast(text, _rgb(_MODES[mode], surface))
        assert ratio >= 4.5, f"{mode}: {label} on --{surface} is {ratio:.2f}:1"


@pytest.mark.parametrize("mode", list(_MODES))
def test_tailoring_lift_sign_colours_meet_aa_on_the_card(mode):
    """The overall lift's +/- figure is text on the chart's card, in both modes."""
    lift = _read("components/charts/tailoring-lift-chart.tsx")
    assert '? "text-emerald-700 dark:text-emerald-400"\n                : "text-destructive"' in lift
    t = _MODES[mode]
    gain = _srgb(_oklab(_TAILWIND["emerald-700" if mode == "light" else "emerald-400"]))
    for name, fg in (("gain", gain), ("loss", _rgb(t, "destructive"))):
        ratio = _contrast(fg, _rgb(t, "card"))
        assert ratio >= 4.5, f"{mode}: lift {name} on --card is {ratio:.2f}:1"
