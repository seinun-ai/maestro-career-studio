"""Agent and model text never stores a third-person line (§6 inv-resume-voice).

The rule held for tailor_session ops and kb_add_points only. A connected agent's
edit_application, tailor_application, edit_base_resume and kb_edit_point, and the
Assistant's edit tool, stored lines like "She grew her team." A write carrying the
MCP origin header is the agent's text, so it is refused with the lines named; the
web studio's own saves send no origin and keep the owner's text as written.
"""

import copy
from datetime import UTC, datetime

from app.models.application import Application
from app.models.base_resume import BaseResume
from app.models.career_kb import KBEntity, KBPoint
from app.models.job import Job
from app.routers import applications
from app.services import base_resume_render, resume_ops
from app.services.chat_tools import ToolContext, ToolError, tool_edit_resume

MCP = {"X-Maestro-CS-Origin": "mcp", "X-Maestro-CS-Origin-Detail": "test-agent"}
THIRD_PERSON = "She led her team of five analysts."
REFUSED = "written about someone else"

BASE = {
    "contact": {"name": "Riley Quill", "email": "riley@example.com"},
    "summary": "Base summary.",
    "skills": [],
    "experience": [
        {"company": "Acme", "role": "Analyst", "start_date": "2021", "enabled": True,
         "bullets": ["Built the weekly carrier report."]},
    ],
    "projects": [],
    "education": [],
    "certifications": [],
}
SUMMARY_OP = [{"kind": "replace_summary", "value": THIRD_PERSON}]


