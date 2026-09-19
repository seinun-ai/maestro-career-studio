"""Design 2026-09-19 §2.2: a render never changes engine silently, and a
missing pdflatex is an actionable error, never a 500 from FileNotFoundError."""
import pytest

from app.services import engines, pdf_render

MINIMAL_TEX = "\\documentclass{article}\\begin{document}x\\end{document}"


def _no_tex(monkeypatch):
    monkeypatch.setattr(engines, "find_pdflatex", lambda: (None, "pdflatex not found (test)"))
    monkeypatch.setattr(engines, "pdflatex_command", lambda: "/nonexistent/pdflatex")
    monkeypatch.setattr(engines, "pdflatex_available", lambda: False)


def test_argv_uses_the_resolved_binary(monkeypatch, tmp_path):
    monkeypatch.setattr(engines, "pdflatex_command", lambda: "/opt/tex/bin/pdflatex")
    argv = pdf_render._pdflatex_argv(tmp_path / "x.tex", tmp_path, "x")
    assert argv[0] == "/opt/tex/bin/pdflatex"
    assert "-no-shell-escape" in argv


def test_compile_pdf_without_pdflatex_is_a_runtime_error(monkeypatch, tmp_path):
    _no_tex(monkeypatch)
    with pytest.raises(RuntimeError, match="pdflatex is not installed"):
        pdf_render.compile_pdf(MINIMAL_TEX, tmp_path)


def test_render_and_compile_without_pdflatex_is_a_runtime_error(monkeypatch, tmp_path):
    _no_tex(monkeypatch)
    from app.services.template_validation import SAMPLE_RESUME

    with pytest.raises(RuntimeError, match="pdflatex is not installed"):
        pdf_render.render_and_compile(
            SAMPLE_RESUME, tmp_path / "r.tex", tmp_path / "r.pdf"
        )


def test_a_directory_as_pdflatex_is_the_same_runtime_error(monkeypatch, tmp_path):
    # A wrong MAESTRO_CS_PDFLATEX may name a directory: spawning one raises
    # PermissionError / IsADirectoryError, not FileNotFoundError.
    monkeypatch.setattr(engines, "find_pdflatex", lambda: (None, "MAESTRO_CS_PDFLATEX points at a directory (test)"))
    monkeypatch.setattr(engines, "pdflatex_command", lambda: str(tmp_path))
    monkeypatch.setattr(engines, "pdflatex_available", lambda: False)
    with pytest.raises(RuntimeError, match="pdflatex is not installed"):
        pdf_render.compile_pdf(MINIMAL_TEX, tmp_path / "out")
