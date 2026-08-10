"""Compile-path hardening for the Typst engine (FIX-4/5/6/7): wall-clock
timeout, fail-closed package rejection, per-render root scoping, and located
diagnostics. All exercise the real out-of-process compiler."""

import re
import time

import pytest

from app.services import pdf_render, typst_compiler

pytest.importorskip("typst")


def test_source_imports_package_is_comment_and_string_aware():
    assert typst_compiler.source_imports_package('#import "@preview/cetz:0.2.0"')
    assert typst_compiler.source_imports_package('import "@local/x:1.0.0": *')
    # only inside a comment -> not an import
    assert not typst_compiler.source_imports_package('// #import "@preview/cetz:0.2.0"\n= hi')
    assert not typst_compiler.source_imports_package('/* import "@preview/x:1.0" */\n= hi')
    # a plain file import is not a package import
    assert not typst_compiler.source_imports_package('#import "header.typ": *')


def test_typst_rejects_remote_package_import_fast(tmp_path):
    """FIX-5: a source importing a package fails closed (RuntimeError) BEFORE any
    compile/network fetch. The reject is local, so it returns near-instantly."""
    src = '#import "@preview/cetz:0.2.0"\n= hi\n'
    t0 = time.monotonic()
    with pytest.raises(RuntimeError, match="package"):
        pdf_render.compile_typst_pdf(src, tmp_path, stem="pkg", sys_inputs={})
    assert time.monotonic() - t0 < 2.0  # no network round trip


def test_typst_package_mention_in_comment_still_compiles(tmp_path):
    """A @preview reference inside a comment must NOT trip the gate."""
    src = '// see #import "@preview/cetz:0.2.0" for ideas\n= Hello\n'
    pdf = pdf_render.compile_typst_pdf(src, tmp_path, stem="ok", sys_inputs={})
    assert pdf.exists()


def test_typst_compile_times_out(tmp_path, monkeypatch):
    """FIX-4: a pathological compile is bounded and killed, not left to hang."""
    monkeypatch.setattr(typst_compiler, "TYPST_COMPILE_TIMEOUT_S", 2.0)
    slow = "#for i in range(2000000) [x ]\n"  # >> any few-second bound
    t0 = time.monotonic()
    with pytest.raises(RuntimeError, match="time limit|terminated"):
        pdf_render.compile_typst_pdf(slow, tmp_path, stem="slow", sys_inputs={})
    elapsed = time.monotonic() - t0
    assert elapsed < 20, f"did not terminate near the bound (took {elapsed:.1f}s)"


def test_typst_cannot_read_sibling_render_source(tmp_path):
    """FIX-6: the render root is scoped to a staging dir holding only this
    render's input, so a template cannot read a sibling file in the output dir
    (base resumes share one tex/ dir)."""
    (tmp_path / "secret.typ").write_text("SECRET DATA", encoding="utf-8")
    src = '#let s = read("secret.typ")\n#s\n'
    with pytest.raises(RuntimeError, match="typst failed"):
        pdf_render.compile_typst_pdf(src, tmp_path, stem="leak", sys_inputs={})


def test_typst_error_message_carries_location(tmp_path):
    """FIX-7: the RuntimeError surfaces the located diagnostic (file:line:col),
    not just the bare message."""
    src = "#let x = 1\n#bad_expr(\n"  # unclosed delimiter at 2:9
    with pytest.raises(RuntimeError) as ei:
        pdf_render.compile_typst_pdf(src, tmp_path, stem="syn", sys_inputs={})
    msg = str(ei.value)
    assert "typst failed" in msg
    assert re.search(r":\d+:\d+", msg), f"no file:line:col in message: {msg!r}"
