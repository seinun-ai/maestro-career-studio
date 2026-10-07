"""Pairing regressions plus the real laptop process / in-process remote contract.

The process tests deliberately aren't slow: they need no downloads and belong in CI.
The pairing regressions also run without sockets, using Task 11's fake channel.
"""

import base64
import gzip
import hashlib
import json
import re
import socket
import time
import uuid
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, inspect as sa_inspect, select, text

from app import models
from app.config import settings
from app.db import get_db
from app.main import app
from app.services import base_resume_data, proposals, seeding, tailoring_session
from app.services.sync import jobs_bundle, pairing, profile_bundle, request_apply, seal, status
from app.services.sync import requests as sync_requests
from app.services.sync import round as sync_round
from tests.sync.conftest import sealed
from tests.conftest import _clear_tables
from tests.pdf_fixtures import text_pdf_bytes
from tests.sync import test_round as round_tests


@pytest.fixture
def world(tmp_path, monkeypatch):
    built = round_tests.World(tmp_path, monkeypatch)
    yield built
    built.close()


@pytest.fixture
def home(world, monkeypatch):
    return round_tests.home.__wrapped__(world, monkeypatch)


@pytest.fixture
def clock(monkeypatch):
    return round_tests.clock.__wrapped__(monkeypatch)


def first(world, **options):
    return sync_round.run_round(world.remote, pair=True, **options)


def setting(world, side, key, value):
    with world.building(side):
        db = getattr(world, side)
        db.add(models.Setting(key=key, value=value))
        db.commit()


def simple_job(db, *, job_id=None, base=None):
    job = models.Job(id=job_id or uuid.uuid4(), title="Test role", raw_text="Synthetic posting",
                     raw_text_hash=uuid.uuid4().hex)
    db.add(job)
    db.flush()
    application = None
    if base:
        application = models.Application(job_id=job.id, base_resume=base, status="draft")
        db.add(application)
        db.flush()
    db.commit()
    return SimpleNamespace(job=job.id, application=application.id if application else None)


def test_pairing_refuses_changed_remote_rows_without_values(world, home, clock, caplog):
    setting(world, "home", "llm.api_key", "home-value-sentinel")
    setting(world, "remote", "llm.api_key", "remote-value-sentinel")

    result = first(world)

    assert not result["ok"] and result["outcome"] == "needs_person"
    assert "settings" in result["skipped"] and "llm.api_key" in result["skipped"]
    assert not status.read_state(world.remote)["paired"]
    assert world.remote.get(models.Setting, "llm.api_key").value == "remote-value-sentinel"
    assert "value-sentinel" not in json.dumps(result) + caplog.text
    accepted = first(world, accept_profile_overwrite=True)
    assert accepted["ok"]
    assert world.remote.get(models.Setting, "llm.api_key").value == "home-value-sentinel"


def test_pairing_lists_lost_bases_and_remote_owned_applications(world, home, clock):
    with world.building("remote"):
        world.remote.add(models.BaseResume(slug="remote-only", data_json={}))
        world.remote.commit()
        ids = simple_job(world.remote, base="remote-only")
        replica = simple_job(world.remote, base="remote-only")
        world.remote.get(models.Job, replica.job).owner_machine = world.machine_id("home")
        world.remote.commit()

    result = first(world)

    assert not result["ok"]
    assert "base_resumes" in result["skipped"] and "remote-only" in result["skipped"]
    assert ids.application.hex in result["skipped"]
    assert replica.application.hex not in result["skipped"]
    assert first(world, accept_profile_overwrite=True)["ok"]
    assert world.remote.get(models.BaseResume, "remote-only") is None
    assert world.remote.get(models.Application, ids.application) is not None


@pytest.mark.parametrize("progress", ["application", "proposal"])
def test_pairing_lists_shared_progress_and_never_pushes_it(world, home, clock, progress):
    shared = uuid.uuid4()
    with world.building("home"):
        simple_job(world.home, job_id=shared)
    with world.building("remote"):
        ids = simple_job(world.remote, job_id=shared,
                         base="base" if progress == "application" else None)
        if progress == "proposal":
            world.remote.add(models.ApplicationProposal(job_id=shared, status="accepted"))
            world.remote.commit()
        remote_only = simple_job(world.remote)

    refused = first(world)

    assert not refused["ok"] and shared.hex in refused["skipped"]
    assert world.remote.get(models.Job, shared).owner_machine is None
    accepted = first(world, accept_profile_overwrite=True)
    assert accepted["ok"] and accepted["steps"]["push"]["sent"] == 1
    assert world.seen("remote").get(models.Job, shared).owner_machine == world.machine_id("home")
    assert world.seen("home").get(models.Job, remote_only.job).owner_machine == world.machine_id("remote")
    assert world.home.scalar(select(models.Application.id).where(models.Application.job_id == shared)) is None
    assert world.remote.scalar(select(models.Application.id).where(models.Application.job_id == shared)) is None
    if ids.application:
        assert world.remote.get(models.Application, ids.application) is None


def test_unworked_shared_jobs_become_replicas_without_an_overwrite_flag(world, home, clock):
    shared = uuid.uuid4()
    with world.building("home"):
        simple_job(world.home, job_id=shared)
    with world.building("remote"):
        simple_job(world.remote, job_id=shared)
    result = first(world)
    assert result["ok"] and result["steps"]["push"]["sent"] == 0
    assert result["steps"]["push"]["refused"] == 0
    assert world.remote.get(models.Job, shared).owner_machine == world.machine_id("home")


def test_a_repair_ignores_progress_on_replicas_of_laptop_jobs(world, home, clock):
    shared = uuid.uuid4()
    with world.building("home"):
        simple_job(world.home, job_id=shared)
    with world.building("remote"):
        simple_job(world.remote, job_id=shared)
    assert first(world)["ok"]
    assert world.remote.get(models.Job, shared).owner_machine == world.machine_id("home")
    with world.building("remote"):
        world.remote.add(models.Application(job_id=shared, base_resume="base", status="draft"))
        world.remote.commit()
        status.update_state(world.remote, paired=False)
        world.remote.commit()

    again = first(world)

    assert again["ok"], again
    assert "Shared jobs" not in json.dumps(again)


