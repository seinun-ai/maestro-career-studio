"""Stage A data-contract tests for custom (extra) resume sections.

Covers the typed ``extra_sections`` discriminated union, its validators, and
the requirement that every ResumeData write path preserves extras while storing
canonical (normalized) content. Phase 1 is ATS-neutral; these tests only assert
the data contract and render-filtering, not ATS/gap behavior.
"""
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.db import get_db
from app.main import app
from app.models.application import Application
from app.models.base_resume import BaseResume
from app.models.job import Job
from app.routers import base_resumes as base_router_module
from app.schemas.resume import ResumeData
from app.services import base_resume_render
from app.services.resume_edit import apply_edits
from app.services.resume_projects import active_extra_sections, resume_for_render
from app.services.resume_versions import record_version

CONTACT = {"name": "Sample", "email": "a@example.com"}


def _resume(**extra) -> dict:
    return {"contact": CONTACT, **extra}


def _entries_section(key="publications", title="Publications", **over) -> dict:
    section = {
        "key": key,
        "title": title,
        "type": "entries",
        "entries": [
            {
                "heading": "A paper title",
                "subheading": "Journal",
                "date": "2025",
                "link": "https://example.com/p",
                "bullets": ["Cited widely."],
            }
        ],
    }
    section.update(over)
    return section


def _bullets_section(key="awards", title="Awards", **over) -> dict:
    section = {
        "key": key,
        "title": title,
        "type": "bullets",
        "bullets": ["First place, Example Competition, 2025"],
    }
    section.update(over)
    return section


# --------------------------------------------------------------------------- #
# Schema: compatibility + union variants
# --------------------------------------------------------------------------- #


def test_old_json_without_extra_sections_stays_valid():
    data = ResumeData.model_validate(_resume(summary="Hi"))
    assert data.extra_sections == []
    # The field is always present in the canonical dump (default []).
    assert data.model_dump(mode="json")["extra_sections"] == []


def test_entries_variant_round_trips():
    data = ResumeData.model_validate(_resume(extra_sections=[_entries_section()]))
    dumped = data.model_dump(mode="json")["extra_sections"][0]
    assert dumped["type"] == "entries"
    assert dumped["key"] == "publications"
    assert dumped["entries"][0]["heading"] == "A paper title"
    assert "bullets" not in dumped  # entries section has no top-level bullets field


def test_bullets_variant_round_trips():
    data = ResumeData.model_validate(_resume(extra_sections=[_bullets_section()]))
    dumped = data.model_dump(mode="json")["extra_sections"][0]
    assert dumped["type"] == "bullets"
    assert dumped["bullets"] == ["First place, Example Competition, 2025"]
    assert "entries" not in dumped  # bullets section has no entries field


def test_entry_optional_fields_default_to_none_and_enabled():
    data = ResumeData.model_validate(
        _resume(
            extra_sections=[
                {
                    "key": "vol",
                    "title": "Volunteer",
                    "type": "entries",
                    "entries": [{"heading": "Habitat build"}],
                }
            ]
        )
    )
    entry = data.extra_sections[0].entries[0]
    assert entry.subheading is None and entry.location is None
    assert entry.date is None and entry.link is None
    assert entry.enabled is True
    assert entry.bullets == []


# --------------------------------------------------------------------------- #
# Schema: validation rejections
# --------------------------------------------------------------------------- #


def test_both_content_fields_at_once_rejected():
    with pytest.raises(ValidationError):
        ResumeData.model_validate(
            _resume(
                extra_sections=[
                    {
                        "key": "x",
                        "title": "X",
                        "type": "entries",
                        "entries": [],
                        "bullets": ["not allowed here"],
                    }
                ]
            )
        )


def test_bullets_section_rejects_entries_field():
    with pytest.raises(ValidationError):
        ResumeData.model_validate(
            _resume(
                extra_sections=[
                    {
                        "key": "x",
                        "title": "X",
                        "type": "bullets",
                        "bullets": [],
                        "entries": [{"heading": "nope"}],
                    }
                ]
            )
        )


def test_missing_type_discriminator_rejected():
    with pytest.raises(ValidationError):
        ResumeData.model_validate(
            _resume(extra_sections=[{"key": "x", "title": "X", "bullets": ["a"]}])
        )


def test_duplicate_keys_rejected_case_insensitively():
    # Keys are lowercase slugs; the uniqueness check is casefold-based so a
    # would-be case variant is treated as the same identity.
    with pytest.raises(ValidationError):
        ResumeData.model_validate(
            _resume(
                extra_sections=[
                    _bullets_section(key="awards", title="Awards"),
                    _bullets_section(key="awards", title="More Awards"),
                ]
            )
        )


