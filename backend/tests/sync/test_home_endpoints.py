"""Home's sync endpoints (/api/sync/*): the channel the always-on copy talks to."""

import asyncio
import json
import logging
import threading
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker
from starlette.requests import ClientDisconnect

from app import models
from app.config import settings
from app.db import Base, get_db, make_engine
from app.main import app
from app.routers import sync as sync_router
from app.services import job_site_login, proposals
from app.services.sync import duplicates, files, jobs_bundle, request_apply, status
from tests.sync.test_jobs_bundle import SENTINEL, WHEN, build_job

LOGIN_SENTINEL = "SENTINEL-LOGIN-4482"
BAD_KEY = "SENTINEL-WRONG-KEY-9917"
ROOT_NAMES = ("applications", "base_resumes", "kb_documents")
ALLOWED_ORIGIN = "http://localhost:3000"
SECRET_CONSENT = {"channel": "frontend", "note": "triage"}
ROUTES = [
    ("GET", "/api/sync/hello", None),
    ("GET", "/api/sync/profile", None),
    ("GET", "/api/sync/jobs", None),
    ("POST", "/api/sync/jobs", {"bundles": [], "tombstones": []}),
    ("POST", "/api/sync/ownership", {"job_ids": []}),
    ("GET", "/api/sync/requests", None),
    ("POST", "/api/sync/requests", {"requests": []}),
    ("POST", "/api/sync/request-results", {"results": []}),
    ("GET", "/api/sync/handover/offers", None),
    ("POST", "/api/sync/handover/commit", {"job_ids": []}),
    ("POST", "/api/sync/handover/return", {"bundles": []}),
    ("POST", "/api/sync/runs", {"runs": []}),
]


@pytest.fixture
def roots(tmp_path, monkeypatch):
    paths = {}
    for side in ("home", "recv"):
        for name in ROOT_NAMES:
            paths[side, name] = tmp_path / side / name
            paths[side, name].mkdir(parents=True)

    def use(side):
        for name in ROOT_NAMES:
            monkeypatch.setattr(settings, f"{name}_dir", paths[side, name])

    use("home")
    return SimpleNamespace(home=paths["home", "applications"], recv=paths["recv", "applications"],
                           use=use)