def test_pairing_skips_a_shared_job_that_vanished_before_the_commit(world, home, clock,
                                                                   monkeypatch):
    shared = uuid.uuid4()
    with world.building("home"):
        simple_job(world.home, job_id=shared)
    with world.building("remote"):
        simple_job(world.remote, job_id=shared)
    found = sync_round._shared_jobs
    monkeypatch.setattr(sync_round, "_shared_jobs", lambda ctx: [*found(ctx), uuid.uuid4()])

    result = first(world)

    assert result["ok"]
    assert world.remote.get(models.Job, shared).owner_machine == world.machine_id("home")


def test_pairing_failure_before_profile_commit_requires_comparison_again(world, home, clock,
                                                                       monkeypatch):
    real_unpack = profile_bundle.files.unpack

    def disk_full(*args, **kwargs):
        raise OSError("private file sentinel")

    monkeypatch.setattr(profile_bundle.files, "unpack", disk_full)
    result = first(world)
    assert not result["ok"]
    assert not status.read_state(world.remote)["paired"]
    assert status.read_state(world.remote)["profile_rev"] is None
    monkeypatch.setattr(profile_bundle.files, "unpack", real_unpack)
    clock.now += timedelta(minutes=31)
    setting(world, "remote", "persona", "changed while unpaired sentinel")
    again = first(world)
    assert not again["ok"] and "persona" in again["skipped"]


def test_pairing_state_and_shared_ownership_land_in_the_first_profile_commit(world, home, clock):
    shared = uuid.uuid4()
    with world.building("home"):
        simple_job(world.home, job_id=shared)
    with world.building("remote"):
        simple_job(world.remote, job_id=shared)
    observed = []

    def committed(db):
        with world.factories["remote"]() as reader:
            state = status.read_state(reader)
            observed.append((state["paired"], state["profile_rev"],
                             reader.get(models.Job, shared).owner_machine))

    event.listen(world.remote, "after_commit", committed)
    try:
        assert first(world)["ok"]
    finally:
        event.remove(world.remote, "after_commit", committed)
    paired = [row for row in observed if row[0]]
    assert paired and all(row[1] is not None for row in paired)
    assert paired[0][2] == world.machine_id("home")


def test_cannot_confirm_additions_do_not_block_pairing_and_reach_home(world, home, clock):
    with world.as_("remote"):
        holder = tailoring_session._cannot_confirm_holder(world.remote)
        world.remote.add(models.KBPoint(entity_id=holder.id, text="Synthetic unconfirmed claim",
                                        state="retired", origin="gap_elicitation",
                                        provenance="user_cannot_confirm"))
        world.remote.commit()
    result = first(world)
    assert result["ok"]
    assert world.seen("home").scalar(select(models.KBPoint.text).where(
        models.KBPoint.provenance == "user_cannot_confirm")) == "Synthetic unconfirmed claim"


def test_equal_profile_rows_ignore_json_object_key_order(world, home, clock):
    for side, data in (("home", {"summary": "same", "name": "Synthetic"}),
                       ("remote", {"name": "Synthetic", "summary": "same"})):
        with world.building(side):
            db = getattr(world, side)
            db.add(models.BaseResume(slug="base", data_json=data, created_at=round_tests.WHEN,
                                     updated_at=round_tests.WHEN))
            db.commit()
    assert first(world)["ok"]


def test_an_empty_career_profile_on_the_remote_does_not_block_pairing(world, home, clock):
    with world.building("home"):
        world.home.add(models.KBProfile(id=1, summary="Home summary", skills_json=["a"]))
        world.home.commit()
    with world.building("remote"):
        world.remote.add(models.KBProfile(id=1))
        world.remote.commit()
    assert first(world)["ok"]
    assert world.remote.get(models.KBProfile, 1).summary == "Home summary"


def test_a_filled_career_profile_on_the_remote_blocks_pairing(world, home, clock):
    with world.building("home"):
        world.home.add(models.KBProfile(id=1, summary="Home summary"))
        world.home.commit()
    with world.building("remote"):
        world.remote.add(models.KBProfile(id=1, summary="Remote summary sentinel"))
        world.remote.commit()
    result = first(world)
    assert not result["ok"] and "kb_profile" in result["skipped"]
    assert "sentinel" not in result["skipped"]


def test_rows_that_differ_only_in_their_own_timestamps_do_not_block_pairing(world, home, clock):
    for side, stamp in (("home", round_tests.WHEN), ("remote", round_tests.WHEN + timedelta(days=3))):
        with world.building(side):
            db = getattr(world, side)
            db.add(models.BaseResume(slug="base", data_json={"summary": "same"},
                                     created_at=stamp, updated_at=stamp))
            db.commit()
    assert first(world)["ok"]


# ------------------------------------------------------------ real home process

@pytest.fixture
def machines(home_backend, db_session, tmp_path, monkeypatch):
    """Separate database and file roots; only the remote uses process-global settings."""
    for name in ("applications", "base_resumes", "kb_documents", "settings"):
        root = tmp_path / name
        root.mkdir()
        monkeypatch.setattr(settings, f"{name}_dir", root)
    monkeypatch.setattr(settings, "sync_key_file", home_backend.key_file)
    monkeypatch.setattr(settings, "sync_remote_url", home_backend.url)
    with home_backend.session() as db:
        _clear_tables(db)
        db.commit()
        with jobs_bundle.applying(db):
            db.add(models.BaseResume(slug="base", data_json={"summary": "Home profile"}))
        (home_backend.root / "base_resumes" / "base.json").write_text(
            json.dumps({"summary": "Home profile"}), encoding="utf-8")
    now = SimpleNamespace(value=sync_round._now())
    monkeypatch.setattr(sync_round, "_now", lambda: now.value)

    def round_(**options):
        now.value += timedelta(minutes=31)
        return sync_round.run_round(db_session, pair=True, **options)

    def db_override():
        yield db_session

    app.dependency_overrides[get_db] = db_override
    remote_http = TestClient(app)
    yield SimpleNamespace(home=home_backend, db=db_session, remote_http=remote_http, round=round_)
    remote_http.close()
    app.dependency_overrides.pop(get_db, None)


