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


def _class_strings(rel: str):
    """Every quoted or template string in a source file, with its line number.

    A class list is a string literal, so "the same class string" is the same
    literal. A literal that is not a class list simply never matches.
    """
    text = (_FRONTEND / rel).read_text(encoding="utf-8")
    for match in _STRING_LITERAL.finditer(text):
        yield text.count("\n", 0, match.start()) + 1, match.group(0)


def _cn_calls(rel: str):
    """Each `cn(...)` call's string literals joined, with the call's line number.

    `cn("text-body-medium", active && "font-semibold")` is one class list written
    in two literals, so a weight in the second is still beside the scale utility.
    """
    text = (_FRONTEND / rel).read_text(encoding="utf-8")
    for call in re.finditer(r"(?<![\w.])cn\(", text):
        depth, position = 1, call.end()
        parts = []
        while depth and position < len(text):
            literal = _STRING_LITERAL.match(text, position)
            if literal:
                parts.append(literal.group(0))
                position = literal.end()
                continue
            depth += {"(": 1, ")": -1}.get(text[position], 0)
            position += 1
        yield text.count("\n", 0, call.start()) + 1, "\n".join(parts)


def _frontend_sources():
    for folder in ("app", "components", "lib", "hooks"):
        for path in sorted((_FRONTEND / folder).rglob("*")):
            if path.suffix in (".ts", ".tsx"):
                yield path.relative_to(_FRONTEND).as_posix()


def _lines_matching(pattern):
    """`path:line` for every line of the frontend source that matches (comments too)."""
    hits = []
    for rel in _frontend_sources():
        text = (_FRONTEND / rel).read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{rel}:{number}")
    return hits


_STRING_LITERAL = re.compile(r"\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`")
# Tailwind's stock sizes and an arbitrary pixel or rem size: the scale has a name for each.
_RAW_SIZE = re.compile(
    r"(?<![\w-])text-(?:xs|sm|base|lg|xl|2xl|3xl|4xl|5xl|6xl|7xl|8xl|9xl)(?![\w-])"
    r"|(?<![\w-])text-\[[0-9.]+(?:px|rem)\]"
)
_SCALE_SIZE = re.compile(r"(?<![\w-])text-(?:display|headline|title|body|label)-(?:large|medium|small)(?![\w-])")
_HAND_WEIGHT = re.compile(r"(?<![\w-])font-(?:medium|semibold|bold)(?![\w-])")
_UPPERCASE = re.compile(r"(?<![\w-])uppercase(?![\w-])")


def test_no_raw_text_size_is_written():
    """Size, line height and weight travel together: `text-sm` is `text-body-medium`
    (or `title-small` / `label-large` when it carried a weight), `text-[11px]` is
    `text-label-small`. docs/design-system/migration.md has the whole table."""
    hits = _lines_matching(_RAW_SIZE)
    assert not hits, "a raw text size is left at:\n" + "\n".join(hits)


def test_no_class_is_uppercase():
    """Group headings and meta labels are sentence case; the caps were the style, not the text."""
    hits = _lines_matching(_UPPERCASE)
    assert not hits, "uppercase is left at:\n" + "\n".join(hits)


# A scale utility carries its own weight, so a hand-paired font-medium/semibold/bold
# in the same class string (or the same cn(...) call) overrides the scale. The
# sanctioned overrides are listed by file and by the class text they may carry, so
# a second weight written elsewhere in the same file still fails:
#   - the page title is `text-title-large font-medium`: PageHeader, the same title
#     in the studios (tailored resume, tailor session, job page, entity heading,
#     the editable title) and the h1 of a full-page state (error, not found, a
#     missing gap analysis), which is that page's title;
#   - StatTile's value is the same title-large at 500;
#   - the current sidebar row is weight 600 under `data-active` (`aria-current`),
#     and so is the open chat row (the weight sits on its button, which has its
#     own scale class);
#   - the health grade letter is headline-small at 600.
_PAGE_TITLE = r"text-title-large font-medium"
_WEIGHT_OVERRIDE_ALLOWED = [
    ("app/error.tsx", _PAGE_TITLE),
    ("app/not-found.tsx", _PAGE_TITLE),
    ("app/jobs/[id]/page.tsx", _PAGE_TITLE),
    ("app/jobs/[id]/tailor/[sessionId]/page.tsx", _PAGE_TITLE),
    ("components/page-shell.tsx", _PAGE_TITLE),
    ("components/career/entity-detail.tsx", _PAGE_TITLE),
    ("components/resume-editor/editable-title.tsx", _PAGE_TITLE),
    ("components/resume-editor/tailored-resume-studio.tsx", _PAGE_TITLE),
    ("components/analytics/stat-tile.tsx", r"text-title-large text-foreground mt-0\.5 font-medium"),
    ("components/ui/sidebar.tsx", r"data-active:font-semibold"),
    ("components/chat/chat-page.tsx", r'text-body-medium"\n"font-semibold"'),
    ("components/resume-health/summary-band.tsx", r"text-headline-small font-semibold"),
]


