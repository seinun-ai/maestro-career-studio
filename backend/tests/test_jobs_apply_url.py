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


def test_an_ingested_twin_gains_the_link_too(client):
    body = {"extracted_json": {"company": "Globex", "title": "Analyst"}, "raw_text": "Analyst at Globex"}
    first = client.post("/api/jobs/ingest", json=body).json()

    again = client.post("/api/jobs/ingest", json={**body, "apply_url": APPLY}).json()

    assert (again["id"], again["apply_url"]) == (first["id"], APPLY)


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