def require_ok(response, code=200):
    assert response.status_code == code, f"HTTP {response.status_code}, expected {code}"
    return response.json()


def real_job(machines, side="remote", base="base"):
    if side == "remote":
        return simple_job(machines.db, base=base)
    with machines.home.session() as db, jobs_bundle.applying(db):
        return simple_job(db, base=base)


def test_real_pairing_refuses_profile_difference_and_accepts_flag(machines):
    with jobs_bundle.applying(machines.db):
        machines.db.add(models.Setting(key="persona", value="Remote profile sentinel"))
    refused = machines.round()
    assert not refused["ok"] and "persona" in refused["skipped"]
    assert "Remote profile sentinel" not in json.dumps(refused)
    assert machines.round(accept_profile_overwrite=True)["ok"]
    assert status.read_state(machines.db)["paired"]
    assert base_resume_data.load_base_resume("base", machines.db)["summary"] == "Home profile"


def test_real_remote_job_patch_is_a_request_and_its_result_returns_home(machines):
    assert machines.round()["ok"]
    ids = real_job(machines)
    assert machines.round()["ok"]
    home_app = require_ok(machines.home.http.get(f"/api/applications/{ids.application}"))
    assert home_app["job_id"] == str(ids.job)
    changed = machines.home.http.patch(f"/api/applications/{ids.application}",
                                        json={"notes": "Synthetic note", "status": "applied"})
    require_ok(changed, 202)
    with machines.home.session() as db:
        assert db.get(models.Application, ids.application).notes is None
        assert db.get(models.Job, ids.job).owner_machine == status.machine_id(machines.db)
    assert machines.round()["ok"]
    machines.db.expire_all()
    application = machines.db.get(models.Application, ids.application)
    assert (application.notes, application.status) == ("Synthetic note", "applied")
    assert application.applied_at is not None
    with machines.home.session() as db:
        request = db.scalar(select(models.SyncRequest))
        assert request.status == "applied" and request.reason is None
    assert machines.round()["ok"]
    result = require_ok(machines.home.http.get(f"/api/applications/{ids.application}"))
    assert (result["notes"], result["status"]) == ("Synthetic note", "applied")


def test_real_two_fresh_installs_pair_without_the_overwrite_flag(machines):
    """Both copies seed templates, the profile and prompts at their own first start."""
    with machines.home.session() as db:
        seeding.seed_startup_data(db)
    seeding.seed_startup_data(machines.db)
    result = machines.round()
    assert result["ok"], result.get("skipped")


def queue_on_home(machines, job_id):
    require_ok(machines.home.http.put("/api/settings/full-automation", json={"value": True}))
    proposal = require_ok(machines.home.http.post("/api/proposals", json={"job_id": str(job_id)}), 201)
    require_ok(machines.home.http.patch(f"/api/proposals/{proposal['id']}", json={
        "status": "accepted", "consent": {"channel": "frontend"}}))


def test_real_home_offer_is_committed_and_owned_by_remote(machines):
    ids = real_job(machines, "home")
    queue_on_home(machines, ids.job)
    with machines.home.session() as db:
        assert db.get(models.Job, ids.job).handover == "offered"
    assert machines.round()["ok"]
    job = machines.db.get(models.Job, ids.job)
    assert job.owner_machine is None and job.handover is None
    with machines.home.session() as db:
        assert db.get(models.Job, ids.job).owner_machine == status.machine_id(machines.db)


def test_real_keep_here_cancels_an_offer_before_the_round(machines):
    ids = real_job(machines, "home")
    queue_on_home(machines, ids.job)
    require_ok(machines.home.http.post(f"/api/jobs/{ids.job}/keep-here"))
    assert machines.round()["ok"]
    assert machines.db.get(models.Job, ids.job).owner_machine != status.machine_id(machines.db)
    with machines.home.session() as db:
        job = db.get(models.Job, ids.job)
        assert job.owner_machine is None and job.handover is None


def home_job_state(machines, job_id):
    with machines.home.session() as db:
        job = db.get(models.Job, job_id)
        return job.owner_machine, job.handover


def assert_handed_to_remote(machines, job_id, result):
    assert result["ok"] and result["steps"]["handovers"]["taken"] == 1
    job = machines.db.get(models.Job, job_id)
    assert (job.owner_machine, job.handover) == (None, None)
    assert home_job_state(machines, job_id) == (status.machine_id(machines.db), None)


def test_real_switching_full_automation_off_withdraws_an_offer_before_the_round(machines):
    ids = real_job(machines, "home")
    queue_on_home(machines, ids.job)
    assert home_job_state(machines, ids.job) == (None, "offered")
    off = machines.home.http.put("/api/settings/full-automation", json={"value": False})
    assert require_ok(off)["value"]["full_automation"] is False
    assert home_job_state(machines, ids.job) == (None, None)
    editable = machines.home.http.patch(f"/api/applications/{ids.application}",
                                        json={"notes": "Still mine"})
    assert editable.status_code == 200
    result = machines.round()
    assert result["ok"] and result["steps"]["handovers"]["taken"] == 0
    assert home_job_state(machines, ids.job) == (None, None)
    assert machines.db.get(models.Job, ids.job).owner_machine != status.machine_id(machines.db)


def test_real_a_queue_request_from_the_remote_is_offered_and_handed_over_in_one_round(machines):
    assert machines.round()["ok"]
    ids = real_job(machines, "home")
    require_ok(machines.home.http.put("/api/settings/full-automation", json={"value": True}))
    proposal = require_ok(machines.home.http.post("/api/proposals", json={"job_id": str(ids.job)}), 201)
    assert machines.round()["ok"]
    queued = machines.remote_http.patch(f"/api/proposals/{proposal['id']}", json={
        "status": "accepted", "consent": {"channel": "frontend"}})
    require_ok(queued, 202)
    assert home_job_state(machines, ids.job) == (None, None)

    assert_handed_to_remote(machines, ids.job, machines.round())

    with machines.home.session() as db:
        assert db.get(models.ApplicationProposal, uuid.UUID(proposal["id"])).status == "accepted"


