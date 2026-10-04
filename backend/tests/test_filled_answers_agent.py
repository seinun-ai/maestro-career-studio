"""The agent's half of the receipt (design §1, §2, §5): final review names the flags, and an
EEO answer's value never reaches an agent, consent or not."""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.schemas.eeo_consent import EeoConsent
from app.services import eeo_consent
from tests.test_proposals_models import _mk_job

client = TestClient(app)
ON_SITE_WEEKLY = ("This role requires you to be in the office 4–5 days a week for the 3-month "
                "duration of the internship. Does that work for you?")


@pytest.fixture(autouse=True)
def _settings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)


def _review(db_session):
    eeo_consent.set_consent(EeoConsent(enabled=True), db_session)
    job = _mk_job(db_session, company="Acme", source="agent")
    pid = client.post("/api/proposals", json={"job_id": str(job.id)}).json()["id"]
    res = client.post(f"/api/jobs/{job.id}/filled-answers", json={"channel": "agent", "fields": [
        {"question": ON_SITE_WEEKLY, "answer": "No", "source": "inferred"},
        {"question": "Gender", "answer": "I prefer not to answer", "source": "inferred"},
        {"question": "First name", "answer": "Ada", "source": "profile"},
    ]})
    assert res.status_code == 201
    return {flag["question"]: flag
            for flag in client.get(f"/api/proposals/{pid}/final-review").json()["flags"]}


def test_the_final_review_lists_only_flagged_answers(db_session):
    assert sorted(_review(db_session)) == sorted([ON_SITE_WEEKLY, "Gender"])


def test_a_flagged_answer_reaches_the_agent_with_its_reason(db_session):
    answer = _review(db_session)[ON_SITE_WEEKLY]
    assert (answer["answer"], answer["source"]) == ("No", "inferred")
    assert [flag["id"] for flag in answer["flags"]] == ["guessed_screening"]


def test_an_eeo_answer_reaches_the_agent_without_its_value_even_under_consent(db_session):
    gender = _review(db_session)["Gender"]
    assert "answer" not in gender
    assert (gender["eeo"], gender["eeo_answered"]) == (True, True)


def test_a_review_with_nothing_recorded_has_no_flags(db_session):
    job = _mk_job(db_session, company="Quiet", source="agent")
    pid = client.post("/api/proposals", json={"job_id": str(job.id)}).json()["id"]
    assert client.get(f"/api/proposals/{pid}/final-review").json()["flags"] == []
