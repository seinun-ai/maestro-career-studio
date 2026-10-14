"""A job remembers the employer's own apply link beside the board page it was saved from."""

import sqlite3
import uuid
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.models.job import Job
from app.routers import jobs

APPLY = "https://acme.example/careers/apply/1"


def _stub_extraction(monkeypatch):
    monkeypatch.setattr(
        jobs.jd_extraction,
        "extract_jd",
        lambda raw_text, session=None: {"company": "Acme", "title": "Data Engineer", "skills": []},
    )


def test_saving_a_job_keeps_the_employer_apply_link(client, monkeypatch):
    _stub_extraction(monkeypatch)
    body = {"raw_text": "Title: Data Engineer\nCompany: Acme", "source_url": "https://board.example/jobs/1",
            "apply_url": APPLY}

    job = client.post("/api/jobs", json=body).json()

    assert job["apply_url"] == APPLY
    assert job["source_url"] == "https://board.example/jobs/1"
    listed = client.get("/api/jobs").json()
    assert [row["apply_url"] for row in listed] == [APPLY]


def test_a_job_saved_without_one_has_no_apply_link(client, monkeypatch):
    _stub_extraction(monkeypatch)

    job = client.post("/api/jobs", json={"raw_text": "Data Engineer at Acme"}).json()

    assert job["apply_url"] is None


@pytest.mark.parametrize("bad", ["javascript:alert(1)", "data:text/html,x", "ftp://acme.example/a",
                                 "//acme.example/a", "https://", "not a url", "",
                                 "https://acme.example/" + "a" * 2048],
                         ids=["javascript", "data", "ftp", "scheme-relative", "no-host", "words", "empty",
                              "too-long"])
def test_an_apply_link_must_be_http(client, monkeypatch, bad):
    _stub_extraction(monkeypatch)

    response = client.post("/api/jobs", json={"raw_text": "x", "apply_url": bad})

    assert response.status_code == 422


def test_the_ingest_route_takes_the_apply_link_too(client):
    body = {"extracted_json": {"company": "Globex", "title": "Analyst"}, "raw_text": "Analyst at Globex",
            "apply_url": APPLY}

    assert client.post("/api/jobs/ingest", json=body).json()["apply_url"] == APPLY
    body["apply_url"] = "javascript:alert(1)"
    assert client.post("/api/jobs/ingest", json=body).status_code == 422


def test_a_saved_again_job_gains_an_apply_link_it_lacked(client, monkeypatch, db_session):
    _stub_extraction(monkeypatch)
    text = {"raw_text": "Title: Data Engineer\nCompany: Acme"}
    first = client.post("/api/jobs", json=text).json()
    assert first["apply_url"] is None

    again = client.post("/api/jobs", json={**text, "apply_url": APPLY}).json()

    assert again["id"] == first["id"]
    assert again["already_existed"] is True
    assert again["apply_url"] == APPLY
    db_session.expire_all()
    assert db_session.get(Job, uuid.UUID(first["id"])).apply_url == APPLY


def test_a_saved_again_job_never_loses_the_link_it_has(client, monkeypatch):
    _stub_extraction(monkeypatch)
    text = {"raw_text": "Title: Data Engineer\nCompany: Acme"}
    client.post("/api/jobs", json={**text, "apply_url": APPLY})

    other = client.post("/api/jobs", json={**text, "apply_url": "https://elsewhere.example/apply"}).json()
    bare = client.post("/api/jobs", json=text).json()

    assert other["apply_url"] == APPLY
    assert bare["apply_url"] == APPLY


def test_a_saved_again_job_keeps_a_stored_empty_link(client, monkeypatch, db_session):
    """Only NULL is missing: an empty string that arrived another way (sync) is not overwritten."""
    _stub_extraction(monkeypatch)
    text = {"raw_text": "Title: Data Engineer\nCompany: Acme"}
    first = client.post("/api/jobs", json=text).json()
    db_session.get(Job, uuid.UUID(first["id"])).apply_url = ""
    db_session.commit()

    again = client.post("/api/jobs", json={**text, "apply_url": APPLY}).json()

    assert again["apply_url"] == ""


def test_a_requisition_twin_gains_the_link_too(client, monkeypatch):
    """The same requisition from another board has different text, so only the twin rule finds it."""
    extraction = {"company": "Acme", "title": "Data Engineer", "requisition_id": "R-777", "skills": []}
    monkeypatch.setattr(jobs.jd_extraction, "extract_jd", lambda raw_text, session=None: dict(extraction))
    first = client.post("/api/jobs", json={"raw_text": "Acme posting as rendered by a board"}).json()

    again = client.post("/api/jobs", json={"raw_text": "Acme posting as rendered by the careers site",
                                           "apply_url": APPLY}).json()

    assert again["id"] == first["id"] and again["already_existed"] is True
    assert again["apply_url"] == APPLY


def test_an_ingested_duplicate_gains_the_link_too(client):
    body = {"extracted_json": {"company": "Globex", "title": "Analyst"}, "raw_text": "Analyst at Globex"}
    first = client.post("/api/jobs/ingest", json=body).json()

    again = client.post("/api/jobs/ingest", json={**body, "apply_url": APPLY}).json()

    assert (again["id"], again["apply_url"]) == (first["id"], APPLY)