def test_real_a_bulk_queue_on_home_is_offered_and_handed_over_at_the_next_round(machines):
    ids = real_job(machines, "home")
    require_ok(machines.home.http.put("/api/settings/full-automation", json={"value": True}))
    proposal = require_ok(machines.home.http.post("/api/proposals", json={"job_id": str(ids.job)}), 201)
    bulk = require_ok(machines.home.http.post("/api/proposals/bulk-transition", json={
        "ids": [proposal["id"]], "status": "accepted", "consent": {"channel": "frontend"}}))
    assert bulk["results"][0]["ok"] and bulk["results"][0]["status"] == "accepted"
    assert home_job_state(machines, ids.job) == (None, "offered")

    assert_handed_to_remote(machines, ids.job, machines.round())


def test_real_work_here_returns_a_remote_job(machines):
    assert machines.round()["ok"]
    ids = real_job(machines)
    assert machines.round()["ok"]
    require_ok(machines.home.http.post(f"/api/jobs/{ids.job}/work-here"), 202)
    assert machines.round()["ok"]
    with machines.home.session() as db:
        job = db.get(models.Job, ids.job)
        assert job.owner_machine is None and job.handover is None
        home_id = status.machine_id(db)
    assert machines.db.get(models.Job, ids.job).owner_machine == home_id


@pytest.mark.parametrize("side", ["home", "remote"])
def test_real_deleted_job_disappears_on_the_other_side(machines, side):
    assert machines.round()["ok"]
    ids = real_job(machines, side)
    assert machines.round()["ok"]
    http = machines.home.http if side == "home" else machines.remote_http
    response = http.delete(f"/api/jobs/{ids.job}")
    assert response.status_code == 204
    assert machines.round()["ok"]
    assert machines.db.get(models.Job, ids.job) is None
    with machines.home.session() as db:
        assert db.get(models.Job, ids.job) is None


def test_real_synced_application_pdf_is_served_and_renderable_on_home(machines):
    assert machines.round()["ok"]
    ids = real_job(machines)
    folder = settings.applications_dir / ids.application.hex
    folder.mkdir()
    pdf = folder / "resume.pdf"
    pdf.write_bytes(text_pdf_bytes("Synthetic resume"))
    application = machines.db.get(models.Application, ids.application)
    application.artifact_dir, application.pdf_path = str(folder), str(pdf)
    machines.db.commit()
    assert machines.round()["ok"]
    response = machines.home.http.get(f"/api/applications/{ids.application}/pdf")
    assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
    assert response.content == pdf.read_bytes()
    preview = require_ok(machines.home.http.get(f"/api/applications/{ids.application}/preview/pages"))
    assert preview["page_count"] == 1
    page = machines.home.http.get(f"/api/applications/{ids.application}/preview/page/1")
    assert page.status_code == 200 and page.headers["content-type"] == "image/png"
    assert page.content.startswith(b"\x89PNG\r\n\x1a\n")


def reserve(db, job_id):
    proposal = proposals.create_proposal(db, job_id=job_id)
    proposal.evidence_json = [{"kind": "final_review"}]
    proposals.transition(db, proposal, "accepted", consent={"channel": "frontend"})
    proposals.transition(db, proposal, "approved", consent={"channel": "frontend"})
    db.commit()


def test_real_daily_cap_counts_reservations_on_both_sides(machines):
    ids = real_job(machines, "home")
    with machines.home.session() as db, jobs_bundle.applying(db):
        reserve(db, ids.job)
    assert machines.round()["ok"]
    remote_ids = real_job(machines)
    reserve(machines.db, remote_ids.job)
    assert machines.round()["ok"]
    cap = proposals.cap_status(machines.db)
    assert cap["reserved_last_24h"] == 2
    assert cap["remaining"] == cap["max_per_day"] - 2
    with machines.home.session() as db:
        assert proposals.cap_status(db)["reserved_last_24h"] == 2


