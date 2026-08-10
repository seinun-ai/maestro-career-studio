import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models.base_resume import BaseResume
from app.models.career_kb import KBEntity, KBPoint, KBProfile
from app.models.setting import Setting
from app.schemas.career_kb import ConsolidationReport
from app.services import kb_consolidation, seeding


def _resume(*, summary=None, projects=None):
    return {
        "contact": {"name": "Sample", "email": "sample@example.com"},
        "summary": summary,
        "skills": [],
        "experience": [],
        "projects": projects or [],
        "education": [],
        "certifications": [],
    }


def _project(name: str, *bullets: str) -> dict:
    return {"name": name, "enabled": True, "bullets": list(bullets)}


def _count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_seed_base_resumes_never_overwrites_an_existing_row(
    db_session, tmp_path, monkeypatch,
):
    """Seeding fills gaps only. An existing row is the user's live edit; a
    same-named file on disk is the shipped starting point and must lose."""
    db_session.add(
        BaseResume(
            slug="analyst", display_name="My Analyst", data_json=_resume(summary="mine")
        )
    )
    db_session.commit()
    monkeypatch.setattr(seeding.settings, "base_resumes_dir", tmp_path)
    monkeypatch.setattr(seeding.base_resume_render, "render_base_resume", lambda *_: None)
    (tmp_path / "analyst.json").write_text(
        json.dumps(_resume(summary="must not overwrite")), encoding="utf-8"
    )
    (tmp_path / "data_scientist.json").write_text(
        json.dumps(_resume(summary="DS")), encoding="utf-8"
    )

    seeded = seeding.seed_base_resumes(db_session)

    assert seeded == ["data_scientist"]
    db_session.expire_all()
    row = db_session.get(BaseResume, "analyst")
    assert row.display_name == "My Analyst"
    assert row.data_json["summary"] == "mine"


def test_seed_career_kb_guard_is_strict_no_op_when_entities_exist(
    db_session, monkeypatch,
):
    entity = KBEntity(kind="project", title="Existing", status="completed", detail_json={})
    db_session.add(entity)
    db_session.commit()

    def unexpected(*args, **kwargs):
        raise AssertionError("guarded seed must not inspect keys or run migration stages")

    monkeypatch.setattr(seeding.llm, "get_openai_key", unexpected)
    monkeypatch.setattr(seeding.kb_consolidation, "consolidate", unexpected)

    seeding.seed_career_kb(db_session)

    assert _count(db_session, KBEntity) == 1
    assert db_session.get(KBProfile, 1) is None


def test_seed_career_kb_without_sources_creates_only_bare_profile(
    db_session, monkeypatch,
):
    monkeypatch.setattr(
        seeding.llm,
        "get_openai_key",
        lambda: pytest.fail("no-source seed must not require an LLM key"),
    )

    seeding.seed_career_kb(db_session)

    db_session.expire_all()
    profile = db_session.get(KBProfile, 1)
    assert profile is not None
    assert profile.contact_json == {}
    assert profile.summary == ""
    assert profile.skills_json == []
    assert profile.notes == ""
    assert _count(db_session, KBEntity) == 0


def test_bare_profile_does_not_block_later_resume_seed(db_session, monkeypatch):
    seeding.seed_career_kb(db_session)
    assert db_session.get(KBProfile, 1) is not None

    db_session.add(BaseResume(slug="later", data_json=_resume()))
    db_session.commit()

    def fake_consolidate(session, sources, *, commit):
        assert [slug for slug, _data in sources] == ["later"]
        assert commit is False
        session.add(KBEntity(kind="project", title="Later project", detail_json={}))
        return ConsolidationReport(entities_created=1)

    monkeypatch.setattr(seeding.llm, "get_openai_key", lambda: "configured")
    monkeypatch.setattr(seeding.kb_consolidation, "consolidate", fake_consolidate)

    seeding.seed_career_kb(db_session)

    assert _count(db_session, KBEntity) == 1


