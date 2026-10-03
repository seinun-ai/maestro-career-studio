"""Pins the shared design tokens in frontend/app/globals.css.

The status roles (success, warning, attention, tertiary, the error container),
the surface-container ladder, and the type, corner, elevation and easing
scales. Contrast uses test_frontend_color_roles' arithmetic, so a role that
slips under WCAG 1.4.3's 4.5:1 on any surface it may sit on fails here. The
scale names are checked against lib/utils.ts: tailwind-merge files an
unregistered `text-*` as a colour, and cn() then drops it beside a real one.
"""

from __future__ import annotations

import re

import pytest

from tests.test_frontend_color_roles import (
    _CSS,
    _FRONTEND,
    _MODES,
    _contrast,
    _oklab,
    _read,
    _rgb,
)

_UTILS = _read("lib/utils.ts")

_CONTAINER_PAIRS = [
    ("success-container", "on-success-container"),
    ("warning-container", "on-warning-container"),
    ("attention-container", "on-attention-container"),
    ("tertiary-container", "on-tertiary-container"),
    ("error-container", "on-error-container"),
]
_LADDER = (
    "surface-container-lowest",
    "surface-container-low",
    "surface-container",
    "surface-container-high",
    "surface-container-highest",
)
# Every surface a line of text or a status dot may sit on.
_SURFACES = ("background", "card", "popover", "canvas", *_LADDER)
_TEXT_ROLES = (
    "foreground",
    "muted-foreground",
    "primary",
    "destructive",
    "success",
    "warning",
    "attention",
    "tertiary",
)


@pytest.mark.parametrize("mode", list(_MODES))
@pytest.mark.parametrize("container,on", _CONTAINER_PAIRS)
def test_status_container_text_meets_aa(mode, container, on):
    t = _MODES[mode]
    ratio = _contrast(_rgb(t, on), _rgb(t, container))
    assert ratio >= 4.5, f"{mode}: --{on} on --{container} is {ratio:.2f}:1"


# A text role that code puts on a container: the health summary's "Go to Needs a
# number" link button is `text-primary` inside the warning callout. Add a pair
# here when a call site does the same; muted-foreground is NOT one (it measures
# 3.7 to 3.9:1 on the success and warning containers in dark).
_ROLE_ON_CONTAINER = [("primary", "warning-container")]


@pytest.mark.parametrize("mode", list(_MODES))
@pytest.mark.parametrize("role,container", _ROLE_ON_CONTAINER)
def test_text_roles_used_on_a_container_meet_aa(mode, role, container):
    t = _MODES[mode]
    ratio = _contrast(_rgb(t, role), _rgb(t, container))
    assert ratio >= 4.5, f"{mode}: --{role} on --{container} is {ratio:.2f}:1"


@pytest.mark.parametrize("mode", list(_MODES))
@pytest.mark.parametrize("role", _TEXT_ROLES)
def test_text_roles_meet_aa_on_every_surface(mode, role):
    t = _MODES[mode]
    for surface in _SURFACES:
        ratio = _contrast(_rgb(t, role), _rgb(t, surface))
        assert ratio >= 4.5, f"{mode}: --{role} on --{surface} is {ratio:.2f}:1"


def _linear_srgb(lab):
    lightness, a, b = lab
    l_ = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (
        4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
        -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
        -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_,
    )


@pytest.mark.parametrize("mode", list(_MODES))
def test_status_tokens_are_inside_srgb(mode):
    """A browser clips an out-of-gamut oklch(), and paints a colour these

    tests never measured. `_srgb` clamps silently, so the gamut is checked on
    the unclamped linear values.
    """
    t = _MODES[mode]
    names = [n for pair in _CONTAINER_PAIRS for n in pair]
    names += ["success", "warning", "attention", "tertiary"]
    for name in names:
        channels = _linear_srgb(_oklab(t[name]))
        assert all(-1e-4 <= c <= 1 + 1e-4 for c in channels), (
            f"{mode}: --{name} oklch{t[name]} is outside sRGB: {channels}"
        )


def test_the_ladder_steps_one_way_and_brackets_the_page():
    """Light runs lowest (brightest) to highest; dark runs the other way.

    The page sits between lowest and low in both, as M3's surface does.
    """
    for mode, t in _MODES.items():
        steps = [t[name][0] for name in _LADDER]
        ordered = sorted(steps, reverse=(mode == "light"))
        assert steps == ordered, f"{mode}: the ladder is out of order: {steps}"
        assert len(set(steps)) == len(steps), f"{mode}: two steps share a tone"
        page = t["background"][0]
        low, high = sorted((steps[0], steps[1]))
        assert low < page < high, f"{mode}: the page is not between lowest and low"


def test_the_ladder_is_built_on_the_neutrals_already_here():
    light, dark = _MODES["light"], _MODES["dark"]
    assert light["surface-container-lowest"] == light["card"]
    assert light["surface-container"] == light["muted"]
    assert light["surface-container-highest"] == light["canvas"]
    assert dark["surface-container-lowest"] == dark["canvas"]
    assert dark["surface-container"] == dark["card"]
    assert dark["surface-container-highest"] == dark["muted"]