def test_real_wrong_key_is_a_bare_404_and_the_round_cannot_verify(machines, tmp_path, monkeypatch):
    path = tmp_path / "wrong-key"
    path.write_text(uuid.uuid4().hex, encoding="utf-8")
    monkeypatch.setattr(settings, "sync_key_file", path)
    response = machines.home.http.get("/api/sync/hello", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 404 and response.content == b""
    result = machines.round()
    assert result["outcome"] == "needs_person"
    assert result["error"] == (
        "The laptop didn't accept this copy's seal: the key differs or sync is off there."
    )
    assert "wrong" not in json.dumps(result)


def test_real_lost_home_after_push_keeps_commits_and_retry_finishes(machines, monkeypatch):
    assert machines.round()["ok"]
    ids = real_job(machines)
    before = status.read_state(machines.db)["since_home"]
    call = sync_round._call

    def stop_after_push(ctx, method, path, **options):
        answer = call(ctx, method, path, **options)
        if (method, path) == ("POST", "/api/sync/jobs"):
            machines.home.stop()
        return answer

    monkeypatch.setattr(sync_round, "_call", stop_after_push)
    try:
        failed = machines.round()
        assert not failed["ok"] and failed["outcome"] == "transient"
        state = status.read_state(machines.db)
        assert state["acked_own"] >= machines.db.get(models.Job, ids.job).sync_rev
        assert state["since_home"] == before
        with machines.home.session() as db:
            assert db.get(models.Job, ids.job) is not None
            assert db.scalar(text("PRAGMA integrity_check")) == "ok"
        assert machines.db.scalar(text("PRAGMA integrity_check")) == "ok"
    finally:
        machines.home.start()
        monkeypatch.setattr(sync_round, "_call", call)
    assert machines.round()["ok"]
    assert status.read_state(machines.db)["failures"] == 0


def peer_for(machines):
    return f"{status.SYNC_PROTOCOL}:{status.schema_revision(machines.db)}:remote-1"


def test_real_missing_seal_and_browser_origin_are_refused(machines):
    bare = machines.home.http.get("/api/sync/hello")
    assert bare.status_code == 404 and bare.content == b""
    assert "www-authenticate" not in bare.headers
    basic = machines.home.http.get("/api/sync/hello", headers={"Authorization": "Basic abc"})
    assert basic.status_code == 404 and basic.content == b""
    key = status.read_key()
    peer = peer_for(machines)
    header, _wire, _rid = seal.seal_request(key, "GET", "/api/sync/hello", "", b"", peer)
    browser = machines.home.http.get("/api/sync/hello", headers={
        seal.HEADER: header, "X-Maestro-Sync": peer, "Origin": "http://localhost:3000"})
    assert browser.status_code == 404 and browser.content == b""
    assert "x-maestro-seal" not in browser.headers
    code, body = sealed(machines.home.http, "GET", "/api/sync/hello", peer=peer, key=key)
    assert code == 200 and body["protocol"] == status.SYNC_PROTOCOL


def _wire_of(wire, send):
    """``prefix`` stalls after 4 bytes; a ``(body, length)`` pair declares a different length."""
    if send == "prefix":
        return wire[:4], len(wire)
    if isinstance(send, tuple):
        return send
    return (wire if send is None else send), len(wire)


def raw_request(machines, method, path, *, plaintext=b"", send=None):
    """One sealed request on its own socket. ``send`` replaces what is written after the headers."""
    key = status.read_key()
    peer = peer_for(machines)
    header, wire, rid = seal.seal_request(key, method, path, "", plaintext, peer)
    sent, length = _wire_of(wire, send)
    lines = (
        f"{method} {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: {length}\r\n"
        f"{seal.HEADER}: {header}\r\nX-Maestro-Sync: {peer}\r\n\r\n"
    )
    sock = socket.create_connection(("127.0.0.1", machines.home.port), timeout=10)
    sock.sendall(lines.encode() + sent)
    return sock, rid, key, wire


def _read_http(sock):
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    head, _, rest = data.partition(b"\r\n\r\n")
    headers = {}
    status_line, _, header_blob = head.partition(b"\r\n")
    for line in header_blob.split(b"\r\n"):
        if b":" in line:
            name, value = line.split(b":", 1)
            headers[name.decode("latin-1").lower()] = value.strip().decode("latin-1")
    length = int(headers.get("content-length", "0"))
    while len(rest) < length:
        chunk = sock.recv(4096)
        if not chunk:
            break
        rest += chunk
    return status_line.decode("latin-1"), headers, rest[:length]


def test_real_oversized_body_is_a_413_before_it_is_read(machines):
    declared = 100 * 1024 * 1024 + 1
    sock, rid, key, _wire = raw_request(
        machines, "POST", "/api/sync/jobs", send=(b"", declared))
    with sock:
        status_line, headers, body = _read_http(sock)
    assert status_line.startswith("HTTP/1.1 413")
    assert b"too large" not in body
    plain = seal.open_response(key, rid, 413, headers["x-maestro-seal"], body)
    assert json.loads(plain)["detail"] == "That request is too large."
    code, _hello = sealed(machines.home.http, "GET", "/api/sync/hello", peer=peer_for(machines))
    assert code == 200


def test_real_stalled_body_does_not_hold_the_lock(machines):
    """The body is read before the single-flight lock, so a stall cannot busy the laptop."""
    sock, _rid, _key, _wire = raw_request(
        machines, "POST", "/api/sync/runs", plaintext=b'{"runs":[]}', send="prefix")
    try:
        codes = []
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            codes.append(sealed(
                machines.home.http, "GET", "/api/sync/hello", peer=peer_for(machines))[0])
            time.sleep(0.05)
        assert 409 not in codes and 200 in codes
    finally:
        sock.close()


def test_real_take_over_is_refused_while_the_bot_is_applying(machines):
    assert machines.round()["ok"]
    ids = real_job(machines)
    reserve(machines.db, ids.job)
    assert machines.round()["ok"]
    require_ok(machines.home.http.post(f"/api/jobs/{ids.job}/work-here"), 202)
    assert machines.round()["ok"]
    with machines.home.session() as db:
        request = db.scalar(select(models.SyncRequest).where(models.SyncRequest.kind == "take_over"))
        assert request.status == "refused"
        assert request.reason == request_apply.BUSY_APPLYING
        assert db.get(models.Job, ids.job).owner_machine == status.machine_id(machines.db)


# ------------------------------------------------ intercepting proxy

_PROFILE = "profile-sentinel-k7m2q9vx4n8p"
_AI_KEY = "sk-sentinel-ai-b4c8e1d6f3a79c2e"
_PASSWORD = "login-sentinel-p9w3h6t2m5"
_TITLE = "title-sentinel-r8y5u1i4o6"
_FILE = b"file-sentinel-bytes-m2n8b5v7q1w4e6r9"
_NOTE = "request-sentinel-q4n7h2c8"
_LATER = "later-note-sentinel-h6k3p9d1"
_REMOTE_TITLE = "remote-title-sentinel-v1k8m3"
_NEWER_TITLE = "newer-title-sentinel-v2p6q1"
_REMOTE_FILE = b"remote-file-sentinel-z4c7n2b8"

# Every route this scenario's rounds send. One that goes around the proxy is missing here.
_ROUTES = frozenset({
    ("POST", "/api/sync/enroll"),
    ("GET", "/api/sync/hello"),
    ("GET", "/api/sync/profile"),
    ("POST", "/api/sync/ownership"),
    ("GET", "/api/sync/jobs"),
    ("POST", "/api/sync/jobs"),
    ("GET", "/api/sync/requests"),
    ("POST", "/api/sync/requests"),
    ("GET", "/api/sync/handover/offers"),
})

# Request names are the forward-proxy allow-list. Response names are what a sealed
# Response actually emits: only X-Maestro-Seal (no media type, so no content-type),
# plus content-length from Starlette and date and server from uvicorn.
_REQUEST_HEADERS = frozenset({
    "host", "content-length", "content-type", "accept", "accept-encoding",
    "connection", "user-agent", "x-maestro-sync", "x-maestro-seal",
})
_RESPONSE_HEADERS = frozenset({"content-length", "date", "server", "x-maestro-seal"})
_B64_TOKEN = re.compile(r"[A-Za-z0-9+/_=-]{16,}")


def _prepare_proxy_remote(monkeypatch, home, tmp_path, proxy):
    """The in-process remote takes the https route, so httpx honors HTTP_PROXY."""
    for name in ("applications", "base_resumes", "kb_documents", "settings"):
        root = tmp_path / name
        root.mkdir()
        monkeypatch.setattr(settings, f"{name}_dir", root)
    monkeypatch.setattr(settings, "sync_key_file", tmp_path / "remote-sync-key")
    monkeypatch.setattr(settings, "sync_remote_url", home.url)
    monkeypatch.setattr(status, "remote_route", lambda: "https")
    monkeypatch.setenv("HTTP_PROXY", proxy.url)
    monkeypatch.setenv("http_proxy", proxy.url)
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)