def _weight_pairs():
    """`path:line` and text of every class string or cn() call with a scale size and a weight."""
    for rel in _frontend_sources():
        for number, text in (*_class_strings(rel), *_cn_calls(rel)):
            if _SCALE_SIZE.search(text) and _HAND_WEIGHT.search(text):
                yield rel, number, text


def test_no_weight_is_paired_with_a_scale_utility_by_hand():
    """Blind spot: a parent's `font-semibold` that a child's own scale class
    overrides (`<div class="font-semibold"><span class="text-body-medium">`) is
    not seen here, because the two never share a class string. Put the weight on
    the element that carries the scale class."""
    hits = []
    for rel, number, text in _weight_pairs():
        if not any(rel == file and re.search(pattern, text) for file, pattern in _WEIGHT_OVERRIDE_ALLOWED):
            hits.append(f"{rel}:{number}")
    assert not hits, "a weight is paired with a scale utility at:\n" + "\n".join(sorted(set(hits)))


def test_every_weight_override_entry_still_matches():
    """A stale entry would let the next hand-paired weight in that file through."""
    pairs = list(_weight_pairs())
    stale = [
        f"{file}: {pattern}"
        for file, pattern in _WEIGHT_OVERRIDE_ALLOWED
        if not any(rel == file and re.search(pattern, text) for rel, _, text in pairs)
    ]
    assert not stale, "allow-list entries that match nothing:\n" + "\n".join(stale)


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


# One corner per kind of thing: `rounded-corner-xs|sm|md|lg|xl`, `rounded-full` or
# `rounded-none`, in any side form (`rounded-t-corner-md`, `rounded-r-corner-sm`).
# Tailwind's own ladder (`rounded`, `rounded-md`, `rounded-xl`) is built on the
# shadcn `--radius` and names no kind, and a bracketed value is a corner by hand.
# Only string literals are scanned (a className, a cn() or cva() argument, a
# template literal), so the word "rounded" in prose does not trip it.
_RADIUS_BY_HAND = re.compile(
    r"(?<![\w-])rounded(?:-(?:t|b|l|r|tl|tr|bl|br|s|e|ss|se|es|ee))?"
    r"(?:-(?:xs|sm|md|lg|xl|2xl|3xl|4xl|\[[^\]]+\]))?(?![\w-])"
)
_CORNER_NAME = re.compile(r"(?<![\w-])rounded(?:-[a-z]{1,2})?-corner-([a-z0-9]+)(?![\w-])")
# The only exception, by file and literal: the tooltip's arrow is a 10px square
# turned 45 degrees, and a 4px corner would blunt its point into a bump.
_RADIUS_BY_HAND_ALLOWED: list[tuple[str, str]] = [
    ("components/ui/tooltip.tsx", "rounded-[2px]"),
]


def _literal_matches(pattern):
    """`(path, line, match)` for every match of `pattern` inside a string literal."""
    for rel in _frontend_sources():
        text = (_FRONTEND / rel).read_text(encoding="utf-8")
        for literal in _STRING_LITERAL.finditer(text):
            for match in pattern.finditer(literal.group(0)):
                yield rel, text.count("\n", 0, literal.start() + match.start()) + 1, match


def _radius_hits():
    for rel, number, match in _literal_matches(_RADIUS_BY_HAND):
        yield rel, number, match.group(0)