def test_theme_exposes_the_token_utilities():
    roles = [name for pair in _CONTAINER_PAIRS for name in pair]
    roles += ["success", "warning", "attention", "tertiary", *_LADDER]
    for role in roles:
        assert f"--color-{role}: var(--{role});" in _CSS, role


def _theme_names(namespace: str) -> list[str]:
    return re.findall(rf"^\s*--{namespace}-([a-z0-9-]+):", _CSS, re.M)


def _registered(key: str) -> list[str]:
    block = re.search(rf"\b{key}:\s*\[(.*?)\]", _UTILS, re.S)
    assert block, f"lib/utils.ts registers no `{key}` names with tailwind-merge"
    return re.findall(r'"([^"]+)"', block.group(1))


def test_every_type_style_carries_its_line_height_and_weight():
    names = [n for n in _theme_names("text") if "--" not in n]
    assert len(names) == 15, names
    for name in names:
        for part in ("line-height", "font-weight"):
            assert f"--text-{name}--{part}:" in _CSS, f"text-{name} has no {part}"


def test_scale_names_are_registered_with_tailwind_merge():
    """An unregistered name is merged as the wrong kind of class, or not at all."""
    text = [n for n in _theme_names("text") if "--" not in n]
    assert sorted(_registered("text")) == sorted(text)
    corners = [n for n in _theme_names("radius") if n.startswith("corner-")]
    assert sorted(_registered("radius")) == sorted(corners)
    assert sorted(_registered("shadow")) == sorted(_theme_names("shadow"))
    easings = [n for n in _theme_names("ease") if n in _registered("ease")]
    assert sorted(_registered("ease")) == sorted(easings)
    for name in ("standard", "emphasized-decelerate", "emphasized-accelerate"):
        assert name in _registered("ease")


def test_no_surface_is_a_muted_with_opacity():
    """`bg-muted/N` is a different grey on every page, card and theme: use the ladder."""
    hits = []
    for folder in ("app", "components"):
        for path in sorted((_FRONTEND / folder).rglob("*")):
            if path.suffix not in (".ts", ".tsx"):
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"bg-muted/\d+", line):
                    hits.append(f"{path.relative_to(_FRONTEND)}:{number}")
    assert not hits, "bg-muted/N is left at:\n" + "\n".join(hits)


# The utilities Tailwind's palette would write: a status is a role, never a shade.
_PALETTE_UTILITY = re.compile(
    r"(?<![\w-])(?:text|bg|border|ring|fill|stroke|from|to|via|outline|decoration|divide|shadow)-"
    r"(?:red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|"
    r"fuchsia|pink|rose|slate|gray|zinc|neutral|stone)-\d{2,3}(?![\w-])"
)
# CompanyMonogram's six hash tints go with step 8 of the design-system plan
# (docs/plans/2026-10-02-design-system-tokens.md). Delete this entry then.
_PALETTE_STILL_ALLOWED = {"components/company-monogram.tsx"}


def test_no_palette_class_is_written_outside_the_monogram():
    """A status is `success` / `warning` / `attention` / `tertiary` / `primary` /
    `destructive` or a container pair, never `text-amber-700 dark:text-amber-400`."""
    hits = []
    for folder in ("app", "components", "lib", "hooks"):
        for path in sorted((_FRONTEND / folder).rglob("*")):
            rel = path.relative_to(_FRONTEND).as_posix()
            if path.suffix not in (".ts", ".tsx") or rel in _PALETTE_STILL_ALLOWED:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if _PALETTE_UTILITY.search(line):
                    hits.append(f"{rel}:{number}")
    assert not hits, "a palette utility is left at:\n" + "\n".join(hits)


def test_stat_tile_is_a_filled_card():
    tile = _read("components/analytics/stat-tile.tsx")
    for cls in (
        "bg-surface-container-low",
        "rounded-corner-md",
        "text-title-large",
        "text-body-small",
        "font-medium",
    ):
        assert cls in tile, cls
    assert "bg-muted" not in tile
    container = re.search(r'<div className=\{cn\("([^"]+)"', tile)
    assert container, "StatTile's container is no longer a cn(...) literal"
    assert not re.search(r"\b(border|shadow)", container.group(1)), container.group(1)


def test_table_rows_lift_on_hover_in_dark_cards():
    """Dark: the card is surface-container, so a -low hover would darken the row."""
    table = _read("components/ui/table.tsx")
    assert "dark:hover:bg-surface-container-high" in table
    assert "dark:has-aria-expanded:bg-surface-container-high" in table


def test_header_rows_that_skip_the_hover_skip_it_in_dark_too():
    """A row's dark hover is its own variant, so `hover:bg-transparent` leaves it."""
    bare = []
    for folder in ("app", "components"):
        for path in sorted((_FRONTEND / folder).rglob("*.tsx")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "<TableRow" in line and "hover:bg-transparent" in line:
                    if "dark:hover:bg-transparent" not in line:
                        bare.append(f"{path.relative_to(_FRONTEND)}:{number}")
    assert not bare, "dark hover still lights the header at:\n" + "\n".join(bare)