def _clock(monkeypatch):
    now = SimpleNamespace(value=sync_round._now())
    monkeypatch.setattr(sync_round, "_now", lambda: now.value)
    return now


def _write_login(home):
    path = Path(home.env["SETTINGS_DIR"]) / "secrets" / "job-site-login.json"
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps({"email": "me@example.test", "password": _PASSWORD}),
                    encoding="utf-8")
    path.chmod(0o600)


def _add_home_rows(db, job_id, app_id, folder):
    db.add(models.KBProfile(id=1, summary=_PROFILE))
    db.add(models.Setting(key="llm.openai_api_key", value=_AI_KEY))
    db.add(models.Setting(key="kb.seeded", value="1"))
    db.add(models.Job(id=job_id, title=_TITLE, raw_text="Synthetic posting",
                      raw_text_hash=uuid.uuid4().hex))
    db.flush()
    db.add(models.Application(
        id=app_id, job_id=job_id, base_resume="base", status="draft",
        artifact_dir=str(folder), pdf_path=str(folder / "note.bin")))


def _seed_home(home, file_bytes):
    job_id, app_id = uuid.uuid4(), uuid.uuid4()
    folder = Path(home.env["APPLICATIONS_DIR"]) / app_id.hex
    folder.mkdir(parents=True)
    (folder / "note.bin").write_bytes(file_bytes)
    _write_login(home)
    with home.session() as db:
        _clear_tables(db)
        db.commit()
        with jobs_bundle.applying(db):
            _add_home_rows(db, job_id, app_id, folder)
    return SimpleNamespace(job=job_id, application=app_id)


def _pair_and_sync(db, home):
    opened = home.http.post("/api/settings/second-copy")
    assert opened.status_code == 200, opened.status_code
    code = opened.json()["code"]
    assert pairing.enroll_here(db, code) == {"ok": True}
    first = sync_round.run_round(db, pair=True)
    assert first["ok"], first.get("outcome")
    return code


def _queue_and_send(db, ids, now):
    application = db.get(models.Application, ids.application)
    queued = sync_requests.queue_application_patch(db, application, {"notes": _NOTE})
    assert queued is not None and queued.status_code == 202
    now.value += timedelta(minutes=31)
    second = sync_round.run_round(db, pair=True)
    assert second["ok"], second.get("outcome")
    assert second["steps"]["requests"]["sent"] == 1
    assert second["steps"]["push"]["sent"] == 1


def _assert_request_landed(home, db, ids):
    with home.session() as session:
        assert session.get(models.Application, ids.application).notes == _NOTE
    db.expire_all()
    assert db.get(models.Application, ids.application).notes is None


def _assert_payloads_arrived(db, tmp_path, ids, file_bytes):
    """The sealed round delivered every sentinel. Absence from the proxy is then meaningful."""
    db.expire_all()
    assert db.get(models.KBProfile, 1).summary == _PROFILE
    assert db.get(models.Setting, "llm.openai_api_key").value == _AI_KEY
    assert db.get(models.Job, ids.job).title == _TITLE
    login = (tmp_path / "settings" / "secrets" / "job-site-login.json").read_text(encoding="utf-8")
    assert _PASSWORD in login
    found = tmp_path / "applications" / ids.application.hex / "note.bin"
    assert found.read_bytes() == file_bytes


def _code_digest(code):
    normalized = pairing.normalize_code(code)
    assert normalized is not None
    return hashlib.sha256(normalized.encode()).hexdigest()


def _sync_key_and_digest(home, code):
    key = home.key_file.read_text(encoding="utf-8").strip()
    return key, _code_digest(code)


def _derived_hex(sync_key, digest):
    """The four message keys, hex: sync traffic from the sync key, enrollment from the digest."""
    pairs = (
        (sync_key, seal.TO_HOME), (sync_key, seal.TO_REMOTE),
        (digest, seal.ENROLL_TO_HOME), (digest, seal.ENROLL_TO_REMOTE),
    )
    return [seal.derive(secret, label).hex().encode() for secret, label in pairs]


def _raw_secrets(home, code, home_file):
    key, digest = _sync_key_and_digest(home, code)
    normalized = pairing.normalize_code(code).encode()
    values = [
        key.encode(), code.encode(), normalized, digest.encode(),
        _PROFILE.encode(), _AI_KEY.encode(), _PASSWORD.encode(), _TITLE.encode(),
        _NOTE.encode(), _LATER.encode(), _REMOTE_TITLE.encode(), _NEWER_TITLE.encode(),
        home_file, _REMOTE_FILE, base64.standard_b64encode(home_file),
        base64.standard_b64encode(_REMOTE_FILE),
    ]
    values.extend(_derived_hex(key, digest))
    return values


def _encode_both(chunk):
    found = []
    for encode in (base64.standard_b64encode, base64.urlsafe_b64encode):
        token = encode(chunk)
        found.append(token)
        stripped = token.rstrip(b"=")
        if stripped != token:
            found.append(stripped)
    return found


