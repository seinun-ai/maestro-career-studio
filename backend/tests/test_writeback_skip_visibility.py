"""Task 11 (Phase C): flywheel silent drops become visible.

Every substantive gap answer the KB write-back skips (too short / wrong
section / no entity-title match / duplicate) is returned through the tailor
response as `kb_writeback_skips`, instead of vanishing into a backend log.
"""
import json

from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_db
from app.main import app
from app.models.base_resume import BaseResume
from app.models.career_kb import KBEntity, KBPoint
from app.models.job import Job
from app.models.tailoring_session import TailoringSession
from app.services import tailoring_session
from tests.ats.fixtures import SAMPLE_JD, SAMPLE_RESUME

_LONG_ANSWER = (
    "Tuned Kafka consumer groups to cut end-to-end event latency from 9s to 2s "
    "across three ingestion topics"
)


def _open_session(db_session, tmp_path, monkeypatch):
    resume = json.loads(json.dumps(SAMPLE_RESUME))
    resume["projects"] = [
        {"name": "", "enabled": True, "bullets": ["Untitled work"], "tech": ""},
        {
            "name": "Churn Model",
            "enabled": True,
            "bullets": ["Trained XGBoost model"],
            "tech": "",
        },
    ]
    job = Job(raw_text="jd", raw_text_hash="wb-hash", extracted_json=SAMPLE_JD)
    db_session.add(job)
    db_session.commit()
    monkeypatch.setattr(settings, "base_resumes_dir", tmp_path)
    slug = "wb_base"
    (tmp_path / f"{slug}.json").write_text(json.dumps(resume))
    db_session.add(BaseResume(slug=slug, data_json=resume))
    db_session.commit()
    gaps = [
        {
            "gap_id": "skill:kafka",
            "kind": "skill",
            "jd_skill": "Kafka",
            "diagnostic": {"fix_hint": "absent"},
            "actions": ["add_keyword", "user_input", "skip"],
        },
    ]
    tailoring = TailoringSession(
        job_id=job.id,
        base_resume=slug,
        status="open",
        gaps_json={"categories": [{"key": "missing_skills", "gaps": gaps}]},
        resolutions_json=[],
    )
    db_session.add(tailoring)
    db_session.commit()
    db_session.refresh(tailoring)
    return tailoring


def _tailor_with_answer(db_session, tailoring, monkeypatch, payload):
    tailoring_session.save_resolutions(
        tailoring.id,
        [{"gap_id": "skill:kafka", "action": "user_input", "payload": payload}],
        session=db_session,
    )
    monkeypatch.setattr(
        tailoring_session.llm, "call_openai", lambda **kwargs: {"ops": []}
    )

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    try:
        client = TestClient(app)
        response = client.post(f"/api/tailoring-sessions/{tailoring.id}/tailor")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    return response.json()


def test_too_short_answer_skip_is_reported(db_session, tmp_path, monkeypatch):
    tailoring = _open_session(db_session, tmp_path, monkeypatch)
    body = _tailor_with_answer(
        db_session,
        tailoring,
        monkeypatch,
        {
            "text": "Used it once.",
            "placement_target": {"section": "projects", "index_or_category": 1},
        },
    )
    skips = body["kb_writeback_skips"]
    assert len(skips) == 1
    assert skips[0]["gap_id"] == "skill:kafka"
    assert skips[0]["skill"] == "Kafka"
    assert skips[0]["reason"] == "too_short"
    assert "too short" in skips[0]["detail"]


def test_unattached_answer_skip_is_reported(db_session, tmp_path, monkeypatch):
    tailoring = _open_session(db_session, tmp_path, monkeypatch)
    body = _tailor_with_answer(
        db_session, tailoring, monkeypatch, {"text": _LONG_ANSWER}
    )
    skips = body["kb_writeback_skips"]
    assert len(skips) == 1
    assert skips[0]["reason"] == "wrong_section"
    assert "experience or project entry" in skips[0]["detail"]


def test_no_entity_match_skip_is_reported(db_session, tmp_path, monkeypatch):
    tailoring = _open_session(db_session, tmp_path, monkeypatch)
    # No KB entity titled "Churn Model" exists.
    body = _tailor_with_answer(
        db_session,
        tailoring,
        monkeypatch,
        {
            "text": _LONG_ANSWER,
            "placement_target": {"section": "projects", "index_or_category": 1},
        },
    )
    skips = body["kb_writeback_skips"]
    assert len(skips) == 1
    assert skips[0]["reason"] == "no_entity_match"
    assert "Churn Model" in skips[0]["detail"]


def test_untitled_entry_skip_is_reported(db_session, tmp_path, monkeypatch):
    tailoring = _open_session(db_session, tmp_path, monkeypatch)
    body = _tailor_with_answer(
        db_session,
        tailoring,
        monkeypatch,
        {
            "text": _LONG_ANSWER,
            "placement_target": {"section": "projects", "index_or_category": 0},
        },
    )
    skips = body["kb_writeback_skips"]
    assert len(skips) == 1
    assert skips[0]["reason"] == "no_entity_match"


def test_duplicate_answer_skip_is_reported(db_session, tmp_path, monkeypatch):
    tailoring = _open_session(db_session, tmp_path, monkeypatch)
    entity = KBEntity(kind="project", title="Churn Model", status="completed")
    db_session.add(entity)
    db_session.flush()
    db_session.add(
        KBPoint(
            entity_id=entity.id, text=_LONG_ANSWER, state="approved", origin="manual"
        )
    )
    db_session.commit()
    body = _tailor_with_answer(
        db_session,
        tailoring,
        monkeypatch,
        {
            # Case tweak → cosine ~1.0 duplicate.
            "text": _LONG_ANSWER.upper(),
            "placement_target": {"section": "projects", "index_or_category": 1},
        },
    )
    skips = body["kb_writeback_skips"]
    assert len(skips) == 1
    assert skips[0]["reason"] == "duplicate"
    assert "already" in skips[0]["detail"]


def test_successful_writeback_reports_no_skips(db_session, tmp_path, monkeypatch):
    tailoring = _open_session(db_session, tmp_path, monkeypatch)
    entity = KBEntity(kind="project", title="Churn Model", status="completed")
    db_session.add(entity)
    db_session.commit()
    body = _tailor_with_answer(
        db_session,
        tailoring,
        monkeypatch,
        {
            "text": _LONG_ANSWER,
            "placement_target": {"section": "projects", "index_or_category": 1},
        },
    )
    assert body["kb_writeback_skips"] == []
