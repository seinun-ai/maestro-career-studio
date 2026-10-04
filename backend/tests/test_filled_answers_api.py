"""The answer receipt over HTTP (docs/entities/filled-answers.md)."""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.application import Application
from app.models.filled_answer import FilledAnswer
from app.schemas.eeo_consent import EeoConsent
from app.services import application_writes, autofill_profile, eeo_consent
from tests.test_proposals_models import _mk_job

client = TestClient(app)

ON_SITE_WEEKLY = ("This role requires you to be in the office 4–5 days a week for the 3-month "
                "duration of the internship. Does that work for you?")


@pytest.fixture(autouse=True)
def _settings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)


def _post(job, fields, **body):
    return client.post(f"/api/jobs/{job.id}/filled-answers",
                       json={"channel": "companion", "fields": fields, **body})


def _f(question, answer, source="profile", **extra):
    return {"question": question, "answer": answer, "source": source, **extra}


def _fields(body):
    return [field for step in body["steps"] for section in step["sections"]
            for field in section["fields"]]


def test_a_post_answers_the_runs_flags_by_position(db_session):
    job = _mk_job(db_session, company="Acme", source_url="https://jobs.ashbyhq.com/acme/1")
    res = _post(job, [_f("First name", "Ada"), _f(ON_SITE_WEEKLY, "No", "inferred")])
    assert res.status_code == 201
    body = res.json()
    assert body["flag_count"] == 1
    assert body["flags"] == [{"index": 1, "question": ON_SITE_WEEKLY, "section": None, "flags": [
        {"id": "guessed_screening", "reason": "A screening question with no saved answer behind it."}]}]
    assert db_session.get(FilledAnswer, UUID(body["id"])).host == "jobs.ashbyhq.com"


def test_the_receipt_keeps_the_latest_answer_per_question(db_session):
    job = _mk_job(db_session, company="Acme")
    _post(job, [_f(ON_SITE_WEEKLY, "No", "inferred"), _f("First name", "Ada")], step="/apply")
    _post(job, [_f(ON_SITE_WEEKLY, "Yes", "you")], step="/apply")
    body = client.get(f"/api/jobs/{job.id}/filled-answers").json()
    answers = {field["question"]: (field["answer"], field["source"]) for field in _fields(body)}
    assert answers == {ON_SITE_WEEKLY: ("Yes", "you"), "First name": ("Ada", "profile")}
    assert (body["pages"], body["flag_count"]) == (1, 0)


def test_the_receipt_groups_by_step_in_the_order_the_pages_came(db_session):
    job = _mk_job(db_session, company="Globex")
    _post(job, [_f("First name", "Ada", section="Personal")], step="/apply/1")
    _post(job, [_f("Which cohorts?", ["A", "B", "C"], "inferred", options_count=3)], step="/apply/2")
    body = client.get(f"/api/jobs/{job.id}/filled-answers").json()
    assert [step["step"] for step in body["steps"]] == ["/apply/1", "/apply/2"]
    assert body["steps"][0]["sections"][0]["section"] == "Personal"
    assert body["steps"][1]["sections"][0]["fields"][0]["flags"][0]["id"] == "ticked_everything"


def test_a_job_with_nothing_filled_reads_empty(db_session):
    job = _mk_job(db_session)
    assert client.get(f"/api/jobs/{job.id}/filled-answers").json()["steps"] == []


@pytest.mark.parametrize(("method", "path"), [("get", "filled-answers"), ("post", "filled-answers")])
def test_an_unknown_job_is_a_404(method, path):
    res = getattr(client, method)(f"/api/jobs/00000000-0000-0000-0000-000000000000/{path}",
                                  **({"json": {"channel": "agent", "fields": [_f("Q", "A")]}}
                                     if method == "post" else {}))
    assert res.status_code == 404


def test_an_application_of_another_job_is_refused(db_session):
    job, other = _mk_job(db_session), _mk_job(db_session)
    app_row = Application(job_id=other.id, base_resume="hybrid")
    db_session.add(app_row)
    db_session.commit()
    res = _post(job, [_f("First name", "Ada")], application_id=str(app_row.id))
    assert res.status_code == 400


def test_an_eeo_answer_without_consent_keeps_only_the_question(db_session):
    job = _mk_job(db_session)
    _post(job, [_f("Gender", "I prefer not to answer", "inferred")])
    [field] = _fields(client.get(f"/api/jobs/{job.id}/filled-answers").json())
    assert (field["eeo"], field["answer"], field["eeo_answered"]) == (True, None, True)
    assert [flag["id"] for flag in field["flags"]] == ["eeo_without_saved_answer"]


def test_an_eeo_answer_under_consent_is_kept(db_session):
    eeo_consent.set_consent(EeoConsent(enabled=True), db_session)
    autofill_profile.set_profile({"eeo": {"gender": "female"}}, db_session)
    job = _mk_job(db_session)
    _post(job, [_f("Gender", "Female", eeo=True, slot="eeo.gender")])
    [field] = _fields(client.get(f"/api/jobs/{job.id}/filled-answers").json())
    assert (field["answer"], field["flags"]) == ("Female", [])


def test_a_resume_upload_is_stamped_with_the_applications_version(db_session):
    job = _mk_job(db_session)
    app_row = Application(job_id=job.id, base_resume="hybrid")
    db_session.add(app_row)
    db_session.flush()
    application_writes.stage_resume_update(db_session, app_row, {"contact": {}}, source="import")
    db_session.commit()
    _post(job, [_f("Resume", "ada-resume.pdf", "upload", slot="resume")],
          application_id=str(app_row.id))
    [field] = _fields(client.get(f"/api/jobs/{job.id}/filled-answers").json())
    assert field["version"] == 1


def test_the_job_detail_says_whether_anything_was_filled(db_session):
    job = _mk_job(db_session)
    assert client.get(f"/api/jobs/{job.id}/detail").json()["has_filled_answers"] is False
    _post(job, [_f("First name", "Ada")])
    assert client.get(f"/api/jobs/{job.id}/detail").json()["has_filled_answers"] is True
