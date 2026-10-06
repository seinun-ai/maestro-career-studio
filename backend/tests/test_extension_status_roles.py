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
        role = next((r for cls, r in _ROLE_OF_CHIP.items() if chip.startswith(cls)), None)
        assert role, f"status {key}: chip class {chip!r} names no role in _ROLE_OF_CHIP"
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


_GLOBALS = (_ROOT / "frontend/app/globals.css").read_text()
_PANEL_CSS = (_ROOT / "extension/panel/panel.css").read_text()
# Panel token -> the web token it copies. The muted pair is the web's `--muted` and `--muted-foreground`.
_COPIED = {
    **{f"--cs-{r}": f"--{r}" for r in (
        "primary-container", "on-primary-container", "secondary-container", "on-secondary-container",
        "success-container", "on-success-container", "warning-container", "on-warning-container",
        "attention-container", "on-attention-container", "tertiary-container", "on-tertiary-container",
        "error-container", "on-error-container")},
    "--cs-muted-container": "--muted", "--cs-on-muted-container": "--muted-foreground",
}


def _props(css: str, selector: str) -> dict[str, str]:
    """The custom properties of the first block opened by `selector` (a line `selector {`), nested blocks cut."""
    body = css.split(selector + " {", 1)[1].split("\n}", 1)[0]
    return dict(re.findall(r"(--[\w-]+):\s*([^;]+);", body))


def test_the_panels_role_tokens_are_the_web_apps_in_both_themes():
    web = {"light": _props(_GLOBALS, ":root"), "dark": _props(_GLOBALS, ".dark")}
    panel_dark = _PANEL_CSS.split("@media (prefers-color-scheme: dark)", 1)[1]
    panel = {"light": _props(_PANEL_CSS, ":root"),
             "dark": dict(re.findall(r"(--cs-[\w-]+):\s*([^;]+);", panel_dark))}
    for theme in ("light", "dark"):
        for mine, theirs in _COPIED.items():
            assert mine in panel[theme], (theme, mine)
            assert panel[theme][mine] == web[theme][theirs], (theme, mine, panel[theme][mine], web[theme][theirs])