def test_no_corner_is_written_by_hand():
    """A card's corner is `rounded-corner-md`, a control's `-sm`, a menu's `-xs`, a
    dialog's `-xl`, a pill's `rounded-full`. docs/design-system/migration.md maps
    each old `rounded-*`. Arbitrary radii and `var(--radius…)` are not written."""
    hits = [
        f"{rel}:{number}: {literal}"
        for rel, number, literal in _radius_hits()
        if (rel, literal) not in _RADIUS_BY_HAND_ALLOWED
    ]
    assert not hits, "a hand-written corner is left at:\n" + "\n".join(hits)


def test_every_corner_name_is_on_the_scale():
    """`rounded-corner-2xl` or a typo would compile to nothing and leave a square corner."""
    hits = [
        f"{rel}:{number}: {match.group(0)}"
        for rel, number, match in _literal_matches(_CORNER_NAME)
        if match.group(1) not in ("xs", "sm", "md", "lg", "xl")
    ]
    assert not hits, "a corner name is not on the scale at:\n" + "\n".join(hits)


def test_no_class_reads_the_radius_variable():
    """`--radius-md` and its siblings are the shadcn ladder; a class that reads one is a corner by hand."""
    hits = _lines_matching(re.compile(r"var\(--radius(?!-corner)"))
    assert not hits, "a class reads the --radius ladder at:\n" + "\n".join(hits)


def test_every_corner_exception_still_matches():
    found = {(rel, literal) for rel, _, literal in _radius_hits()}
    stale = [entry for entry in _RADIUS_BY_HAND_ALLOWED if entry not in found]
    assert not stale, f"allow-list entries that match nothing: {stale}"


def _jsx_tags(rel: str, names: tuple[str, ...]):
    """`(line, name, tag source)` of each `<Name ...>` opening tag, comments skipped.

    Walks to the tag's closing `>` past quotes, `{...}` expressions and comments,
    so a `cn(...)` argument and a `render={<Button className=... />}` are inside it.
    """
    text = (_FRONTEND / rel).read_text(encoding="utf-8")
    for opening in re.finditer(r"<(%s)(?=[\s/>])" % "|".join(names), text):
        i, depth, quote = opening.end(), 0, None
        while i < len(text):
            c = text[i]
            if quote:
                if c == "\\":
                    i += 1
                elif c == quote:
                    quote = None
            elif text.startswith("//", i):
                i = text.index("\n", i)
            elif text.startswith("/*", i):
                i = text.index("*/", i) + 1
            elif c in "\"'`":
                quote = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            elif c == ">" and depth == 0 and text[i - 1] != "=":
                break
            i += 1
        yield text.count("\n", 0, opening.start()) + 1, opening.group(1), text[opening.start() : i + 1]


# A control keeps its kind's corner: buttons, select triggers and tabs are 8px
# (docs/design-system/components/Button, TextField, Tabs). The READMEs sanction no round
# icon button and no pill tab strip; a segmented toggle is its own component
# (source-toggle.tsx) and writes its pill by hand. Allow-list a sanctioned case
# by (file, tag name) with a reason.
_CONTROLS = ("Button", "SelectTrigger", "TabsList", "TabsTrigger")
_PILL_CONTROL_ALLOWED: list[tuple[str, str]] = []


def test_a_control_call_site_does_not_pass_a_pill():
    hits = []
    for rel in _frontend_sources():
        if rel.startswith("components/ui/") or not rel.endswith(".tsx"):
            continue
        for number, name, tag in _jsx_tags(rel, _CONTROLS):
            if re.search(r"(?<![\w-])rounded-full(?![\w-])", tag) and (rel, name) not in _PILL_CONTROL_ALLOWED:
                hits.append(f"{rel}:{number}: <{name}>")
    assert not hits, "a control is overridden to a pill at:\n" + "\n".join(hits)


def _slot_classes(rel: str, slot: str) -> str:
    """The class literals of the element that carries `data-slot="<slot>"`, up to the next component."""
    text = _read(rel)
    start = text.index(f'data-slot="{slot}"')
    end = text.find("\nfunction ", start)
    end = len(text) if end < 0 else end
    return "\n".join(literal[1:-1] for literal in _STRING_LITERAL.findall(text[start:end]))


