"""The stage on the wire: both list shapes and the job detail carry the rung from
services/stage.py, and so does the by-URL match. Row builders are tests/stage_rows.py's."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.schemas.application import ApplicationSummary
from app.schemas.job import JobSummary
from tests.stage_rows import make_application, make_base_score, make_job, make_session


def _app_row(client, application):
    rows = client.get("/api/applications").json()
    return next(r for r in rows if r["id"] == str(application.id))


def _job_row(client, job, query="without_application=true"):
    rows = client.get(f"/api/jobs?{query}").json()
    return next(r for r in rows if r["id"] == str(job.id))


def test_the_application_list_carries_the_stage(client, db_session):
    job = make_job(db_session)
    app = make_application(
        db_session, job, pdf_path="/tmp/x.pdf", customized_json={"summary": "x"}, status="draft"
    )
    row = _app_row(client, app)
    assert row["stage"] == "pdf_ready" and row["has_draft"] and row["has_pdf"]
    assert row["open_session_id"] is None and (row["gaps_done"], row["gaps_total"]) == (0, 0)
    assert "customized_json" not in row


def test_an_application_without_a_draft_says_so(client, db_session):
    job = make_job(db_session)
    app = make_application(db_session, job, status="draft")
    row = _app_row(client, app)
    assert row["stage"] == "saved" and not row["has_draft"] and not row["has_pdf"]


def test_an_application_with_a_newer_open_session_carries_its_counts(client, db_session):
    job = make_job(db_session)
    app = make_application(db_session, job, customized_json={"summary": "x"}, status="draft")
    session = make_session(
        db_session,
        job,
        resolutions=[{"gap_id": "g0"}],
        created_at=datetime.now(UTC) + timedelta(hours=1),
    )
    row = _app_row(client, app)
    assert row["stage"] == "gaps" and row["open_session_id"] == str(session.id)
    assert (row["gaps_done"], row["gaps_total"]) == (1, 5)


def test_the_saved_jobs_list_carries_an_open_session(client, db_session):
    job = make_job(db_session)
    session = make_session(db_session, job, resolutions=[{"gap_id": "g0"}, {"gap_id": "g1"}], n=5)
    row = _job_row(client, job)
    assert row["stage"] == "gaps" and row["open_session_id"] == str(session.id)
    assert (row["gaps_done"], row["gaps_total"]) == (2, 5)


def test_the_saved_jobs_list_tells_scored_from_saved(client, db_session):
    scored, plain = make_job(db_session, 1), make_job(db_session, 2)
    make_base_score(db_session, scored)
    assert _job_row(client, scored)["stage"] == "scored"
    row = _job_row(client, plain)
    assert row["stage"] == "saved" and row["open_session_id"] is None


def test_the_full_jobs_list_reads_each_jobs_newest_application(client, db_session):
    job = make_job(db_session)
    make_application(db_session, job, pdf_path="/tmp/x.pdf", customized_json={"summary": "x"})
    free = make_job(db_session, 2)
    make_base_score(db_session, free)
    assert _job_row(client, job, "without_application=false")["stage"] == "pdf_ready"
    assert _job_row(client, free, "without_application=false")["stage"] == "scored"


def test_the_detail_carries_the_stage(client, db_session):
    job = make_job(db_session)
    body = client.get(f"/api/jobs/{job.id}/detail").json()
    assert body["stage"] == "saved"
    assert (body["open_session_id"], body["gaps_done"], body["gaps_total"]) == (None, 0, 0)


def test_the_detail_carries_an_open_session(client, db_session):
    job = make_job(db_session)
    session = make_session(db_session, job, resolutions=[{"gap_id": "g0"}])
    body = client.get(f"/api/jobs/{job.id}/detail").json()
    assert body["stage"] == "gaps" and body["open_session_id"] == str(session.id)
    assert (body["gaps_done"], body["gaps_total"]) == (1, 5)


def test_the_detail_reads_the_applications_rung(client, db_session):
    job = make_job(db_session)
    make_application(db_session, job, customized_json={"summary": "x"}, status="draft")
    assert client.get(f"/api/jobs/{job.id}/detail").json()["stage"] == "tailored"


def test_the_newer_of_two_applications_decides_the_list_and_the_detail(client, db_session):
    job = make_job(db_session)
    tie = datetime.now(UTC)
    # Same created_at: the higher id is the newer one, in the list and the detail alike.
    make_application(
        db_session,
        job,
        id=UUID(int=1),
        created_at=tie,
        status="draft",
        customized_json={"summary": "x"},
        pdf_path="/tmp/x.pdf",
    )
    make_application(
        db_session,
        job,
        id=UUID(int=2),
        created_at=tie,
        status="draft",
        customized_json={"summary": "y"},
    )
    assert _job_row(client, job, "without_application=false")["stage"] == "tailored"
    body = client.get(f"/api/jobs/{job.id}/detail").json()
    assert body["stage"] == "tailored" and body["application"]["id"] == str(UUID(int=2))


def test_the_match_carries_the_applications_rung_and_pdf(client, db_session):
    job = make_job(db_session)
    job.source_url = "https://jobs.example.com/postings/4242"
    db_session.commit()
    make_application(
        db_session, job, status="draft", customized_json={"summary": "x"}, pdf_path="/tmp/x.pdf"
    )
    body = client.get("/api/jobs/match", params={"url": job.source_url}).json()
    assert body["match"] == "exact"
    assert body["job"]["stage"] == "pdf_ready"
    application = body["application"]
    assert (
        application["stage"] == "pdf_ready" and application["has_pdf"] and application["has_draft"]
    )


def test_an_unstamped_summary_defaults_to_saved(db_session):
    job = make_job(db_session)
    app = make_application(db_session, job)
    assert ApplicationSummary.model_validate(app).stage == "saved"
    summary = JobSummary.model_validate(job)
    assert summary.stage == "saved" and summary.gaps_total == 0
