"""Pairing regressions plus the real laptop process / in-process remote contract.

The process tests deliberately aren't slow: they need no downloads and belong in CI.
The pairing regressions also run without sockets, using Task 11's fake channel.
"""

import json
import socket
import time
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text

from app import models
from app.config import settings
from app.db import get_db
from app.main import app
from app.services import base_resume_data, proposals, seeding, tailoring_session
from app.services.sync import jobs_bundle, profile_bundle, request_apply, seal, status
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
    assert result["outcome"] == "transient"
    assert result["error"] == "The laptop's answer couldn't be verified."
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
    assert browser.status_code == 403 and "x-maestro-seal" not in browser.headers
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