def test_the_primitives_carry_their_kind_of_corner():
    button = re.search(r"const buttonVariants = cva\(\s*\"([^\"]+)\"", _read("components/ui/button.tsx"))
    assert button and "rounded-corner-sm" in button.group(1).split()
    assert "rounded-corner-md" in _slot_classes("components/ui/card.tsx", "card").split()
    assert "rounded-corner-xl" in _slot_classes("components/ui/dialog.tsx", "dialog-content").split()
    assert "rounded-corner-sm" in _read("components/ui/input.tsx").split()
    assert "rounded-corner-xs" in _slot_classes("components/ui/checkbox.tsx", "checkbox").split()


def test_a_menu_is_the_small_corner_and_a_popover_panel_the_medium_one():
    """POPUP_SURFACE owns no corner: a menu is a list of rows, a popover a panel."""
    popover = _read("components/ui/popover.tsx")
    surface = re.search(r"export const POPUP_SURFACE =\s*\"([^\"]+)\"", popover)
    assert surface and "rounded" not in surface.group(1)
    assert "rounded-corner-md" in _slot_classes("components/ui/popover.tsx", "popover-content").split()
    for slot in ("dropdown-menu-content", "dropdown-menu-sub-content", "dropdown-menu-item"):
        assert "rounded-corner-xs" in _slot_classes("components/ui/dropdown-menu.tsx", slot).split(), slot
    assert "rounded-corner-xs" in _slot_classes("components/ui/select.tsx", "select-content").split()


def test_sidebar_menu_rows_are_pills():
    """The hover and the current row share one shape (owner decision, UX change 1)."""
    sidebar = _read("components/ui/sidebar.tsx")
    variants = re.search(r"const sidebarMenuButtonVariants = cva\(\s*\"([^\"]+)\"", sidebar)
    assert variants, "sidebarMenuButtonVariants is no longer a cva( literal"
    assert "rounded-full" in variants.group(1).split()
    action = sidebar[sidebar.index("function SidebarMenuAction(") :].split("\nfunction ")[0]
    assert "rounded-full" in action.split(), "SidebarMenuAction nests in a pill row"


def test_a_sheet_rounds_the_edge_it_opens_on():
    """16px on the two corners that face the page, whichever side the sheet is on."""
    classes = _slot_classes("components/ui/sheet.tsx", "sheet-content").split()
    for side, edge in (("right", "l"), ("left", "r"), ("bottom", "t"), ("top", "b")):
        assert f"data-[side={side}]:rounded-{edge}-corner-lg" in classes, side


def test_a_tab_nests_in_the_list_that_holds_it():
    """The list is 8px with 3px of padding; its trigger is the 4px corner inside it."""
    tabs = _read("components/ui/tabs.tsx")
    assert re.search(r"justify-center-safe rounded-corner-sm p-\[3px\]", tabs)
    assert re.search(r"gap-1\.5 rounded-corner-xs border border-transparent", tabs)


def test_the_focus_ring_only_removes_what_it_added():
    """RING carries `rounded-corner-md`, which a Card already has; stripping it after the
    flash would square the card."""
    source = _read("lib/use-focus-section.ts")
    assert 'const RING = ["ring-2", "ring-primary/60", "rounded-corner-md"];' in source
    assert "const added = RING.filter((cls) => !el.classList.contains(cls));" in source
    assert "el.classList.add(...added);" in source
    assert "el.classList.remove(...added)" in source
    assert "classList.remove(...RING)" not in source


# Only what floats casts a shadow: `shadow-level1` a hovered FAB or interactive chip,
# `shadow-level2` a menu, popover, tooltip, toast, dragged row or sticky bar over
# content, `shadow-level3` a dialog or sheet. Cards, tiles, inputs, buttons, tabs and
# tables rest flat. Any variant prefix is fine (`hover:`, `data-dragging:`), and a
# trailing `!` (an important utility that must beat a third party's own rule).
_SHADOW_UTILITY = re.compile(r"(?<![\w-])shadow(?:-[^\s\"'`!]+)?!?(?=[\s\"'`]|$)")
_SHADOW_LEVEL = re.compile(r"shadow-level[123]!?")
# A 1px hairline that has to live in a box-shadow. The sticky table header's rule
# stays one: a border on a sticky <th> under border-collapse stays with the grid
# and scrolls away from the header it should underline.
_SHADOW_BY_HAND_ALLOWED: list[tuple[str, str]] = [
    ("components/ui/table.tsx", "shadow-[inset_0_-1px_0_var(--color-border)]"),
]