def _job(db_session):
    job = Job(
        raw_text="Need SQL", raw_text_hash="agent-write-voice",
        extracted_json={"title": "Analyst", "company": "Acme"}, title="Analyst",
        company="Acme", role_category="data_analyst", extracted_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def _stub_base(monkeypatch):
    monkeypatch.setattr(
        applications.base_resume_data, "load_base_resume",
        lambda slug, session=None: copy.deepcopy(BASE),
    )


def _stub_render(monkeypatch, tmp_path):
    monkeypatch.setattr(base_resume_render, "render_base_resume", lambda *a, **k: None)
    monkeypatch.setattr(resume_ops.base_resume_render, "render_base_resume", lambda *a, **k: None)
    monkeypatch.setattr(resume_ops.settings, "base_resumes_dir", tmp_path)


def _application(client, db_session, monkeypatch):
    _stub_base(monkeypatch)
    job = _job(db_session)
    created = client.post(
        "/api/applications/from-base",
        json={"job_id": str(job.id), "base_resume": "analyst", "ops": []},
    )
    assert created.status_code == 200, created.text
    return job, created.json()["id"]


def test_an_agent_edit_to_an_application_refuses_a_third_person_line(client, db_session, monkeypatch):
    _, app_id = _application(client, db_session, monkeypatch)
    refused = client.patch(f"/api/applications/{app_id}/edits", json={"ops": SUMMARY_OP}, headers=MCP)
    assert refused.status_code == 400
    assert REFUSED in refused.json()["detail"]
    assert THIRD_PERSON in refused.json()["detail"]
    detail = client.get(f"/api/applications/{app_id}").json()
    assert detail["customized_json"]["summary"] == "Base summary."


def test_the_web_studio_still_saves_the_owner_text_as_written(client, db_session, monkeypatch):
    _, app_id = _application(client, db_session, monkeypatch)
    saved = client.patch(f"/api/applications/{app_id}/edits", json={"ops": SUMMARY_OP})
    assert saved.status_code == 200
    assert saved.json()["customized_json"]["summary"] == THIRD_PERSON


def test_an_agent_rebuild_from_the_base_refuses_a_third_person_line(client, db_session, monkeypatch):
    _stub_base(monkeypatch)
    job = _job(db_session)
    refused = client.post(
        "/api/applications/from-base",
        json={"job_id": str(job.id), "base_resume": "analyst", "ops": SUMMARY_OP},
        headers=MCP,
    )
    assert refused.status_code == 400
    assert REFUSED in refused.json()["detail"]
    assert db_session.query(Application).filter_by(job_id=job.id).count() == 0


def test_an_agent_edit_to_a_base_refuses_a_third_person_line(client, db_session, monkeypatch, tmp_path):
    _stub_render(monkeypatch, tmp_path)
    db_session.add(BaseResume(slug="analyst", display_name="Analyst", data_json=copy.deepcopy(BASE)))
    db_session.commit()
    refused = client.patch("/api/base-resumes/analyst/edits", json={"ops": SUMMARY_OP}, headers=MCP)
    assert refused.status_code == 400
    assert REFUSED in refused.json()["detail"]
    db_session.expire_all()
    assert db_session.get(BaseResume, "analyst").data_json["summary"] == "Base summary."


def _point(db_session, text="Built the weekly carrier report."):
    entity = KBEntity(kind="experience", title="Analyst", org="Acme", origin="manual")
    db_session.add(entity)
    db_session.flush()
    point = KBPoint(entity_id=entity.id, text=text, state="approved", origin="manual")
    db_session.add(point)
    db_session.commit()
    return point


def test_an_agent_rewording_of_a_career_point_refuses_a_third_person_line(client, db_session):
    point = _point(db_session)
    refused = client.patch(
        f"/api/kb/points/{point.id}", json={"text": THIRD_PERSON}, headers=MCP
    )
    assert refused.status_code == 400
    assert REFUSED in refused.json()["detail"]
    db_session.expire_all()
    assert db_session.get(KBPoint, point.id).text == "Built the weekly carrier report."


def test_an_agent_rewording_of_a_career_point_loses_its_em_dash(client, db_session):
    point = _point(db_session)
    saved = client.patch(
        f"/api/kb/points/{point.id}", json={"text": "Built a dashboard — fast."}, headers=MCP
    )
    assert saved.status_code == 200
    assert "—" not in saved.json()["text"]


def test_the_assistant_edit_tool_refuses_a_third_person_line(db_session, monkeypatch, tmp_path):
    _stub_render(monkeypatch, tmp_path)
    db_session.add(BaseResume(slug="analyst", display_name="Analyst", data_json=copy.deepcopy(BASE)))
    db_session.commit()
    ctx = ToolContext(db=db_session, message_id="msg-voice")
    try:
        tool_edit_resume(ctx, "base", "analyst", SUMMARY_OP)
    except ToolError as exc:
        assert REFUSED in str(exc)
    else:
        raise AssertionError("the Assistant stored a third-person line")
    db_session.expire_all()
    assert db_session.get(BaseResume, "analyst").data_json["summary"] == "Base summary."


def test_an_agent_whole_replace_of_a_base_refuses_a_third_person_line(client, db_session, monkeypatch, tmp_path):
    _stub_render(monkeypatch, tmp_path)
    db_session.add(BaseResume(slug="analyst", display_name="Analyst", data_json=copy.deepcopy(BASE)))
    db_session.commit()
    replaced = {**copy.deepcopy(BASE), "summary": THIRD_PERSON}
    refused = client.put("/api/base-resumes/analyst", json={"data": replaced}, headers=MCP)
    assert refused.status_code == 400
    assert REFUSED in refused.json()["detail"]
    db_session.expire_all()
    assert db_session.get(BaseResume, "analyst").data_json["summary"] == "Base summary."
    saved = client.put("/api/base-resumes/analyst", json={"data": replaced})
    assert saved.status_code == 200, saved.text


def test_removing_a_bullet_never_blames_the_owner_line_that_moves_up(client, db_session, monkeypatch, tmp_path):
    """changed_hits compares by position, so the owner's own line that moves up a
    slot read as the agent's text and the agent could not delete the bullet above it."""
    _stub_render(monkeypatch, tmp_path)
    owner_line = "Riley rebuilt the pricing model for the team."
    data = copy.deepcopy(BASE)
    data["experience"][0]["bullets"] = ["Built the weekly carrier report.", owner_line]
    db_session.add(BaseResume(slug="analyst", display_name="Analyst", data_json=data))
    db_session.commit()
    op = [{"kind": "remove_bullet", "section": "experience", "index": 0, "bullet_index": 0}]
    removed = client.patch("/api/base-resumes/analyst/edits", json={"ops": op}, headers=MCP)
    assert removed.status_code == 200, removed.text
    assert removed.json()["data"]["experience"][0]["bullets"] == [owner_line]


def test_a_retag_that_resends_unchanged_text_is_not_refused(client, db_session):
    point = _point(db_session, text=THIRD_PERSON)  # the owner's own words, saved from the web
    retagged = client.patch(
        f"/api/kb/points/{point.id}", json={"text": THIRD_PERSON, "tags": ["leadership"]}, headers=MCP
    )
    assert retagged.status_code == 200, retagged.text
    assert retagged.json()["tags"] == ["leadership"]