@pytest.fixture
def recv(tmp_path):
    """The always-on copy's database."""
    engine = make_engine(f"sqlite:///{tmp_path / 'recv.sqlite3'}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, autoflush=False)() as session:
        yield session
    engine.dispose()


@pytest.fixture
def client(db_session):
    def override():
        try:
            yield db_session
        except Exception:
            db_session.rollback()
            raise
    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def remote_id(recv, sync_on):
    value = status.machine_id(recv)
    recv.commit()
    return value


@pytest.fixture
def home_id(db_session, sync_on):
    value = status.machine_id(db_session)
    db_session.commit()
    return value


@pytest.fixture
def auth(db_session, remote_id, home_id):
    """The headers a paired always-on copy sends."""
    revision = db_session.execute(text("SELECT version_num FROM alembic_version")).scalar()
    return {"Authorization": f"Bearer {status.read_key()}",
            "X-Maestro-Sync": f"{status.SYNC_PROTOCOL}:{revision}:{remote_id}"}


def _ids(items):
    return sorted(uuid.UUID(item).hex for item in items)


def remote_job(recv, roots, tag="a", **kwargs):
    """A job the always-on copy owns, as the bundle it would send."""
    roots.use("recv")
    ids = build_job(recv, roots.recv, tag=tag, **kwargs)
    bundle = json.loads(json.dumps(jobs_bundle.export_job(recv, ids.job)))
    roots.use("home")
    return ids, bundle


def set_hash(bundle, value):
    for item in bundle["rows"]:
        if item["table"] == "jobs":
            item["row"]["raw_text_hash"] = value
    return bundle


def post_jobs(client, auth, bundles, tombstones=()):
    return client.post("/api/sync/jobs", headers=auth,
                       json={"bundles": list(bundles), "tombstones": list(tombstones)})


def home_job(db, roots, tag="h", **kwargs):
    roots.use("home")
    return build_job(db, roots.home, tag=tag, **kwargs)


def lone_job(db, *, raw_text="Shared posting text", pending=False):
    """A job with no application and, optionally, one proposal still waiting for review."""
    job = models.Job(id=uuid.uuid4(), raw_text=raw_text,
                     raw_text_hash=uuid.uuid4().hex, title="Role", created_at=WHEN)
    db.add(job)
    db.flush()
    if pending:
        db.add(models.ApplicationProposal(job_id=job.id, status="pending_review"))
    db.commit()
    return job


# ------------------------------------------------------------------------ the common dependency


@pytest.fixture
def sync_off(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path / "settings")
    monkeypatch.setattr(settings, "sync_key_file", tmp_path / "absent-key")
    monkeypatch.setattr(settings, "sync_remote_url", "")


@pytest.mark.parametrize(("method", "path", "body"), ROUTES)
def test_every_route_is_a_404_with_sync_off(client, sync_off, method, path, body):
    headers = {"Authorization": "Bearer anything", "X-Maestro-Sync": "1:abc:def"}
    response = client.request(method, path, headers=headers, json=body)
    assert response.status_code == 404


def test_sync_off_beats_the_origin_check(client, sync_off):
    response = client.get("/api/sync/hello", headers={"Origin": ALLOWED_ORIGIN})
    assert response.status_code == 404


@pytest.mark.parametrize(("method", "path", "body"), ROUTES)
def test_the_always_on_copy_has_no_home_routes(client, sync_remote, auth, method, path, body):
    assert client.request(method, path, headers=auth, json=body).status_code == 404


@pytest.mark.parametrize(("method", "path", "body"), ROUTES)
def test_an_origin_is_refused_before_the_key_is_read(client, auth, method, path, body):
    headers = {**auth, "Authorization": f"Bearer {BAD_KEY}", "Origin": ALLOWED_ORIGIN}
    response = client.request(method, path, headers=headers, json=body)
    assert response.status_code == 403
    assert BAD_KEY not in response.text


def test_an_origin_is_refused_with_the_right_key_too(client, auth):
    assert client.get("/api/sync/hello", headers={**auth, "Origin": ALLOWED_ORIGIN}
                      ).status_code == 403


def test_an_unlisted_origin_is_refused_too(client, auth):
    headers = {**auth, "Origin": "https://evil.example"}
    assert client.get("/api/sync/hello", headers=headers).status_code == 403


@pytest.mark.parametrize("header", [None, f"Bearer {BAD_KEY}", BAD_KEY, "Bearer ", "Basic abc"])
def test_a_wrong_or_missing_key_is_a_401_that_echoes_nothing(client, auth, header):
    headers = {"X-Maestro-Sync": auth["X-Maestro-Sync"]}
    if header is not None:
        headers["Authorization"] = header
    body = {"bundles": [{"note": SENTINEL}], "tombstones": []}
    response = client.post("/api/sync/jobs", headers=headers, json=body)
    assert response.status_code == 401
    assert BAD_KEY not in response.text and SENTINEL not in response.text
    assert status.read_key() not in response.text


@pytest.mark.parametrize("change", ["protocol", "schema", "missing", "garbled", "same_machine"])
def test_a_version_or_identity_mismatch_is_a_409(client, auth, home_id, change):
    _, revision, remote = auth["X-Maestro-Sync"].split(":")
    value = {
        "protocol": f"{status.SYNC_PROTOCOL + 1}:{revision}:{remote}",
        "schema": f"{status.SYNC_PROTOCOL}:other-revision:{remote}",
        "garbled": "not-a-header",
        "same_machine": f"{status.SYNC_PROTOCOL}:{revision}:{home_id}",
        "missing": None,
    }[change]
    headers = {"Authorization": auth["Authorization"]}
    if value is not None:
        headers["X-Maestro-Sync"] = value
    response = client.get("/api/sync/hello", headers=headers)
    assert response.status_code == 409
    assert response.json()["reason"] == ("machine" if change == "same_machine" else "version")
    assert remote not in response.text and revision not in response.text


def test_the_key_is_checked_before_the_version(client, auth):
    headers = {"Authorization": f"Bearer {BAD_KEY}", "X-Maestro-Sync": "bad"}
    assert client.get("/api/sync/hello", headers=headers).status_code == 401


def test_a_second_request_while_one_runs_is_a_409(client, auth):
    assert sync_router._LOCK.acquire(blocking=False)
    try:
        response = client.get("/api/sync/hello", headers=auth)
    finally:
        sync_router._LOCK.release()
    assert (response.status_code, response.json()["detail"]) == (409, "A sync is already running.")
    assert client.get("/api/sync/hello", headers=auth).status_code == 200


def test_the_lock_is_released_after_every_outcome(client, auth):
    assert client.post("/api/sync/ownership", headers=auth, json={"job_ids": 5}).status_code == 422
    assert client.get("/api/sync/hello", headers=auth).status_code == 200
    assert client.get("/api/sync/hello", headers={**auth, "Authorization": "x"}).status_code == 401
    assert not sync_router._LOCK.locked()


def test_the_lock_is_held_while_a_request_runs(client, auth, monkeypatch):
    held = []
    real = sync_router.profile_bundle.export_profile

    def spy(*args, **kwargs):
        held.append(sync_router._LOCK.locked())
        return real(*args, **kwargs)

    monkeypatch.setattr(sync_router.profile_bundle, "export_profile", spy)
    assert client.get("/api/sync/profile", headers=auth).status_code == 200
    assert held == [True]


def test_a_body_over_the_cap_is_a_413(client, auth, monkeypatch):
    monkeypatch.setattr(sync_router, "MAX_BODY_BYTES", 500)
    response = client.post("/api/sync/ownership", headers=auth,
                           json={"job_ids": [SENTINEL * 100]})
    assert response.status_code == 413
    assert response.json()["detail"] == "That request is too large."
    assert SENTINEL not in response.text


def test_the_cap_counts_a_stream_that_declares_no_length(client, auth, monkeypatch):
    monkeypatch.setattr(sync_router, "MAX_BODY_BYTES", 500)

    def chunks():
        for _ in range(10):
            yield b'{"job_ids": ["' + b"x" * 100 + b'"]}'

    response = client.post("/api/sync/ownership", headers={**auth, "Content-Type": "application/json"},
                           content=chunks())
    assert response.status_code == 413


def test_a_body_at_the_cap_is_read(client, auth, monkeypatch):
    body = json.dumps({"job_ids": []}).encode()
    monkeypatch.setattr(sync_router, "MAX_BODY_BYTES", len(body))
    response = client.post("/api/sync/ownership", headers={**auth, "Content-Type": "application/json"},
                           content=body)
    assert response.status_code == 200


@pytest.mark.parametrize("payload", [
    {"job_ids": SENTINEL}, {"job_ids": [SENTINEL]}, {"nope": SENTINEL}, [SENTINEL], SENTINEL,
])
def test_a_bad_body_is_a_422_that_does_not_echo_it(client, auth, payload):
    response = client.post("/api/sync/ownership", headers=auth, json=payload)
    assert response.status_code == 422
    assert SENTINEL not in response.text
    assert response.json() == {"detail": "The request wasn't valid."}


def test_a_body_that_is_not_json_is_a_422(client, auth):
    response = client.post("/api/sync/ownership",
                           headers={**auth, "Content-Type": "application/json"},
                           content=f"{{{SENTINEL}".encode())
    assert response.status_code == 422 and SENTINEL not in response.text


def test_a_bad_query_is_a_422_that_does_not_echo_it(client, auth):
    response = client.get(f"/api/sync/jobs?since={SENTINEL}", headers=auth)
    assert response.status_code == 422
    assert SENTINEL not in response.text


# ----------------------------------------------------------------------------- the read routes


def test_hello_names_this_copy(client, auth, db_session, home_id):
    response = client.get("/api/sync/hello", headers=auth)
    revision = db_session.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert response.status_code == 200
    assert response.json() == {"protocol": status.SYNC_PROTOCOL, "schema_revision": revision,
                               "machine_id": home_id, "profile_rev": 0}


def test_profile_without_since_is_the_bundle(client, auth, db_session, roots):
    db_session.add(models.Setting(key="persona", value="Home persona"))
    db_session.commit()
    job_site_login.write("me@example.test", LOGIN_SENTINEL)
    body = client.get("/api/sync/profile", headers=auth).json()
    assert {"rows", "files", "job_site_login", "profile_rev"} <= set(body)
    assert body["job_site_login"]["password"] == LOGIN_SENTINEL
    assert any(item["table"] == "settings" for item in body["rows"])


def test_profile_since_the_current_revision_is_unchanged(client, auth, db_session):
    db_session.add(models.Setting(key="persona", value="Home persona"))
    db_session.commit()
    revision = client.get("/api/sync/hello", headers=auth).json()["profile_rev"]
    assert revision > 0
    assert client.get(f"/api/sync/profile?since={revision}", headers=auth).json() == {
        "unchanged": True}
    assert "rows" in client.get(f"/api/sync/profile?since={revision - 1}", headers=auth).json()


def test_profile_that_cannot_be_read_is_a_fixed_500(client, auth, monkeypatch):
    def refuse(*args, **kwargs):
        raise OSError(f"/private/{SENTINEL}")
    monkeypatch.setattr(sync_router.profile_bundle, "export_profile", refuse)
    response = client.get("/api/sync/profile", headers=auth)
    assert response.status_code == 500 and SENTINEL not in response.text


def cursor_of(bundle):
    return f"{bundle['sync_rev']}:{bundle['job_id']}"


def test_jobs_are_paged_by_a_revision_and_id_cursor(client, auth, db_session, roots):
    first = home_job(db_session, roots, tag="one")
    second = home_job(db_session, roots, tag="two")
    third = home_job(db_session, roots, tag="three")
    page = client.get("/api/sync/jobs?limit=2", headers=auth).json()
    assert [b["job_id"] for b in page["bundles"]] == [first.job.hex, second.job.hex]
    assert page["more"] is True and page["tombstones"] == []
    assert page["next_since"] == cursor_of(page["bundles"][-1])
    rest = client.get(f"/api/sync/jobs?since={page['next_since']}&limit=2", headers=auth).json()
    assert [b["job_id"] for b in rest["bundles"]] == [third.job.hex]
    assert rest["more"] is False
    assert rest["next_since"] == cursor_of(rest["bundles"][0])
    assert client.get(f"/api/sync/jobs?since={rest['next_since']}", headers=auth).json()[
        "bundles"] == []


def test_a_page_may_end_inside_a_revision_that_several_jobs_share(
        client, auth, db_session, roots):
    ids = [home_job(db_session, roots, tag=f"j{index}").job for index in range(5)]
    db_session.execute(text("UPDATE jobs SET sync_rev = 7"))
    db_session.commit()
    seen, cursor = [], "0"
    for _ in range(6):
        page = client.get(f"/api/sync/jobs?since={cursor}&limit=2", headers=auth).json()
        assert len(page["bundles"]) <= 2
        seen += [b["job_id"] for b in page["bundles"]]
        cursor = page["next_since"]
        if not page["more"]:
            break
    assert sorted(seen) == sorted(job.hex for job in ids)


def test_an_integer_since_still_means_after_that_revision(client, auth, db_session, roots):
    home_job(db_session, roots, tag="one")
    second = home_job(db_session, roots, tag="two")
    first_rev = client.get("/api/sync/jobs?limit=1", headers=auth).json()["bundles"][0]["sync_rev"]
    body = client.get(f"/api/sync/jobs?since={first_rev}", headers=auth).json()
    assert [b["job_id"] for b in body["bundles"]] == [second.job.hex]


@pytest.mark.parametrize("since", ["1:zz", "-1", "1:2:3", "9" * 40, "x:" + "a" * 32])
def test_a_malformed_cursor_is_a_422(client, auth, since):
    response = client.get(f"/api/sync/jobs?since={since}", headers=auth)
    assert response.status_code == 422


def test_a_page_stops_at_the_byte_budget_with_more(client, auth, db_session, roots, monkeypatch):
    first = home_job(db_session, roots, tag="one")
    home_job(db_session, roots, tag="two")
    one = client.get("/api/sync/jobs?limit=1", headers=auth).json()["bundles"][0]
    weight = jobs_bundle.weight(one)
    monkeypatch.setattr(sync_router, "PAGE_BYTES", weight + weight // 2)
    page = client.get("/api/sync/jobs", headers=auth).json()
    assert [b["job_id"] for b in page["bundles"]] == [first.job.hex]
    assert page["more"] is True and page["next_since"] == cursor_of(page["bundles"][0])


def test_a_job_over_the_budget_alone_is_still_sent(client, auth, db_session, roots, monkeypatch):
    first = home_job(db_session, roots, tag="one")
    second = home_job(db_session, roots, tag="two")
    monkeypatch.setattr(sync_router, "PAGE_BYTES", 10)
    page = client.get("/api/sync/jobs", headers=auth).json()
    assert [b["job_id"] for b in page["bundles"]] == [first.job.hex] and page["more"] is True
    rest = client.get(f"/api/sync/jobs?since={page['next_since']}", headers=auth).json()
    assert [b["job_id"] for b in rest["bundles"]] == [second.job.hex] and rest["more"] is False


def test_jobs_leave_out_replicas_and_carry_files(client, auth, db_session, recv, roots):
    mine = home_job(db_session, roots)
    _, bundle = remote_job(recv, roots)
    assert post_jobs(client, auth, [bundle]).status_code == 200
    body = client.get("/api/sync/jobs", headers=auth).json()
    assert [b["job_id"] for b in body["bundles"]] == [mine.job.hex]
    assert {entry["path"].split("/")[-1] for entry in body["bundles"][0]["files"]} >= {
        "resume.pdf", "resume.tex"}


def test_jobs_report_tombstones_within_the_page(client, auth, db_session, roots):
    keep = home_job(db_session, roots, tag="keep")
    gone = home_job(db_session, roots, tag="gone")
    db_session.delete(db_session.get(models.Job, gone.job))
    db_session.commit()
    body = client.get("/api/sync/jobs", headers=auth).json()
    assert [b["job_id"] for b in body["bundles"]] == [keep.job.hex]
    assert [t["job_id"] for t in body["tombstones"]] == [gone.job.hex]
    assert int(body["next_since"].split(":")[0]) >= body["tombstones"][0]["rev"]
    again = client.get(f"/api/sync/jobs?since={body['next_since']}", headers=auth).json()
    assert again["tombstones"] == []


def test_tombstones_ride_the_page_that_reaches_their_revision(client, auth, db_session, roots):
    gone = home_job(db_session, roots, tag="gone")
    db_session.delete(db_session.get(models.Job, gone.job))
    db_session.commit()
    first = home_job(db_session, roots, tag="one")
    second = home_job(db_session, roots, tag="two")
    page = client.get("/api/sync/jobs?limit=1", headers=auth).json()
    assert [b["job_id"] for b in page["bundles"]] == [first.job.hex]
    assert page["more"] is True and [t["job_id"] for t in page["tombstones"]] == [gone.job.hex]
    rest = client.get(f"/api/sync/jobs?since={page['next_since']}&limit=1", headers=auth).json()
    assert [b["job_id"] for b in rest["bundles"]] == [second.job.hex]
    assert rest["tombstones"] == []


def test_a_job_too_large_to_send_is_skipped_and_counted(client, auth, db_session, roots,
                                                       monkeypatch):
    home_job(db_session, roots)

    def too_big(*args, **kwargs):
        raise ValueError("too big")
    monkeypatch.setattr(sync_router.jobs_bundle, "export_job", too_big)
    body = client.get("/api/sync/jobs", headers=auth).json()
    assert body["bundles"] == [] and body["skipped"] == 1 and body["next_since"] != "0"


# ------------------------------------------------------------------------------- POST /jobs


def test_a_remote_job_is_stored_as_a_replica_owned_by_the_sender(
        client, auth, db_session, recv, roots, remote_id):
    ids, bundle = remote_job(recv, roots)
    body = post_jobs(client, auth, [bundle]).json()
    assert _ids(body["applied"]) == [ids.job.hex]
    assert body["duplicates"] == [] and body["refused"] == []
    db_session.expire_all()
    job = db_session.get(models.Job, ids.job)
    assert job.owner_machine == remote_id
    assert (roots.home / "Co_Role_a" / "resume.pdf").read_bytes() == b"%PDF a"
    assert db_session.get(models.Application, ids.app).artifact_dir == str(
        roots.home / "Co_Role_a")


def test_resending_a_bundle_changes_nothing(client, auth, db_session, recv, roots):
    ids, bundle = remote_job(recv, roots)
    first = post_jobs(client, auth, [bundle]).json()
    second = post_jobs(client, auth, [bundle]).json()
    assert first == second
    assert db_session.scalars(select(models.Job)).all()[0].id == ids.job


def test_a_remote_tombstone_deletes_its_own_replica_only(
        client, auth, db_session, recv, roots, remote_id):
    ids, bundle = remote_job(recv, roots)
    mine = home_job(db_session, roots)
    post_jobs(client, auth, [bundle])
    body = post_jobs(client, auth, [], [{"job_id": ids.job.hex, "rev": 5},
                                        {"job_id": mine.job.hex, "rev": 6},
                                        {"job_id": uuid.uuid4().hex, "rev": 7}]).json()
    assert _ids(body["deleted"]) == [ids.job.hex]
    db_session.expire_all()
    assert db_session.get(models.Job, ids.job) is None
    assert db_session.get(models.Job, mine.job) is not None
    assert not (roots.home / "Co_Role_a").exists()


def test_a_bundle_for_a_job_this_copy_owns_is_refused(client, auth, db_session, recv, roots):
    ids, bundle = remote_job(recv, roots)
    post_jobs(client, auth, [bundle])
    mine = home_job(db_session, roots)
    stolen = json.loads(json.dumps(bundle))
    stolen["job_id"] = mine.job.hex
    for item in stolen["rows"]:
        if item["table"] == "jobs":
            item["row"]["id"] = mine.job.hex
    body = post_jobs(client, auth, [stolen]).json()
    assert body["applied"] == [] and len(body["refused"]) == 1
    assert body["refused"][0]["job_id"] == mine.job.hex
    db_session.expire_all()
    assert db_session.get(models.Job, mine.job).owner_machine is None


def test_a_bundle_that_names_another_owner_is_refused(client, auth, recv, roots):
    _, bundle = remote_job(recv, roots)
    bundle["owner"] = "a-third-machine"
    body = post_jobs(client, auth, [bundle]).json()
    assert body["applied"] == [] and len(body["refused"]) == 1


def test_a_malformed_bundle_is_refused_without_stopping_the_rest(
        client, auth, db_session, recv, roots):
    ids, good = remote_job(recv, roots)
    bad = {"job_id": uuid.uuid4().hex, "rows": [{"table": "jobs", "row": {"id": SENTINEL}}]}
    body = post_jobs(client, auth, [bad, good]).json()
    assert _ids(body["applied"]) == [ids.job.hex]
    assert len(body["refused"]) == 1 and SENTINEL not in json.dumps(body)


def test_a_job_text_clash_with_nothing_started_keeps_the_laptops(
        client, auth, db_session, recv, roots):
    mine = lone_job(db_session)
    roots.use("recv")
    theirs = lone_job(recv)
    bundle = json.loads(json.dumps(jobs_bundle.export_job(recv, theirs.id)))
    roots.use("home")
    set_hash(bundle, db_session.get(models.Job, mine.id).raw_text_hash)
    body = post_jobs(client, auth, [bundle]).json()
    assert body["duplicates"] == [{"job_id": theirs.id.hex, "kept": "laptop",
                                   "local_id": mine.id.hex}]
    assert body["applied"] == []
    db_session.expire_all()
    assert db_session.get(models.Job, theirs.id) is None


def test_a_pending_review_proposal_alone_still_keeps_the_laptops(
        client, auth, db_session, recv, roots):
    mine = lone_job(db_session)
    roots.use("recv")
    theirs = lone_job(recv, pending=True)
    bundle = json.loads(json.dumps(jobs_bundle.export_job(recv, theirs.id)))
    roots.use("home")
    set_hash(bundle, db_session.get(models.Job, mine.id).raw_text_hash)
    assert post_jobs(client, auth, [bundle]).json()["duplicates"][0]["kept"] == "laptop"


def test_a_job_text_clash_with_work_done_keeps_both(
        client, auth, db_session, recv, roots, remote_id):
    mine = lone_job(db_session)
    ids, bundle = remote_job(recv, roots)
    original = db_session.get(models.Job, mine.id).raw_text_hash
    set_hash(bundle, original)
    body = post_jobs(client, auth, [bundle]).json()
    assert body["duplicates"] == [{"job_id": ids.job.hex, "kept": "both",
                                   "local_id": mine.id.hex}]
    assert _ids(body["applied"]) == [ids.job.hex]
    db_session.expire_all()
    replica = db_session.get(models.Job, ids.job)
    assert replica.owner_machine == remote_id
    assert replica.raw_text_hash == duplicates.replica_hash(ids.job) != original
    assert db_session.get(models.Job, mine.id).raw_text_hash == original


def test_a_kept_both_replica_can_be_applied_again_and_again(
        client, auth, db_session, recv, roots):
    mine = lone_job(db_session)
    ids, bundle = remote_job(recv, roots)
    set_hash(bundle, db_session.get(models.Job, mine.id).raw_text_hash)
    assert post_jobs(client, auth, [bundle]).json()["duplicates"][0]["kept"] == "both"
    for _ in range(2):
        again = post_jobs(client, auth, [bundle]).json()
        assert _ids(again["applied"]) == [ids.job.hex] and again["refused"] == []
    db_session.expire_all()
    assert db_session.get(models.Job, ids.job).raw_text_hash == duplicates.replica_hash(ids.job)


def test_a_kept_both_replica_stays_even_when_the_remote_job_has_no_work_left(
        client, auth, db_session, recv, roots):
    mine = lone_job(db_session)
    ids, bundle = remote_job(recv, roots)
    set_hash(bundle, db_session.get(models.Job, mine.id).raw_text_hash)
    post_jobs(client, auth, [bundle])
    bare = {**bundle, "files": [], "rows": [item for item in bundle["rows"]
                               if item["table"] in ("jobs", "job_skills")]}
    again = post_jobs(client, auth, [bare]).json()
    assert _ids(again["applied"]) == [ids.job.hex]
    assert again["duplicates"] == [] and again["refused"] == []
    db_session.expire_all()
    assert db_session.get(models.Job, ids.job).raw_text_hash == duplicates.replica_hash(ids.job)


def test_the_replica_hash_is_sha256_of_replica_and_the_job_id():
    job_id = uuid.UUID("12345678123456781234567812345678")
    import hashlib
    assert duplicates.replica_hash(job_id) == hashlib.sha256(
        b"replica:12345678123456781234567812345678").hexdigest()


def test_a_disk_failure_is_a_fixed_500_that_names_no_path(
        client, auth, db_session, recv, roots, monkeypatch, caplog):
    _, bundle = remote_job(recv, roots)
    caplog.set_level(logging.DEBUG)

    def fail(*args, **kwargs):
        raise OSError(28, f"No space left on device: '/private/{SENTINEL}'")
    monkeypatch.setattr(files, "unpack", fail)
    response = post_jobs(client, auth, [bundle])
    assert response.status_code == 500
    assert response.json() == {"detail": "Maestro couldn't save the files it received."}
    assert SENTINEL not in caplog.text


def test_the_files_limit_is_passed_to_apply(client, auth, recv, roots, monkeypatch):
    _, bundle = remote_job(recv, roots)
    seen = []
    real = files.unpack
    monkeypatch.setattr(files, "unpack", lambda entries, *, max_bytes=None: (
        seen.append(max_bytes), real(entries, max_bytes=max_bytes))[1])
    post_jobs(client, auth, [bundle])
    assert seen and all(isinstance(value, int) and value > 0 for value in seen)


def test_a_delete_and_a_new_job_with_the_same_text_in_one_push_keep_the_new_job(
        client, auth, db_session, recv, roots):
    old, old_bundle = remote_job(recv, roots, tag="old")
    assert post_jobs(client, auth, [old_bundle]).status_code == 200
    original = db_session.get(models.Job, old.job).raw_text_hash
    new, new_bundle = remote_job(recv, roots, tag="new")
    set_hash(new_bundle, original)
    body = post_jobs(client, auth, [new_bundle], [{"job_id": old.job.hex, "rev": 9}]).json()
    assert _ids(body["deleted"]) == [old.job.hex] and _ids(body["applied"]) == [new.job.hex]
    assert body["duplicates"] == [] and body["refused"] == []
    db_session.expire_all()
    assert db_session.get(models.Job, old.job) is None
    assert db_session.get(models.Job, new.job).raw_text_hash == original


def test_a_text_clash_with_a_replica_the_sender_owns_is_refused_for_a_retry(
        client, auth, db_session, recv, roots):
    old, old_bundle = remote_job(recv, roots, tag="old")
    post_jobs(client, auth, [old_bundle])
    original = db_session.get(models.Job, old.job).raw_text_hash
    new, new_bundle = remote_job(recv, roots, tag="new")
    set_hash(new_bundle, original)
    body = post_jobs(client, auth, [new_bundle]).json()
    assert body["applied"] == [] and body["duplicates"] == []
    assert [r["job_id"] for r in body["refused"]] == [new.job.hex]
    db_session.expire_all()
    assert db_session.get(models.Job, old.job) is not None
    assert db_session.get(models.Job, new.job) is None
    retry = post_jobs(client, auth, [new_bundle], [{"job_id": old.job.hex, "rev": 9}]).json()
    assert _ids(retry["applied"]) == [new.job.hex]


# --------------------------------------------------------------------------- POST /ownership


def test_ownership_names_home_remote_or_gone(client, auth, db_session, recv, roots):
    mine = home_job(db_session, roots)
    ids, bundle = remote_job(recv, roots)
    post_jobs(client, auth, [bundle])
    missing = uuid.uuid4()
    asked = [mine.job.hex, str(ids.job), missing.hex]
    body = client.post("/api/sync/ownership", headers=auth, json={"job_ids": asked}).json()
    assert body == {mine.job.hex: "home", str(ids.job): "remote", missing.hex: "gone"}


def test_an_offered_job_is_still_home(client, auth, db_session, roots):
    job = home_job(db_session, roots)
    db_session.get(models.Job, job.job).handover = "offered"
    db_session.commit()
    body = client.post("/api/sync/ownership", headers=auth, json={"job_ids": [job.job.hex]})
    assert body.json() == {job.job.hex: "home"}


def test_ownership_refuses_an_id_that_is_not_one(client, auth):
    response = client.post("/api/sync/ownership", headers=auth, json={"job_ids": [SENTINEL]})
    assert response.status_code == 422 and SENTINEL not in response.text


# ---------------------------------------------------------------------------- the requests


def _remote_case(client, auth, db_session, recv, roots, *, tag="a"):
    ids, bundle = remote_job(recv, roots, tag=tag)
    post_jobs(client, auth, [bundle])
    return ids


def _local_request(db, job_id, kind="proposal_transition", payload=None, when=None):
    row = models.SyncRequest(kind=kind, job_id=job_id, payload_json=payload or {"to": "rejected"},
                             origin="local", status="pending",
                             created_at=when or datetime.now(UTC))
    db.add(row)
    db.commit()
    return row


def test_requests_for_jobs_the_remote_owns_are_sent_and_marked(
        client, auth, db_session, recv, roots):
    ids = _remote_case(client, auth, db_session, recv, roots)
    mine = home_job(db_session, roots)
    now = datetime.now(UTC)
    late = _local_request(db_session, ids.job, when=now)
    early = _local_request(db_session, ids.job, "take_over", {}, now - timedelta(minutes=5))
    _local_request(db_session, mine.job)
    body = client.get("/api/sync/requests", headers=auth).json()
    assert [r["id"] for r in body] == [early.id.hex, late.id.hex]
    assert body[1] == {"id": late.id.hex, "kind": "proposal_transition", "job_id": ids.job.hex,
                       "payload": {"to": "rejected"}, "created_at": body[1]["created_at"]}
    db_session.expire_all()
    assert {r.status for r in db_session.scalars(select(models.SyncRequest)
            .where(models.SyncRequest.job_id == ids.job))} == {"sent"}
    assert client.get("/api/sync/requests", headers=auth).json() == body  # until answered
    client.post("/api/sync/request-results", headers=auth, json={"results": [
        {"id": early.id.hex, "status": "applied", "reason": None},
        {"id": late.id.hex, "status": "refused", "reason": "No."}]})
    assert client.get("/api/sync/requests", headers=auth).json() == []


def _owned_case(db, roots, status_="accepted", app_status="draft"):
    ids = home_job(db, roots, tag="own")
    proposal = db.get(models.ApplicationProposal, ids.proposal)
    proposal.status = status_
    db.get(models.Application, ids.app).status = app_status
    db.commit()
    return ids


def _request(job_id, kind, payload, when=None, request_id=None):
    return {"id": (request_id or uuid.uuid4()).hex, "kind": kind, "job_id": job_id.hex if job_id
            else None, "payload": payload,
            "created_at": (when or datetime.now(UTC)).isoformat()}


def post_requests(client, auth, *items):
    return client.post("/api/sync/requests", headers=auth, json={"requests": list(items)})


def test_a_proposal_decision_is_applied_with_the_users_consent(client, auth, db_session, roots):
    ids = _owned_case(db_session, roots)
    item = _request(ids.job, "proposal_transition", {
        "proposal_id": str(ids.proposal), "to": "rejected", "reason": "Not for me",
        "consent": SECRET_CONSENT})
    (result,) = post_requests(client, auth, item).json()
    assert result == {"id": item["id"], "status": "applied", "reason": None}
    db_session.expire_all()
    proposal = db_session.get(models.ApplicationProposal, ids.proposal)
    assert (proposal.status, proposal.reason) == ("rejected", "Not for me")
    events = db_session.scalars(select(models.ConsentEvent).where(
        models.ConsentEvent.proposal_id == ids.proposal, models.ConsentEvent.action == "rejected")
    ).all()
    assert [(e.channel, e.note) for e in events] == [("frontend", "triage")]


def test_a_decision_the_rules_refuse_is_refused_with_the_rule(client, auth, db_session, roots):
    ids = _owned_case(db_session, roots, status_="rejected")
    item = _request(ids.job, "proposal_transition", {
        "proposal_id": str(ids.proposal), "to": "accepted", "consent": SECRET_CONSENT})
    (result,) = post_requests(client, auth, item).json()
    assert result["status"] == "refused"
    assert result["reason"] == ("This proposal's status is Skipped, so it can't be changed "
                                "that way.")
    db_session.expire_all()
    assert db_session.get(models.ApplicationProposal, ids.proposal).status == "rejected"


def test_a_decision_with_no_consent_is_refused(client, auth, db_session, roots):
    ids = _owned_case(db_session, roots, status_="pending_review")
    item = _request(ids.job, "proposal_transition", {
        "proposal_id": str(ids.proposal), "to": "accepted"})
    (result,) = post_requests(client, auth, item).json()
    assert result["status"] == "refused" and "consent" in result["reason"]


def test_a_decision_on_a_job_that_is_not_here_is_refused(client, auth, db_session, recv, roots):
    ids = _remote_case(client, auth, db_session, recv, roots)
    item = _request(ids.job, "proposal_transition", {
        "proposal_id": str(ids.proposal), "to": "rejected", "consent": SECRET_CONSENT})
    (result,) = post_requests(client, auth, item).json()
    assert result == {"id": item["id"], "status": "refused",
                      "reason": "This job isn't on your laptop."}


def test_a_decision_on_an_offered_job_says_it_is_moving(client, auth, db_session, roots):
    ids = _owned_case(db_session, roots)
    db_session.get(models.Job, ids.job).handover = "offered"
    db_session.commit()
    item = _request(ids.job, "proposal_transition", {
        "proposal_id": str(ids.proposal), "to": "rejected", "consent": SECRET_CONSENT})
    (result,) = post_requests(client, auth, item).json()
    assert result["status"] == "refused" and "moving to your bot" in result["reason"]
    db_session.expire_all()
    assert db_session.get(models.ApplicationProposal, ids.proposal).status == "accepted"


def test_a_decision_naming_another_jobs_proposal_is_refused(client, auth, db_session, roots):
    ids = _owned_case(db_session, roots)
    other = home_job(db_session, roots, tag="other")
    item = _request(other.job, "proposal_transition", {
        "proposal_id": str(ids.proposal), "to": "rejected", "consent": SECRET_CONSENT})
    (result,) = post_requests(client, auth, item).json()
    assert result["status"] == "refused"
    db_session.expire_all()
    assert db_session.get(models.ApplicationProposal, ids.proposal).status == "accepted"


def test_a_status_change_stamps_the_date_and_closes_the_open_proposal(
        client, auth, db_session, roots):
    ids = _owned_case(db_session, roots)
    item = _request(ids.job, "application_patch", {
        "application_id": str(ids.app), "fields": {"status": "applied", "notes": "Sent it"}})
    (result,) = post_requests(client, auth, item).json()
    assert result["status"] == "applied"
    db_session.expire_all()
    application = db_session.get(models.Application, ids.app)
    assert (application.status, application.notes) == ("applied", "Sent it")
    assert application.applied_at is not None
    proposal = db_session.get(models.ApplicationProposal, ids.proposal)
    assert (proposal.status, proposal.reason) == ("rejected", "applied manually")


def test_a_notes_only_change_leaves_the_status_alone(client, auth, db_session, roots):
    ids = _owned_case(db_session, roots)
    item = _request(ids.job, "application_patch", {
        "application_id": str(ids.app), "fields": {"notes": "Call on Monday"}})
    post_requests(client, auth, item)
    db_session.expire_all()
    application = db_session.get(models.Application, ids.app)
    assert (application.status, application.notes, application.applied_at) == (
        "draft", "Call on Monday", None)
    assert db_session.get(models.ApplicationProposal, ids.proposal).status == "accepted"


@pytest.mark.parametrize("fields", [{"status": "teleported"}, {"template_id": "x"},
                                    {"customized_json": None}, {}])
def test_an_application_change_outside_status_and_notes_is_refused(
        client, auth, db_session, roots, fields):
    ids = _owned_case(db_session, roots)
    item = _request(ids.job, "application_patch", {
        "application_id": str(ids.app), "fields": fields})
    (result,) = post_requests(client, auth, item).json()
    assert result["status"] == "refused"
    db_session.expire_all()
    assert db_session.get(models.Application, ids.app).status == "draft"


def test_an_application_change_on_a_job_that_is_not_here_is_refused(
        client, auth, db_session, recv, roots):
    ids = _remote_case(client, auth, db_session, recv, roots)
    item = _request(ids.job, "application_patch", {
        "application_id": str(ids.app), "fields": {"status": "applied"}})
    (result,) = post_requests(client, auth, item).json()
    assert result["status"] == "refused"
    db_session.expire_all()
    assert db_session.get(models.Application, ids.app).status == "saved"


def test_the_requests_are_applied_in_created_order_so_the_last_decision_wins(
        client, auth, db_session, roots):
    ids = _owned_case(db_session, roots, status_="pending_review")
    now = datetime.now(UTC)
    payload = {"proposal_id": str(ids.proposal), "consent": SECRET_CONSENT}
    later = _request(ids.job, "proposal_transition", {**payload, "to": "rejected"}, now)
    earlier = _request(ids.job, "proposal_transition", {**payload, "to": "accepted"},
                       now - timedelta(minutes=1))
    results = post_requests(client, auth, later, earlier).json()
    assert [r["id"] for r in results] == [earlier["id"], later["id"]]
    assert [r["status"] for r in results] == ["applied", "applied"]
    db_session.expire_all()
    assert db_session.get(models.ApplicationProposal, ids.proposal).status == "rejected"


def test_a_resent_request_is_answered_from_the_record_not_applied_twice(
        client, auth, db_session, roots):
    ids = _owned_case(db_session, roots)
    item = _request(ids.job, "proposal_transition", {
        "proposal_id": str(ids.proposal), "to": "rejected", "consent": SECRET_CONSENT})
    first = post_requests(client, auth, item).json()
    second = post_requests(client, auth, item).json()
    assert first == second == [{"id": item["id"], "status": "applied", "reason": None}]
    db_session.expire_all()
    events = db_session.scalars(select(models.ConsentEvent).where(
        models.ConsentEvent.action == "rejected")).all()
    assert len(events) == 1
    row = db_session.get(models.SyncRequest, uuid.UUID(item["id"]))
    assert (row.origin, row.status, row.job_id) == ("remote", "applied", ids.job)


def test_a_refusal_is_recorded_and_repeated_as_it_was(client, auth, db_session, roots):
    ids = _owned_case(db_session, roots, status_="rejected")
    item = _request(ids.job, "proposal_transition", {
        "proposal_id": str(ids.proposal), "to": "accepted", "consent": SECRET_CONSENT})
    first = post_requests(client, auth, item).json()
    db_session.get(models.ApplicationProposal, ids.proposal).status = "pending_review"
    db_session.commit()
    assert post_requests(client, auth, item).json() == first


def test_a_profile_addition_creates_the_holder_and_the_point_once(client, auth, db_session):
    holder = {"kind": "extra", "title": "Unconfirmed claims", "status": "archived",
              "origin": "gap_elicitation", "detail_json": {"holder": "cannot_confirm"}}
    first = _request(None, "profile_addition", {"claim": "Stream processing", "holder": holder})
    second = _request(None, "profile_addition", {"claim": " stream  PROCESSING ", "holder": holder})
    results = post_requests(client, auth, first, second).json()
    assert [r["status"] for r in results] == ["applied", "applied"]
    db_session.expire_all()
    points = db_session.scalars(select(models.KBPoint)).all()
    assert [(p.text, p.provenance, p.state, p.origin) for p in points] == [
        ("Stream processing", "user_cannot_confirm", "retired", "gap_elicitation")]
    holders = db_session.scalars(select(models.KBEntity)).all()
    assert [(h.kind, h.title, h.status) for h in holders] == [
        ("extra", "Unconfirmed claims", "archived")]
    assert points[0].entity_id == holders[0].id


def test_a_profile_addition_reuses_an_existing_holder(client, auth, db_session):
    from app.services import tailoring_session
    existing = tailoring_session._cannot_confirm_holder(db_session)
    db_session.commit()
    item = _request(None, "profile_addition", {"claim": "Rust at scale", "holder": None})
    assert post_requests(client, auth, item).json()[0]["status"] == "applied"
    db_session.expire_all()
    assert [p.entity_id for p in db_session.scalars(select(models.KBPoint))] == [existing.id]
    assert len(db_session.scalars(select(models.KBEntity)).all()) == 1


@pytest.mark.parametrize("payload", [{}, {"claim": ""}, {"claim": 5}, {"claim": "x" * 5000}])
def test_a_profile_addition_without_a_usable_claim_is_refused(client, auth, db_session, payload):
    item = _request(None, "profile_addition", payload)
    assert post_requests(client, auth, item).json()[0]["status"] == "refused"
    assert db_session.scalars(select(models.KBPoint)).all() == []


def test_a_take_over_sent_to_home_is_refused_and_changes_nothing(
        client, auth, db_session, roots):
    ids = _owned_case(db_session, roots)
    item = _request(ids.job, "take_over", {})
    (result,) = post_requests(client, auth, item).json()
    assert result["status"] == "refused" and result["reason"]
    db_session.expire_all()
    assert db_session.get(models.Job, ids.job).owner_machine is None


def test_a_needs_decision_proposal_with_no_application_cannot_go_to_review(
        client, auth, db_session, roots):
    ids = _owned_case(db_session, roots, status_="needs_decision")
    proposal = db_session.get(models.ApplicationProposal, ids.proposal)
    proposal.application_id = None
    db_session.commit()
    item = _request(ids.job, "proposal_transition", {
        "proposal_id": str(ids.proposal), "to": "pending_review", "consent": SECRET_CONSENT})
    (result,) = post_requests(client, auth, item).json()
    assert result == {"id": item["id"], "status": "refused",
                      "reason": proposals.NO_APPLICATION_TO_LINK}
    db_session.expire_all()
    assert db_session.get(models.ApplicationProposal, ids.proposal).status == "needs_decision"


def test_a_needs_decision_proposal_with_an_application_goes_to_review_as_the_web_does(
        client, auth, db_session, roots):
    ids = _owned_case(db_session, roots, status_="needs_decision")
    item = _request(ids.job, "proposal_transition", {
        "proposal_id": str(ids.proposal), "to": "pending_review"})
    (result,) = post_requests(client, auth, item).json()
    assert result["status"] == "applied"
    db_session.expire_all()
    proposal = db_session.get(models.ApplicationProposal, ids.proposal)
    assert proposal.status == "pending_review" and proposal.fit_json["decided_by"] == "user"


def test_a_request_that_raises_is_refused_alone_with_a_fixed_sentence(
        client, auth, db_session, roots, monkeypatch, caplog):
    ids = _owned_case(db_session, roots)
    caplog.set_level(logging.DEBUG)

    def boom(db, item):
        raise RuntimeError(f"secret {SENTINEL}")
    monkeypatch.setitem(request_apply.APPLIERS, "take_over", boom)
    now = datetime.now(UTC)
    bad = _request(ids.job, "take_over", {}, now - timedelta(minutes=1))
    good = _request(ids.job, "application_patch", {
        "application_id": str(ids.app), "fields": {"notes": "Still applied"}}, now)
    first, second = post_requests(client, auth, bad, good).json()
    assert first == {"id": bad["id"], "status": "refused",
                     "reason": "Maestro couldn't apply this request."}
    assert second["status"] == "applied"
    assert SENTINEL not in caplog.text and SENTINEL not in json.dumps([first, second])
    db_session.expire_all()
    assert db_session.get(models.Application, ids.app).notes == "Still applied"
    assert post_requests(client, auth, bad).json() == [first]


def test_an_unknown_kind_is_refused(client, auth):
    item = _request(None, "wire_money", {"note": SENTINEL})
    (result,) = post_requests(client, auth, item).json()
    assert result["status"] == "refused" and SENTINEL not in json.dumps(result)


def test_a_request_with_an_unusable_shape_is_a_422(client, auth):
    response = client.post("/api/sync/requests", headers=auth,
                           json={"requests": [{"id": SENTINEL, "kind": "take_over"}]})
    assert response.status_code == 422 and SENTINEL not in response.text


# ----------------------------------------------------------------------- POST /request-results


def test_results_close_the_requests_that_were_sent(client, auth, db_session, recv, roots):
    ids = _remote_case(client, auth, db_session, recv, roots)
    applied = _local_request(db_session, ids.job)
    refused = _local_request(db_session, ids.job, "take_over", {})
    untouched = _local_request(db_session, ids.job, "take_over", {})
    client.get("/api/sync/requests", headers=auth)
    db_session.get(models.SyncRequest, untouched.id).status = "pending"
    db_session.commit()
    body = client.post("/api/sync/request-results", headers=auth, json={"results": [
        {"id": applied.id.hex, "status": "applied", "reason": None},
        {"id": refused.id.hex, "status": "refused", "reason": "Your bot is applying to this one."},
        {"id": untouched.id.hex, "status": "applied", "reason": None},
        {"id": uuid.uuid4().hex, "status": "applied", "reason": None},
    ]})
    assert body.status_code == 200 and body.json() == {"updated": 2}
    db_session.expire_all()
    rows = {r.id: r for r in db_session.scalars(select(models.SyncRequest))}
    assert (rows[applied.id].status, rows[applied.id].answered_at is not None) == ("applied", True)
    assert (rows[refused.id].status, rows[refused.id].reason) == (
        "refused", "Your bot is applying to this one.")
    assert rows[untouched.id].status == "pending"


def test_a_result_cannot_close_the_remotes_own_record(client, auth, db_session, roots):
    ids = _owned_case(db_session, roots)
    item = _request(ids.job, "take_over", {})
    post_requests(client, auth, item)
    client.post("/api/sync/request-results", headers=auth, json={"results": [
        {"id": item["id"], "status": "applied", "reason": None}]})
    db_session.expire_all()
    assert db_session.get(models.SyncRequest, uuid.UUID(item["id"])).status == "refused"


def test_a_result_with_another_status_is_a_422(client, auth):
    response = client.post("/api/sync/request-results", headers=auth, json={"results": [
        {"id": uuid.uuid4().hex, "status": "sent", "reason": SENTINEL}]})
    assert response.status_code == 422 and SENTINEL not in response.text


# --------------------------------------------------------------------------------- handovers


def _offer(db, roots, tag="offer"):
    ids = home_job(db, roots, tag=tag)
    db.get(models.Job, ids.job).handover = "offered"
    db.commit()
    return ids


def test_offers_are_the_bundles_of_offered_jobs_only(client, auth, db_session, roots):
    offered = _offer(db_session, roots)
    home_job(db_session, roots, tag="plain")
    body = client.get("/api/sync/handover/offers", headers=auth).json()
    assert [b["job_id"] for b in body["bundles"]] == [offered.job.hex]
    assert body["bundles"][0]["handover"] == "offered"


def test_commit_gives_an_offered_job_to_the_remote(client, auth, db_session, roots, remote_id):
    offered = _offer(db_session, roots)
    plain = home_job(db_session, roots, tag="plain")
    before = db_session.get(models.Job, offered.job).sync_rev
    body = client.post("/api/sync/handover/commit", headers=auth, json={
        "job_ids": [offered.job.hex, plain.job.hex, uuid.uuid4().hex]})
    assert body.status_code == 200 and _ids(body.json()["job_ids"]) == [offered.job.hex]
    db_session.expire_all()
    job = db_session.get(models.Job, offered.job)
    assert (job.owner_machine, job.handover) == (remote_id, None)
    assert job.sync_rev > before
    assert db_session.get(models.Job, plain.job).owner_machine is None


def test_a_job_the_user_kept_is_not_committed(client, auth, db_session, roots):
    offered = _offer(db_session, roots)
    db_session.get(models.Job, offered.job).handover = None
    db_session.commit()
    body = client.post("/api/sync/handover/commit", headers=auth,
                       json={"job_ids": [offered.job.hex]})
    assert body.json()["job_ids"] == []
    db_session.expire_all()
    assert db_session.get(models.Job, offered.job).owner_machine is None


def test_a_returned_job_is_owned_here_again(client, auth, db_session, recv, roots, remote_id):
    ids, bundle = remote_job(recv, roots)
    post_jobs(client, auth, [bundle])
    bundle["handover"] = "returning"
    for item in bundle["rows"]:
        if item["table"] == "applications" and str(item["row"]["id"]) == ids.app.hex:
            item["row"]["notes"] = "Changed at the bot"
    body = client.post("/api/sync/handover/return", headers=auth, json={"bundles": [bundle]})
    assert body.status_code == 200
    assert _ids(body.json()["job_ids"]) == [ids.job.hex] and body.json()["refused"] == []
    db_session.expire_all()
    job = db_session.get(models.Job, ids.job)
    assert (job.owner_machine, job.handover) == (None, None)
    assert db_session.get(models.Application, ids.app).notes == "Changed at the bot"
    db_session.get(models.Job, ids.job)
    # and the job is writable here again
    db_session.get(models.Application, ids.app).notes = "Mine"
    db_session.commit()


def test_a_kept_both_job_can_be_returned(client, auth, db_session, recv, roots):
    mine = lone_job(db_session)
    ids, bundle = remote_job(recv, roots)
    set_hash(bundle, db_session.get(models.Job, mine.id).raw_text_hash)
    assert post_jobs(client, auth, [bundle]).json()["duplicates"][0]["kept"] == "both"
    bundle["handover"] = "returning"
    body = client.post("/api/sync/handover/return", headers=auth, json={"bundles": [bundle]})
    assert _ids(body.json()["job_ids"]) == [ids.job.hex] and body.json()["refused"] == []
    db_session.expire_all()
    job = db_session.get(models.Job, ids.job)
    assert (job.owner_machine, job.handover) == (None, None)
    assert job.raw_text_hash == duplicates.replica_hash(ids.job)


def test_a_return_of_a_job_the_remote_does_not_own_is_refused(client, auth, db_session, recv,
                                                             roots):
    _, bundle = remote_job(recv, roots)
    unknown = client.post("/api/sync/handover/return", headers=auth, json={"bundles": [bundle]})
    assert unknown.json()["job_ids"] == [] and len(unknown.json()["refused"]) == 1
    mine = home_job(db_session, roots)
    stolen = json.loads(json.dumps(bundle))
    stolen["job_id"] = mine.job.hex
    for item in stolen["rows"]:
        if item["table"] == "jobs":
            item["row"]["id"] = mine.job.hex
    refused = client.post("/api/sync/handover/return", headers=auth, json={"bundles": [stolen]})
    assert refused.json()["job_ids"] == []


# ------------------------------------------------------------------------------------- runs


def _run(**changes):
    run = {"id": uuid.uuid4().hex, "automation": "hunt", "outcome": "ok", "agent": "A bot",
           "finished_at": datetime(2026, 10, 5, 12, 0, tzinfo=UTC).isoformat(),
           "counts": {"found": 3}, "digest": "Found three.", "job_ids": [uuid.uuid4().hex]}
    return {**run, **changes}


def test_runs_are_stored_with_the_senders_machine_and_upserted(
        client, auth, db_session, remote_id):
    run = _run()
    first = client.post("/api/sync/runs", headers=auth, json={"runs": [run]})
    assert first.status_code == 200 and _ids(first.json()["ids"]) == [run["id"]]
    client.post("/api/sync/runs", headers=auth, json={"runs": [{**run, "digest": "Changed."}]})
    db_session.expire_all()
    (row,) = db_session.scalars(select(models.AgentRun)).all()
    assert (row.machine, row.digest, row.outcome, row.counts) == (
        remote_id, "Changed.", "ok", {"found": 3})
    assert row.finished_at == datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def test_runs_never_overwrite_a_run_that_happened_here(client, auth, db_session):
    here = models.AgentRun(id=uuid.uuid4(), automation="hunt", outcome="ok", digest="Mine",
                           machine=None)
    db_session.add(here)
    db_session.commit()
    body = client.post("/api/sync/runs", headers=auth, json={"runs": [
        _run(id=here.id.hex, digest="Theirs")]})
    assert body.json()["ids"] == []
    db_session.expire_all()
    assert db_session.get(models.AgentRun, here.id).digest == "Mine"


def test_runs_are_never_pruned_by_a_push(client, auth, db_session, remote_id):
    runs = [_run() for _ in range(3)]
    client.post("/api/sync/runs", headers=auth, json={"runs": runs})
    client.post("/api/sync/runs", headers=auth, json={"runs": runs[:1]})
    assert len(db_session.scalars(select(models.AgentRun)).all()) == 3


@pytest.mark.parametrize("change", [{"outcome": "great"}, {"counts": {"found": "3"}},
                                    {"finished_at": "2026-10-05T12:00:00"}, {"id": SENTINEL}])
def test_a_run_of_the_wrong_shape_is_a_422(client, auth, change):
    response = client.post("/api/sync/runs", headers=auth, json={"runs": [_run(**change)]})
    assert response.status_code == 422 and SENTINEL not in response.text


def test_run_counts_accept_only_the_known_names(client, auth):
    response = client.post("/api/sync/runs", headers=auth, json={"runs": [
        _run(counts={SENTINEL: 1})]})
    assert response.status_code == 422 and SENTINEL not in response.text


# ------------------------------------------------------------------------------- the body reader


def test_a_stalled_peer_gets_a_408_and_the_lock_is_released(client, auth, monkeypatch):
    async def stalled(self):
        yield b"{"
        await asyncio.sleep(30)
    with monkeypatch.context() as patched:
        patched.setattr(Request, "stream", stalled)
        patched.setattr(sync_router, "_CHUNK_TIMEOUT", 0.05)
        response = client.post("/api/sync/ownership", headers=auth, json={"job_ids": []})
    assert response.status_code == 408
    assert response.json() == {"detail": "The request took too long to arrive."}
    assert not sync_router._LOCK.locked()
    assert client.get("/api/sync/hello", headers=auth).status_code == 200


def test_a_client_that_hangs_up_is_not_an_error(client, auth, monkeypatch, caplog):
    async def gone(self):
        raise ClientDisconnect
        yield b""
    monkeypatch.setattr(Request, "stream", gone)
    caplog.set_level(logging.DEBUG)
    client.post("/api/sync/ownership", headers=auth, json={"job_ids": []})
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert not sync_router._LOCK.locked()


# ---------------------------------------------------------------------------- never in a log


def test_nothing_secret_reaches_a_log_line(client, auth, db_session, recv, roots, caplog,
                                           monkeypatch):
    caplog.set_level(logging.DEBUG)
    job_site_login.write("me@example.test", LOGIN_SENTINEL)
    _, bundle = remote_job(recv, roots)
    good = post_jobs(client, auth, [bundle])
    assert good.status_code == 200
    broken = json.loads(json.dumps(bundle))
    broken["rows"][0]["row"]["salary_min"] = SENTINEL
    post_jobs(client, auth, [broken])
    client.post("/api/sync/ownership", headers=auth, json={"job_ids": SENTINEL})
    client.post("/api/sync/jobs", headers={**auth, "Authorization": f"Bearer {BAD_KEY}"},
                json={"bundles": [bundle], "tombstones": []})
    client.get("/api/sync/hello", headers={**auth, "Origin": ALLOWED_ORIGIN})
    profile = client.get("/api/sync/profile", headers=auth)
    assert LOGIN_SENTINEL in profile.text  # the channel carries it; nothing may write it down

    def boom(*args, **kwargs):
        raise RuntimeError(f"secret {SENTINEL} {LOGIN_SENTINEL}")
    monkeypatch.setattr(sync_router.jobs_bundle, "export_job", boom)
    home_job(db_session, roots)
    crashed = client.get("/api/sync/jobs", headers=auth)
    assert crashed.status_code == 500
    assert SENTINEL not in crashed.text and LOGIN_SENTINEL not in crashed.text
    for secret in (SENTINEL, LOGIN_SENTINEL, BAD_KEY, status.read_key()):
        assert secret not in caplog.text


def test_the_module_lock_is_a_plain_thread_lock():
    assert isinstance(sync_router._LOCK, type(threading.Lock()))
    assert sync_router.MAX_BODY_BYTES == 100 * 1024 * 1024