@pytest.mark.parametrize(
    "reserved",
    ["contact", "summary", "skills", "experience", "projects", "education", "certifications"],
)
def test_reserved_core_key_rejected(reserved):
    with pytest.raises(ValidationError):
        ResumeData.model_validate(
            _resume(extra_sections=[_bullets_section(key=reserved, title="X")])
        )


@pytest.mark.parametrize("bad", ["Bad Slug", "has space", "UPPER", "_leading", "-lead", "sym!bol", ""])
def test_bad_slug_key_rejected(bad):
    with pytest.raises(ValidationError):
        ResumeData.model_validate(
            _resume(extra_sections=[_bullets_section(key=bad, title="X")])
        )


@pytest.mark.parametrize(
    "title",
    # Case- and whitespace-insensitive; covers the core headers that actually
    # render (incl. "Technical Skills", the skills section's printed header).
    ["Experience", "projects", "EDUCATION", "Technical Skills", " Summary ",
     "Certifications", "skills"],
)
def test_extra_section_title_colliding_with_core_header_rejected(title):
    # F6: an extra-section title equal to a core section's display header would
    # print a duplicate header in the PDF, so it is rejected.
    with pytest.raises(ValidationError):
        ResumeData.model_validate(
            _resume(extra_sections=[_bullets_section(key="awards", title=title)])
        )


def test_non_colliding_title_accepted():
    data = ResumeData.model_validate(
        _resume(extra_sections=[_bullets_section(key="awards", title="Awards & Honors")])
    )
    assert data.extra_sections[0].title == "Awards & Honors"


def test_valid_slug_variants_accepted():
    data = ResumeData.model_validate(
        _resume(
            extra_sections=[
                _bullets_section(key="a", title="A"),
                _bullets_section(key="pub-2025", title="B"),
                _bullets_section(key="vol_work3", title="C"),
            ]
        )
    )
    assert [s.key for s in data.extra_sections] == ["a", "pub-2025", "vol_work3"]


def test_section_order_is_preserved():
    keys = ["publications", "awards", "volunteer"]
    data = ResumeData.model_validate(
        _resume(extra_sections=[_bullets_section(key=k, title=k.title()) for k in keys])
    )
    assert [s.key for s in data.extra_sections] == keys


# --------------------------------------------------------------------------- #
# resume_for_render: disabled filtering
# --------------------------------------------------------------------------- #


def test_resume_for_render_filters_disabled_sections_and_entries():
    data = _resume(
        extra_sections=[
            {
                "key": "publications",
                "title": "Publications",
                "type": "entries",
                "enabled": True,
                "entries": [
                    {"heading": "Kept", "enabled": True},
                    {"heading": "Dropped", "enabled": False},
                    {"heading": "DefaultKept"},
                ],
            },
            _bullets_section(key="hidden", title="Hidden", enabled=False),
            _bullets_section(key="shown", title="Shown"),
        ]
    )
    out = resume_for_render(data)
    sections = out["extra_sections"]
    assert [s["key"] for s in sections] == ["publications", "shown"]
    pub_headings = [e["heading"] for e in sections[0]["entries"]]
    assert pub_headings == ["Kept", "DefaultKept"]
    # Caller data is not mutated (shallow-copy contract).
    assert len(data["extra_sections"]) == 3
    assert len(data["extra_sections"][0]["entries"]) == 3


def test_active_extra_sections_handles_missing_and_empty():
    assert active_extra_sections(None) == []
    assert active_extra_sections([]) == []


def test_resume_for_render_defaults_extra_sections_key():
    out = resume_for_render(_resume())
    assert out["extra_sections"] == []


# --------------------------------------------------------------------------- #
# Write-path preservation: apply_edits (from-base / materialize / typed edits)
# --------------------------------------------------------------------------- #


def test_apply_edits_preserves_extra_sections():
    base = _resume(
        summary="Old",
        extra_sections=[_entries_section(), _bullets_section()],
    )
    from app.schemas.resume_edit import ReplaceSummary

    result = apply_edits(base, [ReplaceSummary(kind="replace_summary", value="New")])
    assert result["summary"] == "New"
    assert [s["key"] for s in result["extra_sections"]] == ["publications", "awards"]


def test_apply_edits_rejects_invalid_extra_sections_in_base():
    # A base whose extras violate the contract must not pass validation.
    base = _resume(
        extra_sections=[
            _bullets_section(key="awards"),
            _bullets_section(key="awards", title="dup"),
        ]
    )
    from app.schemas.resume_edit import ReplaceSummary

    with pytest.raises(ValueError):
        apply_edits(base, [ReplaceSummary(kind="replace_summary", value="x")])


