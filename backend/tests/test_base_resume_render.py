from pathlib import Path

from tests.pdf_fixtures import write_blank_pdf

from app.models.base_resume import BaseResume
from app.services import base_resume_render, pdf_render


def _write_valid_pdf(path: Path, pages: int = 1) -> None:
    write_blank_pdf(path, pages)


SAMPLE_DATA = {
    "contact": {"name": "Sample", "email": "a@example.com"},
    "summary": "Summary",
    "skills": [{"category": "Core", "items": ["Python"]}],
    "experience": [],
    "projects": [],
    "education": [],
    "certifications": [],
}


def test_render_base_resume_writes_files_and_updates_row(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(base_resume_render.settings, "base_resumes_dir", tmp_path)

    def fake_render_and_compile(
        data,
        tex_path: Path,
        pdf_path: Path,
        *,
        template_id=None,
        session=None,
        formatting=None,
    ):
        tex_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        tex_path.write_text("tex", encoding="utf-8")
        _write_valid_pdf(pdf_path)
        return tex_path, pdf_render.RenderedDoc("latex", "tex")

    monkeypatch.setattr(pdf_render, "render_and_compile", fake_render_and_compile)

    db_session.add(
        BaseResume(slug="data_scientist", display_name="DS", data_json=SAMPLE_DATA)
    )
    db_session.commit()

    row = base_resume_render.render_base_resume("data_scientist", db_session)

    assert row.pdf_path == str(tmp_path / "pdfs" / "data_scientist.pdf")
    assert row.tex_path == str(tmp_path / "tex" / "data_scientist.tex")
    assert row.pdf_rendered_at is not None
    assert row.pdf_pages == 1
    assert row.render_error is None
    assert Path(row.pdf_path).exists()
    assert Path(row.tex_path).exists()


def test_render_base_resume_raises_when_slug_missing(db_session):
    import pytest

    with pytest.raises(LookupError):
        base_resume_render.render_base_resume("nope", db_session)


def test_render_base_resume_propagates_pdflatex_failure(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(base_resume_render.settings, "base_resumes_dir", tmp_path)

    def fake_render_and_compile(data, tex_path, pdf_path, *, template_id=None, session=None, formatting=None):
        raise RuntimeError("pdflatex boom")

    monkeypatch.setattr(pdf_render, "render_and_compile", fake_render_and_compile)

    db_session.add(
        BaseResume(slug="data_scientist", display_name="DS", data_json=SAMPLE_DATA)
    )
    db_session.commit()

    import pytest

    with pytest.raises(RuntimeError, match="pdflatex"):
        base_resume_render.render_base_resume("data_scientist", db_session)
