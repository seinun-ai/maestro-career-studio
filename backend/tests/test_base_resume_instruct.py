"""Instruction → proposal on a base resume. Proposes; never writes."""

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.base_resume import BaseResume
from app.models.resume_version import ResumeVersion
from app.services import base_resume_instruct, llm, prompts

RESUME = {
    "contact": {"name": "Jordan Sample", "email": "jordan@example.com"},
    "summary": "Data scientist with a long summary that could be tighter.",
    "skills": [{"category": "Core", "items": ["Python", "SQL"]}],
    "experience": [
        {"company": "Acme", "role": "Data Scientist", "start_date": "2021-03",
         "enabled": True,
         "bullets": ["Built churn models.", "Maintained Airflow pipelines."]}
    ],
    "projects": [],
    "education": [],
    "certifications": [],
    "extra_sections": [],
}


@pytest.fixture
def row(db_session):
    r = BaseResume(slug="ds", display_name="DS", data_json=RESUME)
    db_session.add(r)
    db_session.commit()
    return r


@pytest.fixture
def client(db_session, monkeypatch, tmp_path):
    from app.routers import base_resumes as router_module
    monkeypatch.setattr(router_module.base_resume_data.settings, "base_resumes_dir", tmp_path)
    monkeypatch.setattr(router_module.base_resume_render, "render_base_resume", lambda slug, db, **kw: None)
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _llm(*payloads):
    """A fake that answers each call with the next payload and records prompts."""
    queue = list(payloads)
    calls = []

    def fake(*, prompt, model, response_format="json", **kw):
        calls.append(prompt)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    fake.calls = calls
    return fake


GOOD = {
    "summary": "Tightens the summary.",
    "notes": "",
    "ops": [{"kind": "replace_summary", "value": "Data scientist."}],
}


def test_a_valid_proposal_is_validated_and_dry_run(db_session, row, monkeypatch):
    fake = _llm(GOOD)
    monkeypatch.setattr(llm, "call_openai", fake)
    out = base_resume_instruct.propose(db_session, row, "tighten the summary")
    assert out.summary == "Tightens the summary."
    assert [op.kind for op in out.ops] == ["replace_summary"]
    assert len(fake.calls) == 1
    prompt = fake.calls[0]
    assert "tighten the summary" in prompt
    assert "Built churn models." in prompt          # the document is in the prompt
    assert '"kind":"replace_bullet"' in prompt        # …and the op vocabulary
    assert "$op_shapes" not in prompt and "$resume_json" not in prompt


def test_ideas_only_answers_in_notes_with_no_ops(db_session, row, monkeypatch):
    monkeypatch.setattr(llm, "call_openai", _llm({
        "summary": "Pivot ideas.",
        "notes": "Analytics engineering fits: the Airflow work is evidence; add dbt.",
        "ops": [],
    }))
    out = base_resume_instruct.propose(db_session, row, "what could this pivot to?")
    assert out.ops == []
    assert "Airflow" in out.notes


def test_ops_that_do_not_apply_get_one_correction_then_422(db_session, row, monkeypatch):
    """Index 7 is out of range: the validator's message goes back to the model
    once; a second bad answer is refused rather than shown to the user."""
    bad = {"summary": "x", "notes": "", "ops": [
        {"kind": "replace_bullet", "section": "experience", "index": 7,
         "bullet_index": 0, "value": "y"}]}
    fake = _llm(bad, GOOD)
    monkeypatch.setattr(llm, "call_openai", fake)
    out = base_resume_instruct.propose(db_session, row, "reword")
    assert [op.kind for op in out.ops] == ["replace_summary"]
    assert len(fake.calls) == 2
    assert "did not apply" in fake.calls[1]

    fake = _llm(bad, bad)
    monkeypatch.setattr(llm, "call_openai", fake)
    with pytest.raises(ValueError, match="could not produce"):
        base_resume_instruct.propose(db_session, row, "reword")


def test_an_unknown_op_kind_is_a_schema_failure_not_a_crash(db_session, row, monkeypatch):
    monkeypatch.setattr(llm, "call_openai", _llm(
        {"summary": "", "notes": "", "ops": [{"kind": "rewrite_everything"}]}))
    with pytest.raises(ValueError, match="invalid ops"):
        base_resume_instruct.propose(db_session, row, "x")


def test_empty_and_oversized_instructions_are_refused_before_any_call(db_session, row, monkeypatch):
    def never(**kw):
        raise AssertionError("no LLM call expected")
    monkeypatch.setattr(llm, "call_openai", never)
    with pytest.raises(ValueError):
        base_resume_instruct.propose(db_session, row, "   ")
    with pytest.raises(ValueError):
        base_resume_instruct.propose(db_session, row, "x" * 5000)


def test_the_endpoint_persists_nothing(client, db_session, row, monkeypatch):
    monkeypatch.setattr(llm, "call_openai", _llm(GOOD))
    r = client.post("/api/base-resumes/ds/propose", json={"instruction": "tighten the summary"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ops_count"] == 1
    assert body["ops"][0]["kind"] == "replace_summary"
    assert body["summary"] == "Tightens the summary."
    db_session.refresh(row)
    assert row.data_json["summary"].startswith("Data scientist with a long")
    assert db_session.query(ResumeVersion).count() == 0
    # …and the ops it returned apply through the ordinary door.
    applied = client.patch("/api/base-resumes/ds/edits", json={"ops": body["ops"]})
    assert applied.status_code == 200, applied.text
    assert applied.json()["data"]["summary"] == "Data scientist."


def test_endpoint_error_mapping(client, row, monkeypatch):
    assert client.post("/api/base-resumes/nope/propose", json={"instruction": "x"}).status_code == 404
    assert client.post("/api/base-resumes/ds/propose", json={"instruction": " "}).status_code == 422

    def down(**kw):
        raise TimeoutError("boom")
    monkeypatch.setattr(llm, "call_openai", down)
    assert client.post("/api/base-resumes/ds/propose", json={"instruction": "x"}).status_code == 502


def test_the_prompt_is_registered_and_forbids_fabrication():
    assert "base_resume_instruct" in prompts.VALID_PROMPTS
    text = (prompts.PROMPT_DIR / "base_resume_instruct.txt").read_text(encoding="utf-8")
    assert "NEVER fabricate" in text
    assert "$op_shapes" in text and "$resume_json" in text and "$instruction" in text