def _aligned_chunk(secret, offset):
    start = (3 - offset) % 3
    length = ((len(secret) - start) // 3) * 3
    return secret[start:start + length]


def _b64_needles(secret):
    """Standard and urlsafe base64 of ``secret`` at each 3-byte alignment."""
    found = _encode_both(secret)
    for offset in range(3):
        chunk = _aligned_chunk(secret, offset)
        if len(chunk) >= 12:
            found.extend(_encode_both(chunk))
    return [token for token in found if len(token) >= 16]


def _unique(items):
    seen, found = set(), []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            found.append(item)
    return found


def _forbidden(home, code, file_bytes):
    raw = _raw_secrets(home, code, file_bytes)
    needles = []
    for secret in raw:
        needles.extend(_b64_needles(secret))
    return _unique(raw + needles)


def _gunzip(blob):
    if len(blob) < 2 or blob[:2] != b"\x1f\x8b":
        return None
    try:
        return gzip.decompress(blob)
    except OSError:
        return None


def _try_decode(padded):
    found = []
    for decoder in (base64.standard_b64decode, base64.urlsafe_b64decode):
        try:
            found.append(decoder(padded))
        except ValueError:
            continue
    return found


def _decoded_at_offsets(token):
    found = []
    for offset in range(3):
        piece = token[offset:]
        if len(piece) < 16:
            continue
        found.extend(_try_decode(piece + "=" * (-len(piece) % 4)))
    return found


def _views_of(blob):
    views = [blob]
    opened = _gunzip(blob)
    if opened is not None:
        views.append(opened)
    for token in _B64_TOKEN.findall(blob.decode("latin-1")):
        for decoded in _decoded_at_offsets(token):
            views.append(decoded)
            inflated = _gunzip(decoded)
            if inflated is not None:
                views.append(inflated)
    return views


def _no_secrets(pairs, forbidden):
    for request, response in pairs:
        for raw in (request, response):
            head, _, body = raw.partition(b"\r\n\r\n")
            for view in _views_of(head) + _views_of(body):
                if any(secret in view for secret in forbidden):
                    raise AssertionError("the proxy recording contained a secret")


def _assert_recorded_seal(blob, port):
    folded = blob.lower()
    absolute = f"http://127.0.0.1:{port}/api/sync/".encode()
    assert absolute in blob and b"x-maestro-seal:" in folded
    assert f"POST {absolute.decode()}enroll ".encode() in blob
    assert b"/api/sync/jobs" in blob and b"http/1.1 200" in folded


def _one_post(proxy, port, path):
    prefix = f"POST http://127.0.0.1:{port}{path} ".encode()
    found = [req for req in proxy.recorded_requests() if req.startswith(prefix)]
    assert len(found) == 1
    return found[0]


def replay_recorded(proxy, raw):
    sock = socket.create_connection(("127.0.0.1", proxy.port), timeout=20)
    with sock:
        sock.sendall(raw)
        status_line, headers, body = _read_http(sock)
    return int(status_line.split(" ", 2)[1]), headers, body


def _assert_bare(code, headers, body):
    assert code == 404 and body == b"" and "x-maestro-seal" not in headers


def _stamp(value):
    return None if value is None else value.isoformat()


def _counts(session):
    names = sorted(sa_inspect(session.get_bind()).get_table_names())
    return {name: session.scalar(text(f'SELECT COUNT(*) FROM "{name}"')) for name in names}


def _request_row(row):
    payload = json.dumps(row.payload_json, sort_keys=True, default=str)
    return (row.id.hex, row.status, row.origin, row.kind, row.reason,
            _stamp(row.answered_at), payload)


def _rows(session, job_id, app_id):
    job = session.get(models.Job, job_id)
    app = session.get(models.Application, app_id)
    reqs = session.scalars(select(models.SyncRequest).order_by(models.SyncRequest.id)).all()
    return {
        "counts": _counts(session),
        "job": None if job is None else (job.title, job.owner_machine, job.handover, job.sync_rev),
        "notes": None if app is None else (app.notes, app.status, _stamp(app.updated_at)),
        "requests": [_request_row(row) for row in reqs],
    }


def _both(home, db, ids):
    db.expire_all()
    with home.session() as session:
        home_rows = _rows(session, ids.job, ids.application)
    return {"home": home_rows, "remote": _rows(db, ids.job, ids.application)}


def _body(raw):
    return raw.partition(b"\r\n\r\n")[2]


def _header_names(raw):
    head = raw.split(b"\r\n\r\n", 1)[0]
    names = set()
    for line in head.split(b"\r\n")[1:]:
        name, sep, _value = line.partition(b":")
        if sep:
            names.add(name.strip().lower().decode("latin-1"))
    return names


def _header_map(raw):
    head = raw.split(b"\r\n\r\n", 1)[0]
    found = {}
    for line in head.split(b"\r\n")[1:]:
        name, sep, value = line.partition(b":")
        if sep:
            found[name.strip().lower().decode("latin-1")] = value.strip().decode("latin-1")
    return found


def _assert_names(raw, allowed):
    extra = _header_names(raw) - allowed
    assert not extra, f"unexpected header: {sorted(extra)}"


def _request_parts(raw):
    method, target, _version = raw.split(b"\r\n", 1)[0].decode("latin-1").split(" ")
    parts = urlsplit(target)
    return method, parts.path, parts.query


def _status_of(raw):
    return int(raw.split(b" ", 2)[1])


def _ciphertext(header, body):
    if body:
        return body
    field = header.split(".")[5]
    return base64.urlsafe_b64decode(field + "=" * (-len(field) % 4))


def _direction(path, sync_key, digest):
    if path == "/api/sync/enroll":
        return digest, seal.ENROLL_TO_HOME, seal.ENROLL_TO_REMOTE
    return sync_key, seal.TO_HOME, seal.TO_REMOTE


def _open_request(secret, label, raw):
    method, path, query = _request_parts(raw)
    headers = _header_map(raw)
    body = _body(raw)
    try:
        ok = seal.check_header(
            secret, method, path, query, headers["x-maestro-seal"],
            headers["x-maestro-sync"], replay=None, label=label)
        plain = seal.open_request(secret, ok, body, label=label)
    except seal.Broken:
        raise AssertionError(f"{method} {path} did not open") from None
    if len(_ciphertext(headers["x-maestro-seal"], body)) != len(plain) + 16:
        raise AssertionError(f"{method} {path} body was not plaintext plus a tag")
    return method, path, plain


def _open_response(secret, label, request, response):
    rid = _header_map(request)["x-maestro-seal"].split(".")[2]
    headers = _header_map(response)
    body = _body(response)
    try:
        plain = seal.open_response(
            secret, rid, _status_of(response), headers["x-maestro-seal"], body, label=label)
    except seal.Broken:
        raise AssertionError("a recorded response did not open") from None
    if len(body) != len(plain) + 16:
        raise AssertionError("a recorded response body was not plaintext plus a tag")
    return plain


def _opened_pair(request, response, sync_key, digest):
    _assert_names(request, _REQUEST_HEADERS)
    _assert_names(response, _RESPONSE_HEADERS)
    path = _request_parts(request)[1]
    secret, to_home, to_remote = _direction(path, sync_key, digest)
    method, path, plain = _open_request(secret, to_home, request)
    _open_response(secret, to_remote, request, response)
    return method, path, plain


def _bundle_crossed(method, path, plain, needle):
    return method == "POST" and path == "/api/sync/jobs" and needle in plain


def _assert_exchange(pairs, sync_key, digest, bundle_file):
    routes, crossed = set(), False
    needle = base64.standard_b64encode(bundle_file)
    for request, response in pairs:
        method, path, plain = _opened_pair(request, response, sync_key, digest)
        routes.add((method, path))
        crossed = crossed or _bundle_crossed(method, path, plain, needle)
    missing = _ROUTES - routes
    assert not missing, f"routes missed the proxy: {sorted(missing)}"
    assert crossed, "the job bundle did not cross the proxy"


def _add_remote_job(db, root, title, file_bytes):
    job_id, app_id = uuid.uuid4(), uuid.uuid4()
    folder = Path(root) / "applications" / app_id.hex
    folder.mkdir(parents=True)
    (folder / "note.bin").write_bytes(file_bytes)
    db.add(models.Job(
        id=job_id, title=title, raw_text="Synthetic remote posting",
        raw_text_hash=uuid.uuid4().hex))
    db.flush()
    db.add(models.Application(
        id=app_id, job_id=job_id, base_resume="base", status="draft",
        artifact_dir=str(folder), pdf_path=str(folder / "note.bin")))
    db.commit()
    return SimpleNamespace(job=job_id, application=app_id)


def _home_title(home, job_id):
    with home.session() as session:
        job = session.get(models.Job, job_id)
        return None if job is None else job.title


def _home_bytes(home, application_id):
    with home.session() as session:
        application = session.get(models.Application, application_id)
        if application is None or not application.pdf_path:
            return None
        return Path(application.pdf_path).read_bytes()


def _retitle(db, job_id, title):
    db.get(models.Job, job_id).title = title
    db.commit()


def _edit_home_note(home, application_id):
    response = home.http.patch(
        f"/api/applications/{application_id}", json={"notes": _LATER})
    assert response.status_code == 200


def _replay_after_restart(home, db, ids, proxy, posted):
    """One fresh home process: the replay cache is empty and the skew window still holds, but
    home refuses any seal stamped before it started, so the replay is the bare 404."""
    home.stop()
    try:
        home.start()
        _edit_home_note(home, ids.application)
        before = _both(home, db, ids)
        _assert_bare(*replay_recorded(proxy, posted))
        assert _both(home, db, ids) == before, "replay after restart changed a database"
    finally:
        if home.process is None or home.process.poll() is not None:
            home.start()


def test_real_intercepting_proxy_sees_ciphertext_and_replay_changes_nothing(
        home_backend, db_session, tmp_path, monkeypatch, recording_proxy):
    """With an http:// target httpx uses the absolute-URI forward form, so the proxy
    records the request in cleartext — exactly the decrypting-proxy view we must survive."""
    _prepare_proxy_remote(monkeypatch, home_backend, tmp_path, recording_proxy)
    now = _clock(monkeypatch)
    ids = _seed_home(home_backend, _FILE)
    code = _pair_and_sync(db_session, home_backend)
    remote = _add_remote_job(db_session, tmp_path, _REMOTE_TITLE, _REMOTE_FILE)
    _queue_and_send(db_session, ids, now)
    _assert_request_landed(home_backend, db_session, ids)
    _assert_payloads_arrived(db_session, tmp_path, ids, _FILE)
    assert _home_bytes(home_backend, remote.application) == _REMOTE_FILE
    assert _home_title(home_backend, remote.job) == _REMOTE_TITLE
    pairs = recording_proxy.recorded_pairs()
    sync_key, digest = _sync_key_and_digest(home_backend, code)
    _assert_exchange(pairs, sync_key, digest, _REMOTE_FILE)
    _assert_recorded_seal(recording_proxy.transcript(), home_backend.port)
    _no_secrets(pairs, _forbidden(home_backend, code, _FILE))
    posted = _one_post(recording_proxy, home_backend.port, "/api/sync/requests")
    before = _both(home_backend, db_session, ids)
    _assert_bare(*replay_recorded(recording_proxy, posted))
    assert _both(home_backend, db_session, ids) == before
    _replay_after_restart(home_backend, db_session, ids, recording_proxy, posted)


def test_real_replayed_push_after_restart_keeps_the_newer_job(
        home_backend, db_session, tmp_path, monkeypatch, recording_proxy):
    """An old push, replayed after home restarts, must not replace a newer revision."""
    _prepare_proxy_remote(monkeypatch, home_backend, tmp_path, recording_proxy)
    now = _clock(monkeypatch)
    _seed_home(home_backend, _FILE)
    _pair_and_sync(db_session, home_backend)
    remote = _add_remote_job(db_session, tmp_path, _REMOTE_TITLE, _REMOTE_FILE)
    now.value += timedelta(minutes=31)
    pushed = sync_round.run_round(db_session, pair=True)
    assert pushed["ok"] and pushed["steps"]["push"]["sent"] == 1
    posted = _one_post(recording_proxy, home_backend.port, "/api/sync/jobs")
    _retitle(db_session, remote.job, _NEWER_TITLE)
    now.value += timedelta(minutes=31)
    again = sync_round.run_round(db_session, pair=True)
    assert again["ok"] and again["steps"]["push"]["sent"] == 1
    assert _home_title(home_backend, remote.job) == _NEWER_TITLE
    home_backend.stop()
    try:
        home_backend.start()
        _assert_bare(*replay_recorded(recording_proxy, posted))
        assert _home_title(home_backend, remote.job) == _NEWER_TITLE
    finally:
        if home_backend.process is None or home_backend.process.poll() is not None:
            home_backend.start()
