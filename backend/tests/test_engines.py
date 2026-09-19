"""The probe is the ONE place that looks for a PDF engine binary."""
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


def test_typst_probe_reports_version_and_fonts():
    status = engines.probe_typst()
    assert status.available is True
    assert status.version


def test_typst_probe_fails_when_a_font_dir_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "typst_font_paths", [tmp_path / "missing"])
    status = engines.probe_typst()
    assert status.available is False
    assert "missing" in status.reason


def test_probe_bundles_both_engines():
    both = engines.probe()
    assert both.typst.name == "typst"
    assert both.pdflatex.name == "pdflatex"