# --------------------------------------------------------------------------- #
# Write-path preservation: base PUT (API round-trip, DB + on-disk)
# --------------------------------------------------------------------------- #


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


def _stub_base_render(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(base_router_module.settings, "base_resumes_dir", tmp_path)
    monkeypatch.setattr(base_resume_render.settings, "base_resumes_dir", tmp_path)

    def fake_render(slug, db, *, template_id=None):
        row = db.get(BaseResume, slug)
        row.pdf_rendered_at = datetime.now(UTC)
        db.commit()
        db.refresh(row)
        return row

    monkeypatch.setattr(base_resume_render, "render_base_resume", fake_render)
    monkeypatch.setattr(
        base_router_module.base_resume_render, "render_base_resume", fake_render
    )


def test_base_put_preserves_extra_sections_in_db_file_and_response(
    db_session, tmp_path, monkeypatch
):
    import json

    _stub_base_render(monkeypatch, tmp_path)
    db_session.add(
        BaseResume(slug="data_scientist", display_name="DS", data_json=_resume())
    )
    db_session.commit()

    new_data = _resume(
        summary="With extras",
        extra_sections=[_entries_section(), _bullets_section()],
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).put(
            "/api/base-resumes/data_scientist",
            json={"display_name": "DS", "data": new_data},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    # API response round-trips extras
    resp_sections = response.json()["data"]["extra_sections"]
    assert [s["key"] for s in resp_sections] == ["publications", "awards"]
    # DB JSONB row keeps them
    row = db_session.get(BaseResume, "data_scientist")
    assert [s["key"] for s in row.data_json["extra_sections"]] == ["publications", "awards"]
    # On-disk mirror keeps them
    written = json.loads((tmp_path / "data_scientist.json").read_text(encoding="utf-8"))
    assert [s["key"] for s in written["extra_sections"]] == ["publications", "awards"]


# --------------------------------------------------------------------------- #
# Write-path preservation: application PATCH (canonical/normalized storage)
# --------------------------------------------------------------------------- #


def _job(db_session) -> Job:
    job = Job(
        raw_text="Need Python",
        raw_text_hash="extra-sections-contract",
        extracted_json={"title": "Data Scientist", "company": "Acme"},
        title="Data Scientist",
        company="Acme",
        role_category="data_scientist",
        extracted_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def test_application_patch_preserves_extras_and_drops_junk(db_session):
    job = _job(db_session)
    application = Application(
        job_id=job.id, base_resume="data_scientist", status="draft"
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    payload_json = _resume(
        summary="Draft",
        extra_sections=[_bullets_section()],
    )
    payload_json["bogus_unknown_key"] = 123  # must be dropped by normalization

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).patch(
            f"/api/applications/{application.id}",
            json={"customized_json": payload_json},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    stored = response.json()["customized_json"]
    assert [s["key"] for s in stored["extra_sections"]] == ["awards"]
    # Convergence: unknown junk keys no longer half-survive here.
    assert "bogus_unknown_key" not in stored
    # DB row is the normalized dump, too.
    db_session.refresh(application)
    assert "bogus_unknown_key" not in application.customized_json
    assert application.customized_json["extra_sections"][0]["type"] == "bullets"


def test_application_patch_rejects_invalid_extra_sections(db_session):
    job = _job(db_session)
    application = Application(
        job_id=job.id, base_resume="data_scientist", status="draft"
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    bad = _resume(extra_sections=[_bullets_section(key="summary", title="collides")])

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).patch(
            f"/api/applications/{application.id}",
            json={"customized_json": bad},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Write-path preservation: version restore
# --------------------------------------------------------------------------- #


def test_application_restore_preserves_extra_sections(db_session):
    job = _job(db_session)
    application = Application(
        job_id=job.id,
        base_resume="data_scientist",
        status="draft",
        customized_json=_resume(summary="core only"),
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    key = str(application.id)
    # v1: core only ; v2: with extras
    record_version(db_session, "application", key, _resume(summary="core only"), source="form_edit")
    with_extras = _resume(summary="has extras", extra_sections=[_entries_section()])
    record_version(db_session, "application", key, with_extras, source="edit_ops")
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            f"/api/resume-versions/application/{key}/2/restore"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    db_session.refresh(application)
    restored = application.customized_json
    assert restored["summary"] == "has extras"
    assert [s["key"] for s in restored["extra_sections"]] == ["publications"]
