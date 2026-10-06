"""The job-site login: a local file, never the DB, never sent back to the web app."""

import logging
import os
import stat

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.main import app
from app.services import job_site_login

client = TestClient(app)
SECRET = "synthetic-job-site-password"


@pytest.fixture(autouse=True)
def _settings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)


def test_the_password_is_stored_0600_and_never_returned():
    put = client.put("/api/settings/job-site-login",
                     json={"email": "ada@example.com", "password": "s3cret-pass"})
    assert put.status_code == 200 and "s3cret-pass" not in put.text
    body = client.get("/api/settings/job-site-login").json()
    assert body == {"email": "ada@example.com", "password_set": True}
    path = job_site_login.path()
    assert path == settings.settings_dir / "secrets" / "job-site-login.json"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(path.parent).st_mode) == 0o700


def test_an_email_change_keeps_the_password():
    client.put("/api/settings/job-site-login", json={"email": "a@x.com", "password": "pw-one-long"})
    client.put("/api/settings/job-site-login", json={"email": "b@x.com"})
    assert job_site_login.read() == ("b@x.com", "pw-one-long")


def test_delete_clears_both():
    client.put("/api/settings/job-site-login", json={"email": "a@x.com", "password": "pw-one-long"})
    assert client.delete("/api/settings/job-site-login").status_code == 204
    assert client.get("/api/settings/job-site-login").json() == {"email": None, "password_set": False}
    assert not job_site_login.path().exists()


@pytest.mark.parametrize("bad", ["short7!", "x" * 201])
def test_a_bad_password_is_refused_without_echoing_it(bad):
    put = client.put("/api/settings/job-site-login", json={"email": "a@x.com", "password": bad})
    assert put.status_code == 422 and bad not in put.text
    assert "input" not in str(put.json()["detail"])
    assert not job_site_login.path().exists()


def test_nothing_is_stored_in_the_database(db_session):
    from app.models.setting import Setting
    client.put("/api/settings/job-site-login", json={"email": "a@x.com", "password": "pw-one-long"})
    assert not any("pw-one-long" in (row.value or "") for row in db_session.query(Setting).all())


@pytest.mark.parametrize("length", [8, 200])
def test_password_length_boundaries_are_accepted(length):
    password = "p" * length
    response = client.put("/api/settings/job-site-login", json={"password": password})
    assert response.status_code == 200
    assert response.json() == {"email": None, "password_set": True}
    assert password not in response.text
    assert job_site_login.read() == (None, password)


def test_invalid_password_does_not_replace_the_saved_login():
    saved = client.put("/api/settings/job-site-login",
                       json={"email": "ada@example.com", "password": SECRET})
    assert saved.status_code == 200
    refused = client.put("/api/settings/job-site-login",
                         json={"email": "other@example.com", "password": "short"})
    assert refused.status_code == 422
    assert job_site_login.read() == ("ada@example.com", SECRET)


def test_a_stale_temporary_file_cannot_weaken_password_permissions():
    target = job_site_login.path()
    target.parent.mkdir(mode=0o700, parents=True)
    stale = target.with_suffix(".tmp")
    stale.write_text("interrupted write", encoding="utf-8")
    stale.chmod(0o644)
    response = client.put("/api/settings/job-site-login", json={"password": SECRET})
    assert response.status_code == 200
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


@pytest.mark.parametrize("payload", [
    [{"email": "ada@example.com", "password": SECRET}],
    {"email": "ada@example.com", "password": [SECRET]},
    {"email": "ada@example.com", "password": {"value": SECRET}},
    {"email": {"value": SECRET}, "password": SECRET},
    {"email": "ada@example.com", "password": SECRET, "confirmation": SECRET},
])
def test_schema_errors_never_echo_the_password(payload):
    response = client.put("/api/settings/job-site-login", json=payload)
    assert response.status_code == 422
    assert SECRET not in response.text
    assert "input" not in str(response.json()["detail"])
    assert not job_site_login.path().exists()


def test_login_requests_never_log_the_password(caplog):
    with caplog.at_level(logging.DEBUG):
        responses = [
            client.put("/api/settings/job-site-login",
                       json={"email": "ada@example.com", "password": SECRET}),
            client.get("/api/settings/job-site-login"),
            client.put("/api/settings/job-site-login", json={"password": "short7!"}),
            client.put("/api/settings/job-site-login", json={"password": [SECRET]}),
            client.delete("/api/settings/job-site-login"),
        ]
    assert [response.status_code for response in responses] == [200, 200, 422, 422, 204]
    assert caplog.records  # Capture is active (the HTTP client emits request metadata).
    assert SECRET not in caplog.text
    assert "short7!" not in caplog.text


def test_the_password_is_absent_from_every_database_table(db_session):
    from app.db import Base

    response = client.put("/api/settings/job-site-login", json={"password": SECRET})
    assert response.status_code == 200
    for table in Base.metadata.sorted_tables:
        rows = db_session.execute(select(table)).all()
        assert SECRET not in repr(rows), table.name


def test_the_password_is_absent_from_exports(db_session, tmp_path, monkeypatch):
    export_dir = tmp_path / "exports"
    monkeypatch.setattr(settings, "exports_dir", export_dir)
    saved = client.put("/api/settings/job-site-login",
                       json={"email": "ada@example.com", "password": SECRET})
    assert saved.status_code == 200
    responses = [
        client.get("/api/exports"),
        client.get("/api/exports/career"),
        client.post("/api/exports/career/refresh"),
    ]
    for response in responses:
        assert response.status_code == 200
        assert SECRET not in response.text
    assert (export_dir / "career.md").exists()
    for exported in export_dir.iterdir():
        assert SECRET.encode() not in exported.read_bytes()
