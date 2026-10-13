"""The frontend's and the extension's preset tables equal the backend's, and the table in the plan.

app/services/resume_colors.py picks the hue; frontend/lib/resume-color.ts and
extension/shared/resume-color.js draw it.
"""

import re
from pathlib import Path

from app.services.resume_colors import PRESET_HUES
from tests.node_ts import run_node_test

_ROOT = Path(__file__).resolve().parents[2]
_TS = (_ROOT / "frontend/lib/resume-color.ts").read_text(encoding="utf-8")
_JS = (_ROOT / "extension/shared/resume-color.js").read_text(encoding="utf-8")

# The recipe's table: name, hue, chroma. A custom hue uses 0.10.
_RECIPE = [
    ("Rose", 5, 0.11), ("Copper", 40, 0.11), ("Ochre", 80, 0.11), ("Olive", 125, 0.11),
    ("Pine", 160, 0.09), ("Teal", 195, 0.09), ("Sky", 230, 0.09), ("Slate", 265, 0.06),
    ("Iris", 300, 0.11), ("Plum", 335, 0.11),
]


_PRESET = re.compile(r'name:\s*"(\w+)",\s*hue:\s*(\d+),\s*chroma:\s*([\d.]+)')


def _frontend_presets() -> list[tuple[str, int, float]]:
    table = _TS.split("export const RESUME_PRESETS", 1)[1].split("] as const", 1)[0]
    return [(name, int(hue), float(chroma)) for name, hue, chroma in _PRESET.findall(table)]


def _extension_presets() -> list[tuple[str, int, float]]:
    table = _JS.split("const PRESETS = [", 1)[1].split("];", 1)[0]
    return [(name, int(hue), float(chroma)) for name, hue, chroma in _PRESET.findall(table)]


def test_the_frontend_hues_equal_the_backend_hues_in_order():
    assert [h for _, h, _ in _frontend_presets()] == list(PRESET_HUES)


def test_the_frontend_names_and_chromas_are_the_recipe():
    assert _frontend_presets() == _RECIPE


def test_the_custom_chroma_is_the_recipe_value():
    assert re.search(r"CUSTOM_CHROMA\s*=\s*0\.1\b", _TS)


def test_resume_color_helpers_node_suite():
    result = run_node_test("lib/resume-color.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_extension_presets_equal_the_frontend_presets_in_order():
    assert _extension_presets() == _frontend_presets() == _RECIPE


def test_the_extension_custom_chroma_is_the_recipe_value():
    assert re.search(r"CUSTOM_CHROMA\s*=\s*0\.1\b", _JS)