# --- the Companion saves the page it ran on -----------------------------------------

WORKDAY_APPLY = "https://acme.wd5.myworkdayjobs.com/en-US/careers/job/Remote/Data-Scientist_R-1/apply/applyManually"
WORKDAY_POSTING = "https://acme.wd5.myworkdayjobs.com/en-US/careers/job/Remote/Data-Scientist_R-1"


def _board_job(client, monkeypatch, **body):
    _stub_extraction(monkeypatch)
    return client.post("/api/jobs", json={"raw_text": "Data Scientist at Acme",
                                          "source_url": "https://board.example/jobs/1", **body}).json()


def test_a_job_gains_its_apply_link_by_patch(client, monkeypatch):
    job = _board_job(client, monkeypatch)

    response = client.patch(f"/api/jobs/{job['id']}", json={"apply_url": WORKDAY_APPLY})

    assert response.status_code == 200
    assert response.json()["apply_url"] == WORKDAY_APPLY
    assert response.json()["source_url"] == "https://board.example/jobs/1"
    assert client.get(f"/api/jobs/{job['id']}").json()["apply_url"] == WORKDAY_APPLY


def test_a_patch_without_the_link_leaves_it_alone(client, monkeypatch):
    job = _board_job(client, monkeypatch, apply_url=APPLY)

    client.patch(f"/api/jobs/{job['id']}", json={"source_url": "https://board.example/jobs/2"})

    assert client.get(f"/api/jobs/{job['id']}").json()["apply_url"] == APPLY


@pytest.mark.parametrize("bad", ["javascript:alert(1)", "data:text/html,x", "ftp://acme.example/a",
                                 "//acme.example/a", "https://", "not a url", "",
                                 "https://acme.example/" + "a" * 2048],
                         ids=["javascript", "data", "ftp", "scheme-relative", "no-host", "words", "empty",
                              "too-long"])
def test_a_patched_apply_link_must_be_http(client, monkeypatch, bad):
    job = _board_job(client, monkeypatch)

    response = client.patch(f"/api/jobs/{job['id']}", json={"apply_url": bad})

    assert response.status_code == 422
    assert client.get(f"/api/jobs/{job['id']}").json()["apply_url"] is None


def test_the_match_finds_a_job_by_its_apply_link(client, monkeypatch):
    """The page the user applied on is remembered: next time it IS the job, though the saved board
    page is another site."""
    job = _board_job(client, monkeypatch)
    assert client.get("/api/jobs/match", params={"url": WORKDAY_APPLY}).json()["match"] == "none"
    client.patch(f"/api/jobs/{job['id']}", json={"apply_url": WORKDAY_APPLY})

    body = client.get("/api/jobs/match", params={"url": WORKDAY_APPLY}).json()

    assert body["match"] == "exact"
    assert body["job"]["id"] == job["id"]


def test_the_match_reads_the_apply_links_below_a_saved_posting_and_the_wizards_other_steps(client, monkeypatch):
    posting = _board_job(client, monkeypatch, source_url=WORKDAY_POSTING)
    # A saved posting matches the apply page that sits below it (the Workday apply suffix)...
    assert client.get("/api/jobs/match", params={"url": WORKDAY_APPLY}).json()["job"]["id"] == posting["id"]
    # ...and a saved apply link matches the same page with a fragment or a referral query.
    other = _board_job(client, monkeypatch, raw_text="Analyst at Globex", source_url="https://board.example/jobs/9",
                       apply_url=WORKDAY_APPLY.replace("Data-Scientist_R-1", "Analyst_R-9"))
    page = WORKDAY_APPLY.replace("Data-Scientist_R-1", "Analyst_R-9") + "?source=x#step2"
    assert client.get("/api/jobs/match", params={"url": page}).json()["job"]["id"] == other["id"]


def test_a_sibling_posting_is_not_matched_by_an_apply_link(client, monkeypatch):
    job = _board_job(client, monkeypatch, apply_url=WORKDAY_APPLY)

    sibling = WORKDAY_APPLY.replace("Data-Scientist_R-1", "Data-Scientist_R-2")

    assert client.get("/api/jobs/match", params={"url": sibling}).json()["match"] == "none"
    assert job["apply_url"] == WORKDAY_APPLY


# --- the migration --------------------------------------------------------------

def _config(tmp_path):
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{tmp_path / 'jobs.sqlite3'}")
    return cfg


def _columns(path):
    with closing(sqlite3.connect(path)) as db:
        return {r[1] for r in db.execute("PRAGMA table_info(jobs)")}


def test_migration_adds_a_nullable_column_and_downgrade_keeps_the_rows(tmp_path):
    cfg = _config(tmp_path)
    path = tmp_path / "jobs.sqlite3"
    command.upgrade(cfg, "abd275b457d8")
    assert "apply_url" not in _columns(path)
    with closing(sqlite3.connect(path)) as db:
        db.execute("INSERT INTO jobs (id, raw_text, raw_text_hash, source) VALUES ('j1', 'x', 'h1', 'user')")
        db.commit()

    command.upgrade(cfg, "head")

    assert "apply_url" in _columns(path)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT apply_url FROM jobs").fetchall() == [(None,)]

    command.downgrade(cfg, "abd275b457d8")

    assert "apply_url" not in _columns(path)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1
