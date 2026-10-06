"""The Companion draws Lucide icons, never emoji or text glyphs (visual-language plan, Task 28)."""

import re
from pathlib import Path

import pytest

from tests.extension_harness import run_node
from tests.extension_panel_harness import (
    PANEL_SCRIPT_SRCS,
    SVG_NS,
    _PANEL_FAKES_JS,
    _panel_script,
    _text,
    PANEL_SOURCE,
    SETTINGS_REPLY,
)

_PANEL = Path(__file__).resolve().parents[2] / "extension/panel"
_GLYPHS = "⚠▲▼✓✅🟡⏸📎▾▸↗→"


def _strip_comments(text: str) -> str:
    """Block and line comments out, like Task 1's `_strip_comments`.

    The panel's files explain themselves in long prose that names the old
    glyphs on purpose, and a pin a comment can break pins nothing about code.
    A `//` inside a string (the svg namespace URL) is left alone: a line comment
    only starts where nothing but whitespace or code precedes it, and the
    `://` of a URL is skipped.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?<!:)//.*", "", text)


def test_no_emoji_or_text_glyph_in_panel_code():
    hits = []
    for path in [*_PANEL.rglob("*.js"), _PANEL / "panel.html"]:
        text = path.read_text()
        if path.suffix == ".html":
            text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        for lineno, line in enumerate(_strip_comments(text).splitlines(), 1):
            hits += [f"{path.name}:{lineno} {ch!r}" for ch in _GLYPHS if ch in line]
    assert hits == [], "\n".join(hits)


def test_icons_module_is_on_the_roster():
    srcs = re.findall(r'<script src="([^"]+)"></script>',
                      (_PANEL / "panel.html").read_text())
    assert "icons.js" in srcs
    # Before every stage and action script, after the shared decisions module.
    assert srcs.index("icons.js") < srcs.index("stages/job.js")
    assert srcs.index("../shared/decisions.js") < srcs.index("icons.js")
    assert "window.careerStudioCompanion" in (_PANEL / "icons.js").read_text()


def test_icons_module_holds_the_twelve_glyphs_and_a_licence_line():
    source = (_PANEL / "icons.js").read_text()
    assert "ISC" in source.split("*/", 1)[0]
    for name in ("check", "circle-check", "circle-minus", "circle-alert", "triangle-alert",
                 "chevron-down", "chevron-right", "external-link", "arrow-right",
                 "paperclip", "lock", "minus"):
        assert f'"{name}"' in source, name


_ICON_DRIVER_JS = _PANEL_FAKES_JS + r"""
const ns = loadModules();
main(async () => {
  await settle();
  const strip = (node) => ({ tag: node.tagName, ns: node.namespace, attrs: node.attrs,
                              kids: node.children.map(strip) });
  let unknown = null;
  try { ns.icon("sparkles"); } catch (err) { unknown = String(err.message); }
  emit({ plain: strip(ns.icon("circle-check")), named: strip(ns.icon("lock", { size: 20, label: "Locked" })),
         unknown });
});
"""


def test_icon_builds_an_svg_that_is_hidden_unless_it_has_a_name(tmp_path):
    out = run_node(_ICON_DRIVER_JS, {"tabs": [], "replies": {"read_settings": SETTINGS_REPLY}},
                   tmp_path, source=PANEL_SOURCE)
    plain, named = out["plain"], out["named"]
    assert (plain["tag"], plain["ns"]) == ("SVG", SVG_NS)
    assert plain["attrs"]["data-icon"] == "circle-check"
    assert plain["attrs"]["aria-hidden"] == "true"
    assert "aria-label" not in plain["attrs"]
    assert [kid["tag"] for kid in plain["kids"]] == ["CIRCLE", "PATH"]
    assert all(kid["ns"] == SVG_NS for kid in plain["kids"])
    # A label makes it an image with that name, and the size is the caller's.
    assert (named["attrs"]["role"], named["attrs"]["aria-label"]) == ("img", "Locked")
    assert "aria-hidden" not in named["attrs"]
    assert (named["attrs"]["width"], named["attrs"]["height"]) == ("20", "20")
    # An unknown name fails the render that asked, not a blank box.
    assert "no icon named sparkles" in out["unknown"]


def test_the_boot_names_icons_js_when_its_tag_is_missing(tmp_path):
    source = "\n".join(_panel_script(src) for src in PANEL_SCRIPT_SRCS if src != "icons.js")
    with pytest.raises(AssertionError, match="icons.js"):
        run_node(_ICON_DRIVER_JS, {"tabs": [], "replies": {"read_settings": SETTINGS_REPLY}},
                 tmp_path, source=source)


def test_an_icon_adds_no_words_to_a_row():
    """`_text` reads an svg as "", like a browser's `textContent`."""
    svg = {"tag": "SVG", "namespace": SVG_NS, "text": "", "attrs": {},
           "children": [{"tag": "PATH", "namespace": SVG_NS, "text": "d", "attrs": {},
                         "children": []}]}
    row = {"tag": "SPAN", "namespace": None, "text": "Done", "attrs": {}, "children": [svg]}
    assert _text(row) == "Done"
