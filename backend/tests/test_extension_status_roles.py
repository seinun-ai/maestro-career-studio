"""The Companion names and colours an application status exactly as StatusChip does (Task 29)."""

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_CHIP = (_ROOT / "frontend/components/status-chip.tsx").read_text()
_ROLES = (_ROOT / "extension/shared/status-roles.js").read_text()

_ROLE_OF_CHIP = {
    "bg-muted": "muted", "bg-primary-container": "primary", "bg-warning-container": "warning",
    "bg-tertiary-container": "tertiary", "bg-success-container": "success", "bg-error-container": "error",
}


def _web_table() -> dict[str, tuple[str, str]]:
    block = _CHIP.split("const STATUS_STYLES", 1)[1].split("};", 1)[0]
    out = {}
    for key, label, chip in re.findall(r'(\w+): \{\s*label: "([^"]+)",\s*chip: "([^"]+)"', block):
        role = next(r for cls, r in _ROLE_OF_CHIP.items() if chip.startswith(cls))
        out[key] = (label, role)
    return out


def _panel_table() -> dict[str, tuple[str, str]]:
    return {k: (label, role) for k, label, role in
            re.findall(r'(\w+): \{ label: "([^"]+)", role: "(\w+)" \}', _ROLES)}


def test_panel_status_table_matches_status_chip():
    assert _web_table(), "status-chip.tsx changed shape: re-read STATUS_STYLES"
    assert _panel_table() == _web_table()


def test_panel_no_longer_colours_every_status_good():
    css = (_ROOT / "extension/panel/panel.css").read_text()
    assert ".chip.app {" not in css and ".draft-on" not in css


def test_every_role_the_table_names_has_a_chip_class_and_tokens():
    css = (_ROOT / "extension/panel/panel.css").read_text()
    for role in {role for _, role in _panel_table().values()}:
        assert f".chip.role-{role}" in css, role
        if role != "muted":
            assert f"--cs-{role}-container:" in css and f"--cs-on-{role}-container:" in css, role