def test_seed_career_kb_without_provider_key_defers_cleanly(
    db_session, monkeypatch, caplog,
):
    db_session.add(BaseResume(slug="data_scientist", data_json=_resume()))
    db_session.commit()
    monkeypatch.setattr(seeding.llm, "get_openai_key", lambda: None)
    monkeypatch.setattr(seeding.llm, "get_gemini_key", lambda: None)
    monkeypatch.setattr(
        seeding.kb_consolidation,
        "consolidate",
        lambda *_args, **_kwargs: pytest.fail("consolidation must be deferred"),
    )

    seeding.seed_career_kb(db_session)

    assert _count(db_session, KBEntity) == 0
    assert _count(db_session, KBPoint) == 0
    assert db_session.get(KBProfile, 1) is None
    assert "KB seed deferred: no LLM key configured" in caplog.text


def test_seed_career_kb_uses_every_active_source_in_stable_chronological_order(
    db_session, monkeypatch,
):
    now = datetime.now(UTC)
    rows = [
        BaseResume(
            slug="newer", data_json=_resume(summary="new"), updated_at=now,
        ),
        BaseResume(
            slug="oldest", data_json=_resume(summary="oldest"),
            updated_at=now - timedelta(days=2),
        ),
        BaseResume(
            slug="older", data_json=_resume(summary="old"),
            updated_at=now - timedelta(days=1),
        ),
        BaseResume(
            slug="deleted", data_json=_resume(summary="deleted"),
            updated_at=now + timedelta(days=1), deleted_at=now,
        ),
    ]
    db_session.add_all(rows)
    db_session.commit()
    events: list[object] = []

    def fake_consolidate(session, sources, *, commit):
        events.append(("consolidate", [slug for slug, _data in sources], commit))
        session.add(KBEntity(kind="project", title="Seeded", detail_json={}))
        return ConsolidationReport(entities_created=1)

    monkeypatch.setattr(seeding.llm, "get_openai_key", lambda: "configured")
    monkeypatch.setattr(seeding.kb_consolidation, "consolidate", fake_consolidate)

    seeding.seed_career_kb(db_session)

    assert events == [("consolidate", ["oldest", "older", "newer"], False)]
    assert _count(db_session, KBEntity) == 1


def test_seed_uses_most_recent_active_resume_for_profile(
    db_session, monkeypatch,
):
    now = datetime.now(UTC)
    db_session.add_all(
        [
            BaseResume(
                slug="older",
                data_json=_resume(
                    summary="Old summary",
                    projects=[_project("Orbit", "Built it")],
                ),
                updated_at=now - timedelta(days=1),
            ),
            BaseResume(
                slug="newer",
                data_json=_resume(
                    summary="Fresh summary",
                    projects=[_project("Orbit", "Built it")],
                ),
                updated_at=now,
            ),
        ]
    )
    db_session.commit()

    def fake_llm(*, prompt, model, response_format="json", **kwargs):
        if "group_indices" in prompt:
            return {
                "clusters": [
                    {
                        "group_indices": [0],
                        "existing_entity_id": None,
                        "canonical": {
                            "kind": "project",
                            "title": "Orbit",
                            "org": None,
                            "start_date": None,
                            "end_date": None,
                        },
                    }
                ]
            }
        if "bullet_indices" in prompt:
            return {
                "clusters": [
                    {
                        "bullet_indices": [0],
                        "existing_point_id": None,
                        "merged_text": None,
                    }
                ]
            }
        raise AssertionError("unexpected LLM prompt")

    monkeypatch.setattr(seeding.llm, "get_openai_key", lambda: "configured")
    monkeypatch.setattr(kb_consolidation.llm, "call_openai", fake_llm)

    seeding.seed_career_kb(db_session)

    db_session.expire_all()
    assert db_session.get(KBProfile, 1).summary == "Fresh summary"


