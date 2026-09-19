"""The probe is the ONE place that looks for a PDF engine binary."""
import importlib.metadata
import subprocess
from pathlib import Path

import pytest

from app.config import settings
from app.services import engines


@pytest.fixture(autouse=True)
def _fresh_probe(monkeypatch):
    engines.reset_cache()
    monkeypatch.setattr(settings, "maestro_cs_pdflatex", None)
    yield
    engines.reset_cache()


def _fake_pdflatex(directory: Path) -> Path:
    exe = directory / "pdflatex"
    exe.write_text("#!/bin/sh\necho 'pdfTeX 3.141592653-2.6-1.40.26 (TeX Live 2025)'\n")
    exe.chmod(0o755)
    return exe


def _stub_pdflatex(directory: Path, body: str) -> Path:
    exe = directory / "pdflatex"
    exe.write_text(f"#!/bin/sh\n{body}\n")
    exe.chmod(0o755)
    return exe


def test_missing_pdflatex_is_unavailable_with_a_reason(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(engines, "_candidate_dirs", lambda: [])
    status = engines.probe_pdflatex()
    assert status.available is False
    assert status.path is None
    assert "not found" in status.reason


def test_found_pdflatex_reports_path_and_version(monkeypatch, tmp_path):
    exe = _fake_pdflatex(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))
    status = engines.probe_pdflatex()
    assert status.available is True
    assert status.path == str(exe)
    assert status.version.startswith("pdfTeX")


def test_known_tex_homes_are_searched_when_path_lacks_tex(monkeypatch, tmp_path):
    exe = _fake_pdflatex(tmp_path)
    monkeypatch.setenv("PATH", "/nonexistent")
    monkeypatch.setattr(engines, "_candidate_dirs", lambda: [str(tmp_path)])
    assert engines.probe_pdflatex().path == str(exe)


def test_no_path_at_all_does_not_search_the_working_directory(monkeypatch, tmp_path):
    """An EMPTY component in a search path means "the current directory" to
    shutil.which, and a GUI-launched process — the case this module exists for —
    can have no PATH at all. The probe owes its caller an ABSOLUTE path, so the
    working directory is never a candidate."""
    _fake_pdflatex(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PATH", raising=False)
    texbin = tmp_path / "texbin"
    texbin.mkdir()
    monkeypatch.setattr(engines, "_candidate_dirs", lambda: [str(texbin)])
    status = engines.probe_pdflatex()
    assert status.available is False
    assert status.path is None


@pytest.mark.parametrize("path_value", ["", ":", "/usr/bin:", ":/usr/bin", "/a::/b"])
def test_an_empty_path_component_never_makes_cwd_a_candidate(
    monkeypatch, tmp_path, path_value
):
    """The same trap hidden mid-string, where filtering a wholly empty PATH
    misses it: PATH must be SPLIT before its empty components are dropped."""
    _fake_pdflatex(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", path_value)
    monkeypatch.setattr(engines, "_candidate_dirs", lambda: [])
    found, reason = engines.find_pdflatex()
    assert found is None
    assert "not found" in reason


def test_wrong_override_fails_closed_and_never_searches(monkeypatch, tmp_path):
    _fake_pdflatex(tmp_path)  # a search WOULD find this one
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(settings, "maestro_cs_pdflatex", tmp_path / "nope")
    status = engines.probe_pdflatex()
    assert status.available is False
    assert "MAESTRO_CS_PDFLATEX" in status.reason
    assert engines.pdflatex_command() == str(tmp_path / "nope")


def test_version_runs_once_per_path(monkeypatch, tmp_path):
    exe = _fake_pdflatex(tmp_path)
    monkeypatch.setattr(settings, "maestro_cs_pdflatex", exe)
    calls: list[list[str]] = []
    real_run = subprocess.run

    def counting_run(argv, **kwargs):
        calls.append(list(argv))
        return real_run(argv, **kwargs)

    monkeypatch.setattr(engines.subprocess, "run", counting_run)
    engines.probe_pdflatex()
    engines.probe_pdflatex()
    assert len(calls) == 1


def test_a_failed_version_is_not_cached(monkeypatch, tmp_path):
    """Only successes are cached. A probe landing mid-install sees the symlink
    farm before the binary runs, and caching THAT would mark TeX missing for the
    life of the process — the opposite of "noticed on the next probe"."""
    exe = _stub_pdflatex(tmp_path, "exit 1")
    monkeypatch.setattr(settings, "maestro_cs_pdflatex", exe)
    assert engines.probe_pdflatex().available is False

    _fake_pdflatex(tmp_path)  # the install finished; same path, now runnable
    status = engines.probe_pdflatex()  # deliberately no reset_cache()
    assert status.available is True
    assert status.version.startswith("pdfTeX")


def test_undecodable_version_output_is_reported_not_raised(monkeypatch, tmp_path):
    """A banner that is not valid UTF-8 must not throw UnicodeDecodeError (a
    ValueError, so not an OSError) out of a probe whose whole job is to report."""
    exe = _stub_pdflatex(tmp_path, r"printf '\377pdfTeX 3.14 (TeX Live 2025)\n'")
    monkeypatch.setattr(settings, "maestro_cs_pdflatex", exe)
    status = engines.probe_pdflatex()
    assert status.available is True
    assert "pdfTeX" in status.version


def test_pdflatex_command_resolves_an_absolute_path_without_an_override(
    monkeypatch, tmp_path
):
    exe = _fake_pdflatex(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert engines.pdflatex_command() == str(exe)


def test_pdflatex_command_falls_back_to_the_bare_name(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))  # empty dir: nothing to find
    monkeypatch.setattr(engines, "_candidate_dirs", lambda: [])
    assert engines.pdflatex_command() == "pdflatex"


def test_typst_probe_reports_version_and_fonts():
    status = engines.probe_typst()
    assert status.available is True
    assert status.version


def test_typst_probe_fails_when_a_font_dir_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "typst_font_paths", [tmp_path / "missing"])
    status = engines.probe_typst()
    assert status.available is False
    assert "missing" in status.reason


def test_typst_without_distribution_metadata_is_still_available(monkeypatch):
    """A frozen build (where the desktop shell is headed) imports the module
    with no dist-info behind it. That costs the version string, not the engine."""
    def _no_metadata(_name):
        raise importlib.metadata.PackageNotFoundError("typst")

    monkeypatch.setattr(engines.importlib.metadata, "version", _no_metadata)
    status = engines.probe_typst()
    assert status.available is True
    assert status.version is None


def test_probe_bundles_both_engines():
    both = engines.probe()
    assert both.typst.name == "typst"
    assert both.pdflatex.name == "pdflatex"
    assert both.pdflatex == engines.probe_pdflatex()
    assert both.typst == engines.probe_typst()
