"""Stable per-application artifact folder allocation and backfill."""
from datetime import date
from pathlib import Path

from app.config import settings as app_settings
from app.models.application import Application
from app.services import application_artifacts
from tests.test_proposals_models import _mk_job


def _mk_app(db_session, *, company="Acme", **kw):
    job = _mk_job(db_session, company=company, title="Data Engineer")
    app_row = Application(job_id=job.id, base_resume="hybrid", status="draft", **kw)
    db_session.add(app_row)
    db_session.commit()
    db_session.refresh(app_row)
    return app_row, job


def test_get_dir_allocates_collision_safe_folder_once(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)
    app_row, job = _mk_app(db_session, company="Starbucks")

    first = application_artifacts.get_dir(
        db_session,
        app_row,
        company=job.company,
        role_label="DataEngineer",
        when=date(2026, 7, 30),
    )
    second = application_artifacts.get_dir(db_session, app_row)

    prefix = app_row.id.hex[:8]
    assert first.name == f"Starbucks_DataEngineer_20260730_{prefix}"
    assert first.parent == tmp_path
    assert first.is_dir()
    assert second == first
    assert app_row.artifact_dir == str(first)


def test_get_dir_backfills_unique_pdf_parent(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)
    legacy = tmp_path / "Acme_DataEngineer_20260729"
    legacy.mkdir()
    pdf = legacy / "Resume.pdf"
    pdf.write_bytes(b"%PDF")
    app_row, _job = _mk_app(db_session)
    app_row.pdf_path = str(pdf)
    db_session.commit()

    resolved = application_artifacts.get_dir(db_session, app_row)

    assert resolved == legacy.resolve()
    assert app_row.artifact_dir == str(legacy.resolve())


def test_get_dir_moves_when_pdf_parent_is_shared(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)
    shared = tmp_path / "Acme_DataEngineer_20260729"
    shared.mkdir()
    pdf_a = shared / "A.pdf"
    pdf_b = shared / "B.pdf"
    pdf_a.write_bytes(b"%PDF-a")
    pdf_b.write_bytes(b"%PDF-b")

    app_a, job = _mk_app(db_session, company="Acme")
    app_a.pdf_path = str(pdf_a)
    app_b, _ = _mk_app(db_session, company="Acme")
    app_b.pdf_path = str(pdf_b)
    db_session.commit()

    resolved = application_artifacts.get_dir(
        db_session,
        app_a,
        company=job.company,
        role_label="DataEngineer",
        when=date(2026, 7, 30),
    )

    assert resolved != shared.resolve()
    assert resolved.name.endswith(f"_{app_a.id.hex[:8]}")
    assert (resolved / "A.pdf").read_bytes() == b"%PDF-a"
    assert Path(app_a.pdf_path) == resolved / "A.pdf"
    assert app_a.artifact_dir == str(resolved)


def test_application_artifact_dir_column_nullable(db_session):
    app_row, _ = _mk_app(db_session)
    assert app_row.artifact_dir is None
