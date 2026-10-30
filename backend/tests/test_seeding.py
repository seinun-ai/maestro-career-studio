import json
import logging
from pathlib import Path

from app.models.base_resume import BaseResume
from app.models.setting import Setting
from app.services import seeding


def test_first_start_without_tex_renders_the_demo_with_typst(db_session, tmp_path, monkeypatch):
    from app.services import engines, template_registry
    from app.models.template import Template

    monkeypatch.setattr(seeding.settings, "base_resumes_dir", tmp_path)
    monkeypatch.setattr(seeding.settings, "maestro_cs_pdflatex", "/nonexistent")
    monkeypatch.setattr(seeding.settings, "settings_dir", tmp_path / "settings")
    monkeypatch.setattr(seeding.settings, "exports_dir", tmp_path / "exports")
    demo = Path(__file__).resolve().parents[2] / "base_resumes" / "example.json"
    (tmp_path / "example.json").write_bytes(demo.read_bytes())
    assert not engines.probe_pdflatex().available

    seeding.seed_startup_data(db_session)

    row = db_session.get(BaseResume, "example")
    assert row.pdf_rendered_at is not None
    assert row.render_error is None
    assert Path(row.pdf_path).read_bytes().startswith(b"%PDF")
    assert Path(row.tex_path).suffix == ".typ"
    assert db_session.get(Template, template_registry.TYPST_CLASSIC_ID).status == "ready"


def test_seed_render_failure_records_the_reason(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(seeding.settings, "base_resumes_dir", tmp_path)
    (tmp_path / "example.json").write_text('{"contact": {"name": "Sample"}}')

    def fail(slug, db):
        raise RuntimeError("No ready Typst template is available")

    monkeypatch.setattr(seeding.base_resume_render, "render_base_resume", fail)
    assert seeding.seed_base_resumes(db_session) == ["example"]
    row = db_session.get(BaseResume, "example")
    assert row.pdf_rendered_at is None
    assert row.render_error == "No ready Typst template is available"


def test_seed_base_resumes_inserts_missing_json_files(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(seeding.settings, "base_resumes_dir", tmp_path)
    monkeypatch.setattr(seeding.base_resume_render, "render_base_resume", lambda slug, db: None)
    (tmp_path / "hybrid.json").write_text(
        json.dumps({"contact": {"name": "Sample", "email": "a@example.com"}}),
        encoding="utf-8",
    )

    seeded = seeding.seed_base_resumes(db_session)
    seeded_again = seeding.seed_base_resumes(db_session)

    assert seeded == ["hybrid"]
    assert seeded_again == []
    row = db_session.get(BaseResume, "hybrid")
    assert row.display_name == "Hybrid"
    assert row.data_json["contact"]["name"] == "Sample"


def test_seed_base_resumes_renders_after_insert(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(seeding.settings, "base_resumes_dir", tmp_path)
    (tmp_path / "hybrid.json").write_text(
        json.dumps({"contact": {"name": "Sample", "email": "a@example.com"}}),
        encoding="utf-8",
    )
    rendered: list[str] = []
    monkeypatch.setattr(
        seeding.base_resume_render,
        "render_base_resume",
        lambda slug, db: rendered.append(slug),
    )

    seeding.seed_base_resumes(db_session)

    assert rendered == ["hybrid"]


def test_seed_base_resumes_tolerates_render_failure(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(seeding.settings, "base_resumes_dir", tmp_path)
    (tmp_path / "hybrid.json").write_text(
        json.dumps({"contact": {"name": "Sample", "email": "a@example.com"}}),
        encoding="utf-8",
    )

    def boom(slug, db):
        raise RuntimeError("pdflatex missing")

    monkeypatch.setattr(seeding.base_resume_render, "render_base_resume", boom)

    seeded = seeding.seed_base_resumes(db_session)

    assert seeded == ["hybrid"]


def test_a_seed_render_failure_is_logged(db_session, tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(seeding.settings, "base_resumes_dir", tmp_path)
    (tmp_path / "hybrid.json").write_text(
        json.dumps({"contact": {"name": "Sample", "email": "a@example.com"}}),
        encoding="utf-8",
    )

    def boom(slug, db):
        raise RuntimeError("boom")

    monkeypatch.setattr(seeding.base_resume_render, "render_base_resume", boom)
    with caplog.at_level(logging.WARNING, logger="app.services.seeding"):
        seeded = seeding.seed_base_resumes(db_session)

    assert seeded == ["hybrid"]
    assert db_session.get(BaseResume, "hybrid") is not None
    assert "hybrid" in caplog.text
    assert "boom" in caplog.text
    assert caplog.records[0].levelno == logging.WARNING
    assert caplog.records[0].exc_info is not None


def test_seed_prompts_inserts_missing_prompt_settings(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(seeding.prompts, "PROMPT_DIR", tmp_path)
    for key in seeding.prompts.VALID_PROMPTS:
        (tmp_path / f"{key}.txt").write_text(f"default {key}", encoding="utf-8")

    seeded = seeding.seed_prompts(db_session)

    assert set(seeded) == seeding.prompts.VALID_PROMPTS
    assert db_session.get(Setting, "prompt.qa").value == "default qa"


def test_run_startup_runs_migrations_and_seeds(monkeypatch):
    calls = []

    monkeypatch.setattr(seeding, "run_migrations", lambda: calls.append("migrate"))

    class FakeSession:
        def __enter__(self):
            calls.append("open")
            return self

        def __exit__(self, exc_type, exc, tb):
            calls.append("close")

    monkeypatch.setattr(seeding, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(seeding, "seed_startup_data", lambda session: calls.append("seed"))

    seeding.run_startup()

    assert calls == ["migrate", "open", "seed", "close"]


def test_seed_startup_data_refreshes_career_export_last(monkeypatch):
    calls = []
    session = object()
    for name in (
        "seed_base_resumes",
        "seed_prompts",
        "seed_templates",
        "ensure_persona",
        "seed_career_kb",
    ):
        monkeypatch.setattr(seeding, name, lambda _session, name=name: calls.append(name))
    monkeypatch.setattr(
        seeding.market_settings,
        "mark_answered_installs_chosen",
        lambda _session: calls.append("mark_answered_installs_chosen"),
    )
    monkeypatch.setattr(
        seeding.career_exports,
        "best_effort_refresh",
        lambda received: calls.append("refresh") if received is session else None,
    )

    seeding.seed_startup_data(session)

    assert calls == [
        "seed_templates",
        "seed_base_resumes",
        "seed_prompts",
        "ensure_persona",
        "mark_answered_installs_chosen",
        "seed_career_kb",
        "refresh",
    ]