def test_seed_career_kb_consolidates_with_mocked_llm(
    db_session, monkeypatch,
):
    db_session.add_all(
        [
            BaseResume(
                slug="analyst",
                data_json=_resume(
                    summary="Older summary",
                    projects=[_project("Orbit", "Built the ingestion pipeline")],
                ),
            ),
            BaseResume(
                slug="data_scientist",
                data_json=_resume(
                    summary="Latest summary",
                    projects=[_project("Orbit", "Built the ingestion pipeline")],
                ),
            ),
        ]
    )
    db_session.commit()
    call_order: list[str] = []

    def fake_llm(*, prompt, model, response_format="json", **kwargs):
        if "group_indices" in prompt:
            call_order.append("entities")
            return {
                "clusters": [
                    {
                        "group_indices": [0],
                        "existing_entity_id": None,
                        "canonical": {
                            "kind": "project",
                            "title": "Orbit",
                            "org": None,
                            "start_date": None,
                            "end_date": None,
                        },
                    }
                ]
            }
        if "bullet_indices" in prompt:
            call_order.append("points")
            return {
                "clusters": [
                    {
                        "bullet_indices": [0],
                        "existing_point_id": None,
                        "merged_text": None,
                    }
                ]
            }
        raise AssertionError("unexpected LLM prompt")

    monkeypatch.setattr(seeding.llm, "get_openai_key", lambda: "configured")
    monkeypatch.setattr(kb_consolidation.llm, "call_openai", fake_llm)

    seeding.seed_career_kb(db_session)

    db_session.expire_all()
    assert call_order == ["entities", "points"]
    assert _count(db_session, KBEntity) == 1
    assert _count(db_session, KBPoint) == 1
    assert db_session.get(KBProfile, 1).summary == "Latest summary"

    # A successful seed is idempotent at startup: the kb.seeded flag prevents a
    # second LLM pass and duplicate points.
    call_order.clear()
    seeding.seed_career_kb(db_session)
    assert call_order == []
    assert _count(db_session, KBEntity) == 1
    assert _count(db_session, KBPoint) == 1


def test_seed_career_kb_zero_entity_source_stays_idempotent(db_session, monkeypatch):
    """A source that yields ZERO entities (no experience/projects/education/
    certs) must still close the guard. The old entity-count guard never closed
    on it, so the whole seed re-ran on every restart; kb.seeded must be set
    regardless of how many entities the seed produced."""
    db_session.add(BaseResume(slug="data_scientist", data_json=_resume(summary="Tailored")))
    db_session.commit()

    def fake_llm(*, prompt, model, response_format="json", **kwargs):
        raise AssertionError(f"unexpected LLM prompt for a zero-entity source: {prompt[:80]}")

    monkeypatch.setattr(seeding.llm, "get_openai_key", lambda: "configured")
    monkeypatch.setattr(kb_consolidation.llm, "call_openai", fake_llm)

    seeding.seed_career_kb(db_session)
    db_session.expire_all()
    assert _count(db_session, KBEntity) == 0
    assert db_session.get(Setting, seeding.KB_SEEDED_FLAG) is not None  # flag closed the guard

    # Next startup: the flag short-circuits before any stage runs.
    seeding.seed_career_kb(db_session)
    db_session.expire_all()
    assert _count(db_session, KBEntity) == 0


def test_seed_career_kb_defers_and_rolls_back_when_a_stage_crashes(
    db_session, monkeypatch,
):
    """A hard seed failure must NOT crash app startup: it rolls back (no
    half-seeded rows), leaves the flag unset (retried next startup), and does
    not re-raise — otherwise a persistent failure would crash-loop the app."""
    db_session.add(BaseResume(slug="data_scientist", data_json=_resume()))
    db_session.commit()

    def crash_consolidate(session, sources, *, commit):
        assert commit is False
        session.add(KBEntity(kind="project", title="Half seeded", detail_json={}))
        session.flush()
        raise RuntimeError("cut off mid-seed")

    monkeypatch.setattr(seeding.llm, "get_openai_key", lambda: "configured")
    monkeypatch.setattr(seeding.kb_consolidation, "consolidate", crash_consolidate)

    # Does NOT raise — startup survives.
    seeding.seed_career_kb(db_session)

    assert _count(db_session, KBEntity) == 0
    assert db_session.get(KBProfile, 1) is None
    assert db_session.get(Setting, seeding.KB_SEEDED_FLAG) is None  # unset -> retried


def test_seed_startup_data_runs_career_seed_last(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(seeding, "seed_base_resumes", lambda session: calls.append("base"))
    monkeypatch.setattr(seeding, "seed_prompts", lambda session: calls.append("prompts"))
    monkeypatch.setattr(seeding, "ensure_persona", lambda session: calls.append("persona"))
    monkeypatch.setattr(seeding, "seed_career_kb", lambda session: calls.append("career"))

    seeding.seed_startup_data(object())

    assert calls == ["base", "prompts", "persona", "career"]
