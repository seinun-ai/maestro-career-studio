"""The README's one paste: its shape here, and the real run in .github/workflows/readme-paste.yml."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location("check_readme_paste", ROOT / "scripts" / "check_readme_paste.py")
assert _spec and _spec.loader
paste = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(paste)


def _blocks() -> dict[str, list[str]]:
    return paste.paste_blocks((ROOT / "README.md").read_text(encoding="utf-8"))


def test_start_here_has_one_paste_for_each_shell():
    assert set(_blocks()) == {"bash", "powershell"}


def test_each_paste_finds_uv_in_the_same_terminal_before_using_it():
    # A terminal can't find uv until it's reopened, so the paste fails without the PATH line.
    bash, powershell = _blocks()["bash"], _blocks()["powershell"]
    assert bash[1] == 'export PATH="$HOME/.local/bin:$PATH"'
    assert powershell[1] == '$env:Path = "$env:USERPROFILE\\.local\\bin;$env:Path"'
    for lines in (bash, powershell):
        assert "install" in lines[0] and "astral.sh/uv" in lines[0]
        assert lines[2] == "uv tool install --python 3.12 maestro-career-studio"
        assert lines[3] == "maestro start"


def test_the_check_swaps_only_the_last_line():
    lines = _blocks()["bash"]
    assert paste.script_for(lines) == [*lines[:-1], "maestro --version"]


def test_the_check_runs_without_the_folder_a_new_terminal_lacks():
    sep = paste.os.pathsep
    assert paste.without_local_bin(sep.join(["/usr/bin", "/home/me/.local/bin", "/bin"])) == sep.join(["/usr/bin", "/bin"])


def test_the_check_starts_the_paste_the_way_a_new_terminal_does():
    # Windows keeps environment names upper-case, and PowerShell 7's PSModulePath stops the uv installer.
    for name in ("PSModulePath", "PSMODULEPATH"):
        env = paste.new_terminal_env({"PATH": "/usr/bin", name: "C:/pwsh/Modules", "HOME": "/home/me"})
        assert env == {"PATH": "/usr/bin", "HOME": "/home/me"}

