"""Knock-out pre-scan, on-site and relocation (design §3). An on-site role in
another city is a hard filter, and the profile's relocation answer decides it."""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.job import Job
from app.schemas.autofill_profile import WorkAuth
from app.services import autofill_profile
from app.services.knockout import scan_job
from tests.test_proposals_models import _mk_job

client = TestClient(app)

NYC = {"city": "New York", "state": "NY", "country": "US"}
HOME_NYC = {"city": "New York City", "state": "New York"}
HOME_TX = {"city": "Austin", "state": "TX"}


def _on_site(mode, place, personal, relocate):
    job = Job(raw_text="jd", raw_text_hash="h" * 8, work_mode=mode, **place)
    preferences = {} if relocate is None else {"willing_to_relocate": relocate}
    result = scan_job(job, WorkAuth(), preferences, personal=personal)
    return next((c for c in result["checks"] if c["kind"] == "on_site"), None), result["status"]


MATRIX = [
    ("remote", "remote", NYC, HOME_TX, False, "pass"),
    ("onsite, same city", "onsite", NYC, HOME_NYC, False, "pass"),
    ("hybrid, same state", "hybrid", {"city": "Albany", "state": "NY"}, HOME_NYC, False, "pass"),
    ("onsite elsewhere, won't relocate", "onsite", NYC, HOME_TX, False, "conflict"),
    ("hybrid elsewhere, typed no", "hybrid", NYC, HOME_TX, "No", "conflict"),
    ("onsite elsewhere, unset", "onsite", NYC, HOME_TX, None, "profile_missing"),
    ("onsite elsewhere, free text", "onsite", NYC, HOME_TX, "Open to relocating for the right role",
     "profile_missing"),
    ("on-site spelled out, will relocate", "on-site", NYC, HOME_TX, True, "pass"),
    ("no home on file", "onsite", NYC, {}, False, "profile_missing"),
    ("no home, will relocate", "onsite", NYC, {}, "yes", "pass"),
]


@pytest.mark.parametrize(("mode", "place", "personal", "relocate", "expected"),
                         [case[1:] for case in MATRIX], ids=[case[0] for case in MATRIX])
def test_the_on_site_matrix(mode, place, personal, relocate, expected):
    check, _ = _on_site(mode, place, personal, relocate)
    assert check["result"] == expected


@pytest.mark.parametrize("mode", [None, "unknown", ""])
def test_an_unknown_work_mode_adds_no_check(mode):
    check, _ = _on_site(mode, NYC, HOME_TX, False)
    assert check is None


def test_a_conflict_is_the_scans_verdict():
    _, status = _on_site("onsite", NYC, HOME_TX, False)
    assert status == "conflict"


MESSAGES = [
    (HOME_TX, False, "This job is on-site in New York. Your profile says you won't relocate."),
    (HOME_TX, None, "This job is on-site in New York. Answer Willing to relocate in Profile › Autofill."),
    ({}, False, "This job is on-site in New York. Add your city and state in Profile › Autofill."),
]


@pytest.mark.parametrize(("personal", "relocate", "message"), MESSAGES)
def test_the_on_site_messages_are_plain_sentences(personal, relocate, message):
    check, _ = _on_site("onsite", NYC, personal, relocate)
    assert check["message"] == message


def _on_site_job(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    autofill_profile.set_profile({"personal": HOME_TX,
                                  "preferences": {"willing_to_relocate": False}}, db_session)
    return _mk_job(db_session, company="Acme", work_mode="onsite",
                   source_url="https://jobs.ashbyhq.com/acme/42", **NYC)


def _kinds(scan):
    return {check["kind"]: check["result"] for check in scan["checks"]}


def test_the_job_detail_carries_the_on_site_check(db_session, tmp_path, monkeypatch):
    job = _on_site_job(db_session, tmp_path, monkeypatch)
    assert _kinds(client.get(f"/api/jobs/{job.id}/detail").json()["knockout"])["on_site"] == "conflict"


def test_the_companions_match_carries_the_scan(db_session, tmp_path, monkeypatch):
    job = _on_site_job(db_session, tmp_path, monkeypatch)
    body = client.get("/api/jobs/match", params={"url": job.source_url}).json()
    assert body["match"] == "exact"
    assert _kinds(body["knockout"])["on_site"] == "conflict"


def test_a_page_matching_nothing_carries_no_scan():
    body = client.get("/api/jobs/match", params={"url": "https://example.test/nothing"}).json()
    assert body["knockout"] is None
