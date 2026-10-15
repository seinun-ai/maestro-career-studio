"""A job saved on an employer's page remembers the job board the user came from (Built In, say), so "How did you hear
about us?" can name it: the extension asks /api/jobs/match for each page it opens, and the board page is among them."""

from uuid import UUID

import pytest

from app.models.job import Job
from app.routers import autofill as autofill_router
from app.routers import jobs
from app.services import autofill_job, autofill_step, board_visits

BOARD_PAGE = "https://builtin.com/job/data-engineer/1"
ATS_PAGE = "https://acme.wd1.myworkdayjobs.com/en-US/careers/job/Remote/Data-Engineer_R-1"
BODY = {"raw_text": "Title: Data Engineer\nCompany: Acme", "source_url": ATS_PAGE}


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    board_visits.forget()
    monkeypatch.setattr(jobs.jd_extraction, "extract_jd",
                        lambda raw_text, session=None: {"company": "Acme", "title": "Data Engineer", "skills": []})
    yield
    board_visits.forget()


def _saved(db_session, job_id):
    db_session.expire_all()
    return db_session.get(Job, UUID(job_id))


def test_a_job_saved_on_the_employers_page_after_a_board_page_remembers_the_board(client, db_session):
    assert client.get("/api/jobs/match", params={"url": BOARD_PAGE}).json()["match"] == "none"
    assert client.get("/api/jobs/match", params={"url": ATS_PAGE}).json()["match"] == "none"
    job = client.post("/api/jobs", json=BODY).json()
    assert _saved(db_session, job["id"]).referrer_board == "Built In"


def test_with_no_board_page_seen_the_job_has_no_referrer_board(client, db_session):
    client.get("/api/jobs/match", params={"url": ATS_PAGE})
    job = client.post("/api/jobs", json=BODY).json()
    assert _saved(db_session, job["id"]).referrer_board is None


def test_a_job_saved_from_a_board_page_has_the_board_in_its_url_not_a_referrer(client, db_session):
    client.get("/api/jobs/match", params={"url": "https://www.indeed.com/viewjob?jk=1"})
    job = client.post("/api/jobs", json={**BODY, "source_url": BOARD_PAGE}).json()
    assert _saved(db_session, job["id"]).referrer_board is None


def test_a_board_page_seen_long_ago_is_forgotten(client, db_session, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(board_visits.time, "monotonic", lambda: now[0])
    client.get("/api/jobs/match", params={"url": BOARD_PAGE})
    now[0] += board_visits.TTL_S + 1
    job = client.post("/api/jobs", json=BODY).json()
    assert _saved(db_session, job["id"]).referrer_board is None


def test_the_latest_board_page_wins(client, db_session):
    client.get("/api/jobs/match", params={"url": BOARD_PAGE})
    client.get("/api/jobs/match", params={"url": "https://uk.linkedin.com/jobs/view/9"})
    job = client.post("/api/jobs", json=BODY).json()
    assert _saved(db_session, job["id"]).referrer_board == "LinkedIn"


def test_a_job_saved_again_keeps_the_board_it_had(client, db_session):
    client.get("/api/jobs/match", params={"url": BOARD_PAGE})
    first = client.post("/api/jobs", json=BODY).json()
    client.get("/api/jobs/match", params={"url": "https://www.indeed.com/viewjob?jk=1"})
    again = client.post("/api/jobs", json=BODY).json()
    assert again["id"] == first["id"] and _saved(db_session, first["id"]).referrer_board == "Built In"


def test_a_blank_or_unparseable_match_url_records_nothing(client):
    client.get("/api/jobs/match", params={"url": ""})
    client.get("/api/jobs/match", params={"url": "not a url"})
    assert board_visits.recent() is None


def _hint(db_session, job, source_hint=None):
    from app.models.application import Application

    application = Application(job_id=job.id, base_resume="base", status="draft")
    db_session.add(application)
    db_session.commit()
    return autofill_router._job_hint(db_session, application.id, source_hint)


def test_the_referrer_board_feeds_the_how_heard_board(client, db_session):
    client.get("/api/jobs/match", params={"url": BOARD_PAGE})
    job = _saved(db_session, client.post("/api/jobs", json=BODY).json()["id"])
    hint = _hint(db_session, job)
    assert autofill_step.board_of("Job board", hint) == "Built In"


def test_the_pages_own_source_and_a_board_in_the_url_come_before_the_referrer(client, db_session):
    client.get("/api/jobs/match", params={"url": BOARD_PAGE})
    job = _saved(db_session, client.post("/api/jobs", json=BODY).json()["id"])
    assert autofill_step.board_of("Job board", _hint(db_session, job, "rec_linkedin")) == "LinkedIn"
    job.source_url = "https://www.indeed.com/viewjob?jk=1"
    db_session.commit()
    assert autofill_step.board_of("Job board", _hint(db_session, job)) == "Indeed"


def test_the_board_names_the_registry_knows_are_what_gets_stored(client):
    for url, name in [(BOARD_PAGE, "Built In"), ("https://www.glassdoor.com/job/1", "Glassdoor")]:
        board_visits.forget()
        client.get("/api/jobs/match", params={"url": url})
        assert board_visits.recent() == name and name in autofill_job.BOARD_NAMES
