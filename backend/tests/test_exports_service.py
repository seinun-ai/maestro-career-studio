from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.models.career_kb import KBEntity, KBPoint, KBProfile
from app.services import exports


FIXED_NOW = datetime(2026, 8, 3, 15, 30, tzinfo=UTC)


def _seed_career(db_session):
    profile = KBProfile(
        id=1,
        contact_json={"name": "Sample", "email": "sample@example.com"},
        summary="Data and AI builder",
        skills_json=[{"category": "Core", "items": ["Python", "FastAPI"]}],
        notes="Prefers evidence over claims.",
    )
    active = KBEntity(
        kind="project",
        title="Maestro CS",
        status="ongoing",
        detail_json={"tech": "Python, Next.js"},
        notes="Built to make application work repeatable.",
    )
    archived = KBEntity(
        kind="project",
        title="Archived Secret",
        status="archived",
        detail_json={},
        notes="must not export",
    )
    db_session.add_all([profile, active, archived])
    db_session.flush()
    db_session.add_all([
        KBPoint(entity_id=active.id, text="Shipped deterministic ATS scoring", state="approved", origin="manual"),
        KBPoint(entity_id=active.id, text="Unreviewed claim", state="draft", origin="ingested"),
        KBPoint(entity_id=archived.id, text="Archived claim", state="approved", origin="manual"),
    ])
    db_session.commit()


def test_render_contains_only_current_approved_career_data(db_session, tmp_path, monkeypatch):
    _seed_career(db_session)
    monkeypatch.setattr(exports.settings, "exports_dir", tmp_path)
    monkeypatch.setattr(exports, "_utc_now", lambda: FIXED_NOW)

    result = exports.get_career_export(db_session, force=True)

    assert result.cached is False
    assert "# Career Profile" in result.markdown
    assert "Data and AI builder" in result.markdown
    assert "Python" in result.markdown
    assert "Maestro CS" in result.markdown
    assert "Shipped deterministic ATS scoring" in result.markdown
    assert "Built to make application work repeatable" in result.markdown
    assert "Unreviewed claim" not in result.markdown
    assert "Archived Secret" not in result.markdown
    assert f"Content SHA-256: `{result.content_hash}`" in result.markdown
    assert "Generated: 2026-08-03T15:30:00Z" in result.markdown
    assert (tmp_path / "career.md").read_text() == result.markdown


def test_unchanged_source_reads_cache_without_rewrite(db_session, tmp_path, monkeypatch):
    _seed_career(db_session)
    monkeypatch.setattr(exports.settings, "exports_dir", tmp_path)
    monkeypatch.setattr(exports, "_utc_now", lambda: FIXED_NOW)

    first = exports.get_career_export(db_session)
    first_mtime = (tmp_path / "career.md").stat().st_mtime_ns
    second = exports.get_career_export(db_session)

    assert second.cached is True
    assert second.markdown == first.markdown
    assert (tmp_path / "career.md").stat().st_mtime_ns == first_mtime


def test_source_change_invalidates_cache(db_session, tmp_path, monkeypatch):
    _seed_career(db_session)
    monkeypatch.setattr(exports.settings, "exports_dir", tmp_path)
    monkeypatch.setattr(exports, "_utc_now", lambda: FIXED_NOW)

    first = exports.get_career_export(db_session)
    profile = db_session.get(KBProfile, 1)
    profile.summary = "Changed summary"
    db_session.commit()
    second = exports.get_career_export(db_session)

    assert second.cached is False
    assert second.content_hash != first.content_hash
    assert "Changed summary" in second.markdown


def test_disk_failure_returns_fresh_body(db_session, tmp_path, monkeypatch, caplog):
    _seed_career(db_session)
    monkeypatch.setattr(exports.settings, "exports_dir", tmp_path)
    monkeypatch.setattr(exports, "_persist", lambda result: (_ for _ in ()).throw(OSError("read only")))

    result = exports.get_career_export(db_session, force=True)

    assert "Data and AI builder" in result.markdown
    assert "read only" in caplog.text


def test_composition_failure_never_returns_stale_file(db_session, tmp_path, monkeypatch):
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "career.md").write_text("stale career")
    (tmp_path / ".meta.json").write_text('{"career":{"hash":"old","generated_at":"2026-01-01T00:00:00Z"}}')
    monkeypatch.setattr(exports.settings, "exports_dir", tmp_path)
    monkeypatch.setattr(exports.career_kb, "compose_resume_data", lambda _session: (_ for _ in ()).throw(RuntimeError("compose failed")))

    with pytest.raises(RuntimeError, match="compose failed"):
        exports.get_career_export(db_session)


def test_memory_headings_nest_under_beyond_the_resume(db_session, tmp_path, monkeypatch):
    _seed_career(db_session)
    monkeypatch.setattr(exports.settings, "exports_dir", tmp_path)
    monkeypatch.setattr(
        exports.career_kb,
        "compose_context",
        lambda _s: "IDENTITY\n## Maestro CS (ongoing)\nA #hashtag stays put.",
    )

    markdown = exports.get_career_export(db_session, force=True).markdown
    headings = [ln for ln in markdown.splitlines() if ln.startswith("#")]

    # The entity header arrived as `##` from the prompt block; as a sibling of
    # `## Contact` it would flatten the document outline.
    assert "### Maestro CS (ongoing)" in headings
    assert "## Maestro CS (ongoing)" not in headings
    assert headings.index("## Beyond the Resume") < headings.index("### Maestro CS (ongoing)")
    assert "A #hashtag stays put." in markdown


def test_renderer_version_change_invalidates_cache(db_session, tmp_path, monkeypatch):
    _seed_career(db_session)
    monkeypatch.setattr(exports.settings, "exports_dir", tmp_path)
    monkeypatch.setattr(exports, "_utc_now", lambda: FIXED_NOW)

    first = exports.get_career_export(db_session)
    assert exports.get_career_export(db_session).cached is True

    # Same KB data, new renderer: the cached body was shaped by the old one, so
    # it must NOT be served back.
    monkeypatch.setattr(exports, "RENDERER_VERSION", "next")
    second = exports.get_career_export(db_session)

    assert second.cached is False
    assert second.content_hash != first.content_hash


def test_refresh_failure_leaves_the_session_usable_for_the_caller(db_session, tmp_path, monkeypatch):
    _seed_career(db_session)
    monkeypatch.setattr(exports.settings, "exports_dir", tmp_path)

    def _failing_query(session):
        session.execute(text("SELECT 1 FROM a_table_that_does_not_exist"))

    monkeypatch.setattr(exports.career_kb, "compose_resume_data", _failing_query)
    exports.best_effort_refresh(db_session)

    # Mutation handlers call the hook after committing and then keep querying
    # this session to build their response body.
    assert db_session.get(KBProfile, 1).summary == "Data and AI builder"