def _shadow_hits():
    for rel, number, match in _literal_matches(_SHADOW_UTILITY):
        yield rel, number, match.group(0)


def test_no_shadow_is_written_but_the_three_levels():
    """`shadow-sm`, `shadow-md`, `shadow-lg`, `shadow-none` and a bracketed
    `shadow-[...]` are the stock ladder or a shadow by hand. docs/design-system/migration.md
    maps each; a flat element writes none."""
    hits = [
        f"{rel}:{number}: {literal}"
        for rel, number, literal in _shadow_hits()
        if not _SHADOW_LEVEL.fullmatch(literal) and (rel, literal) not in _SHADOW_BY_HAND_ALLOWED
    ]
    assert not hits, "a shadow utility off the level scale is left at:\n" + "\n".join(hits)


def test_every_shadow_exception_still_matches():
    found = {(rel, literal) for rel, _, literal in _shadow_hits()}
    stale = [entry for entry in _SHADOW_BY_HAND_ALLOWED if entry not in found]
    assert not stale, f"allow-list entries that match nothing: {stale}"


def test_an_inline_box_shadow_reads_a_level():
    """A chart tooltip is styled inline, so its shadow is `var(--shadow-level2)`."""
    bad = [
        hit
        for hit in _lines_matching(re.compile(r"boxShadow\s*:|box-shadow\s*:"))
        if not re.search(r"var\(--shadow-level[123]\)", _line_at(hit))
    ]
    assert not bad, "an inline box-shadow is not a level at:\n" + "\n".join(bad)
    assert 'boxShadow: "var(--shadow-level2)"' in _read("components/charts/chart-kit.tsx")


def _line_at(hit: str) -> str:
    rel, number = hit.rsplit(":", 1)
    return _read(rel).splitlines()[int(number) - 1]


# `transition-[color,box-shadow]` names a property; only a `shadow` utility casts one.
_CASTS_SHADOW = re.compile(r"(?<![\w-])shadow(?![\w])")


def _class_list(rel: str, slot: str) -> list[str]:
    return _slot_classes(rel, slot).split()


def test_a_card_and_a_flat_control_cast_no_shadow():
    for rel, slot in (
        ("components/ui/card.tsx", "card"),
        ("components/ui/input.tsx", "input"),
        ("components/ui/textarea.tsx", "textarea"),
        ("components/ui/checkbox.tsx", "checkbox"),
        ("components/ui/switch.tsx", "switch"),
        ("components/ui/slider.tsx", "slider-thumb"),
    ):
        text = _read(rel)
        assert 'data-slot="%s"' % slot in text, f"{rel} lost its {slot} slot"
        assert not _CASTS_SHADOW.search(_slot_classes(rel, slot)), f"{rel}: {slot} casts a shadow"
    button = re.search(r"const buttonVariants = cva\(\s*\"([^\"]+)\"", _read("components/ui/button.tsx"))
    assert button and not _CASTS_SHADOW.search(button.group(1)), "a button rests flat"
    assert not _CASTS_SHADOW.search(_read("components/ui/tabs.tsx")), "a tab rests flat"


def test_what_floats_carries_its_level():
    popover = _read("components/ui/popover.tsx")
    surface = re.search(r"export const POPUP_SURFACE =\s*\"([^\"]+)\"", popover)
    assert surface and "shadow-level2" in surface.group(1).split()  # popover and menu
    assert "shadow-level2" in _class_list("components/ui/dropdown-menu.tsx", "dropdown-menu-sub-content")
    assert "shadow-level2" in _class_list("components/ui/select.tsx", "select-content")
    assert "shadow-level2" in _class_list("components/ui/tooltip.tsx", "tooltip-content")
    assert 'toast: "cn-toast shadow-level2!"' in _read("components/ui/sonner.tsx")
    assert "shadow-level3" in _class_list("components/ui/dialog.tsx", "dialog-content")
    assert "shadow-level3" in _class_list("components/ui/sheet.tsx", "sheet-content")
    fab = re.search(r"fab:\s*\"([^\"]+)\"", _read("components/ui/button.tsx"))
    assert fab and "hover:shadow-level1" in fab.group(1).split()
    assert "hover:shadow-level1" in _read("components/status-chip.tsx")
