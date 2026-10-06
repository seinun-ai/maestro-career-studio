"""The always-on copy's round (Task 11): every step against a hand-written fake home.

The fake home is an ``httpx.MockTransport`` handler that calls the route functions of
``routers/sync.py`` directly, with a session on a second SQLite file; it never touches the FastAPI
app, whose ``get_db``, ``status.enabled()`` and lock are process-global. While it serves, the
process-global settings (key, remote url, file roots) are switched to home's side and back.
"""

import json
import logging
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from app import models
from app.config import settings
from app.db import Base, get_db, make_engine
from app.main import app
from app.routers import sync as sync_router
from app.services import application_status, http_client
from app.services.sync import duplicates, jobs_bundle, requests, status
from app.services.sync import round as sync_round
from tests.sync.test_jobs_bundle import SENTINEL, WHEN, build_job
from tests.sync.test_profile_bundle import build_profile

KEY = "SENTINEL-SYNC-KEY-5150-" + "k" * 24
REVISION = "rev-test-1"
ROOT_NAMES = ("applications", "base_resumes", "kb_documents")
UNREACHABLE = "Laptop unreachable."
VERSION = "Update Maestro on both machines to the same version."
BUSY_APPLYING = "Your bot is applying to this one; try again after its run."
START = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)

PATH_FUNCTIONS = {
    ("GET", "/api/sync/hello"): "hello",
    ("GET", "/api/sync/profile"): "get_profile",
    ("GET", "/api/sync/jobs"): "get_jobs",
    ("POST", "/api/sync/jobs"): "post_jobs",
    ("POST", "/api/sync/ownership"): "post_ownership",
    ("GET", "/api/sync/requests"): "get_requests",
    ("POST", "/api/sync/requests"): "post_requests",
    ("POST", "/api/sync/request-results"): "post_request_results",
    ("GET", "/api/sync/handover/offers"): "get_offers",
    ("POST", "/api/sync/handover/commit"): "post_commit",
    ("POST", "/api/sync/handover/return"): "post_return",
    ("POST", "/api/sync/runs"): "post_runs",
}


class World:
    """Two copies, each with its own database and file roots; the process is on one side at a time."""

    def __init__(self, tmp_path, monkeypatch):
        self.mp, self.tmp = monkeypatch, tmp_path
        self.key = tmp_path / "key"
        self.key.write_text(KEY, encoding="utf-8")
        self.key.chmod(0o600)
        self.engines, self.factories = {}, {}
        for side in ("home", "remote"):
            for name in (*ROOT_NAMES, "settings"):
                (tmp_path / side / name).mkdir(parents=True)
            engine = make_engine(f"sqlite:///{tmp_path / side}.sqlite3")
            Base.metadata.create_all(engine)
            with engine.begin() as connection:
                connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
                connection.execute(text("INSERT INTO alembic_version VALUES (:v)"), {"v": REVISION})
            self.engines[side] = engine
            self.factories[side] = sessionmaker(bind=engine, autoflush=False)
        self.home, self.remote = self.factories["home"](), self.factories["remote"]()
        self.now = (None, None)
        self._set("remote", "remote")

    def close(self):
        self.home.close()
        self.remote.close()
        for engine in self.engines.values():
            engine.dispose()

    def _set(self, side, mode):
        for name in ROOT_NAMES:
            self.mp.setattr(settings, f"{name}_dir", self.tmp / side / name)
        self.mp.setattr(settings, "settings_dir", self.tmp / side / "settings")
        keyed = mode != "off"
        self.mp.setattr(settings, "sync_key_file", self.key if keyed else self.tmp / "no-key")
        self.mp.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101" if mode == "remote" else "")
        self.now = (side, mode)

    @contextmanager
    def using(self, side, mode):
        before = self.now
        self._set(side, mode)
        try:
            yield
        finally:
            self._set(*before)

    def as_(self, side):
        return self.using(side, side)

    def building(self, side):
        """Sync off, this side's roots: set up rows the guard would refuse."""
        return self.using(side, "off")

    def root(self, side):
        return self.tmp / side / "applications"

    def at(self, side, name):
        return self.tmp / side / name

    def machine_id(self, side):
        db = getattr(self, side)
        value = status.machine_id(db)
        db.commit()
        return value

    def seen(self, side):
        db = getattr(self, side)
        db.rollback()
        db.expire_all()
        return db


class FakeHome:
    """What the laptop's endpoints answer, with switches to break the line."""

    def __init__(self, world):
        self.world = world
        self.calls: list[tuple[str, str]] = []
        self.unreachable: set[tuple[str, str]] = set()
        self.lose_reply: set[tuple[str, str]] = set()
        self.reply: dict[tuple[str, str], httpx.Response] = {}
        self.hello_patch: dict = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        key = (request.method, request.url.path)
        self.calls.append(key)
        if key in self.unreachable:
            raise httpx.ConnectError("down", request=request)
        if key in self.reply:
            return self.reply[key]
        with self.world.as_("home"):
            response = self._serve(request, key)
        if key in self.lose_reply:
            raise httpx.ReadError("lost", request=request)
        return response

    def posts(self, path=None):
        return [call for call in self.calls
                if call[0] == "POST" and (path is None or call[1] == path)]

    def _serve(self, request, key):
        if request.headers.get("authorization") != f"Bearer {KEY}":
            return httpx.Response(401, json={"detail": "A sync key is needed."})
        protocol, revision, remote_id = request.headers["x-maestro-sync"].split(":")
        with self.world.factories["home"]() as db:
            if protocol != str(status.SYNC_PROTOCOL) or revision != db.scalar(
                    text("SELECT version_num FROM alembic_version")):
                return httpx.Response(409, json={"detail": VERSION, "reason": "version"})
            status.machine_id(db)
            db.commit()  # as the real dependency does: the first call stores home's id
            return self._route(request, key, sync_router.PeerInfo(remote_id), db)

    def _route(self, request, key, peer, db):
        function = getattr(sync_router, PATH_FUNCTIONS[key])
        params = dict(request.url.params)
        try:
            if key == ("GET", "/api/sync/profile"):
                answer = function(peer, db, since=int(params["since"]) if "since" in params else None)
            elif key == ("GET", "/api/sync/jobs"):
                answer = function(peer, db, since=params["since"], limit=int(params["limit"]))
            elif request.method == "POST":
                answer = function(peer, db, json.loads(request.content))
            else:
                answer = function(peer, db)
        except HTTPException as refusal:
            return httpx.Response(refusal.status_code, json={"detail": refusal.detail})
        if key == ("GET", "/api/sync/hello"):
            answer = {**answer, **self.hello_patch}
        return httpx.Response(200, json=answer)


@pytest.fixture
def world(tmp_path, monkeypatch):
    built = World(tmp_path, monkeypatch)
    yield built
    built.close()


@pytest.fixture
def home(world, monkeypatch):
    fake = FakeHome(world)
    real = http_client.new_client
    monkeypatch.setattr(http_client, "new_client",
                        lambda **kwargs: real(transport=httpx.MockTransport(fake), **kwargs))
    return fake


@pytest.fixture
def clock(monkeypatch):
    time = SimpleNamespace(now=START)
    monkeypatch.setattr(sync_round, "_now", lambda: time.now)
    return time


def go(world, **kwargs):
    kwargs.setdefault("pair", True)
    return sync_round.run_round(world.remote, **kwargs)


def state(world):
    world.remote.rollback()
    return status.read_state(world.remote)


def job_of(world, side, job_id):
    return world.seen(side).get(models.Job, job_id)


def lone_job(world, side, *, hash_=None, application=False):
    """A job with no work on it, or with one application (progressed)."""
    job_id = uuid.uuid4()
    with world.building(side):
        db = getattr(world, side)
        db.add(models.Job(id=job_id, raw_text=f"Posting {SENTINEL}",
                          raw_text_hash=hash_ or uuid.uuid4().hex, title="Role", created_at=WHEN))
        db.flush()
        if application:
            db.add(models.Application(id=uuid.uuid4(), job_id=job_id, base_resume="base",
                                      status="saved", created_at=WHEN, updated_at=WHEN))
        db.commit()
    return job_id


def full_job(world, side, tag):
    with world.building(side):
        return build_job(getattr(world, side), world.root(side), tag=tag).job


def add_run(world, when=WHEN):
    with world.building("remote"):
        run_id = uuid.uuid4()
        world.remote.add(models.AgentRun(id=run_id, automation="apply", outcome="ok",
                                         finished_at=when, counts={"found": 1}, digest="done"))
        world.remote.commit()
    return run_id


def retry_after_backoff(clock, world):
    clock.now = datetime.fromisoformat(state(world)["next_attempt_at"])


# ------------------------------------------------------------------------------ the happy path


def test_a_full_round(world, home, clock, caplog):
    caplog.set_level(logging.DEBUG)
    with world.building("home"):
        build_profile(world.home, world)
    home_job = full_job(world, "home", "h")
    own_job = full_job(world, "remote", "r")
    run_id = add_run(world)
    own_rev = job_of(world, "remote", own_job).sync_rev
    remote_id, home_id = world.machine_id("remote"), world.machine_id("home")

    summary = go(world)

    assert summary["ok"] is True, summary
    steps = summary["steps"]
    assert steps["profile"]["applied"] == 1
    assert (steps["push"]["sent"], steps["pull"]["applied"], steps["runs"]["sent"]) == (1, 1, 1)
    assert world.seen("remote").get(models.BaseResume, "data_scientist") is not None
    replica = job_of(world, "remote", home_job)
    assert replica.owner_machine == home_id
    at_home = job_of(world, "home", own_job)
    assert at_home.owner_machine == remote_id
    assert (world.root("home") / "Co_Role_r" / "resume.pdf").read_bytes() == b"%PDF r"
    assert (world.root("remote") / "Co_Role_h" / "resume.pdf").read_bytes() == b"%PDF h"
    assert world.seen("home").get(models.AgentRun, run_id).machine == remote_id
    saved = state(world)
    assert (saved["paired"], saved["failures"], saved["last_error"]) == (True, 0, None)
    assert saved["last_ok"] == START.isoformat()
    assert saved["acked_own"] == own_rev and saved["since_home"] != "0"
    assert isinstance(saved["profile_rev"], int)
    blob = json.dumps(summary) + json.dumps(saved)
    assert KEY not in blob and KEY not in caplog.text and SENTINEL not in blob


def test_the_second_round_sends_nothing(world, home, clock):
    full_job(world, "home", "h")
    full_job(world, "remote", "r")
    add_run(world)
    first = go(world)
    assert first["ok"], first
    home.calls.clear()

    summary = go(world)

    # the ownership question about the home jobs held here is a read; nothing else goes out
    assert summary["ok"] and home.posts() == [("POST", "/api/sync/ownership")]
    assert summary["steps"]["push"]["sent"] == summary["steps"]["pull"]["applied"] == 0


def test_a_first_round_needs_the_pair_flag(world, home, clock):
    summary = go(world, pair=False)

    assert summary["ok"] is False and "paired" in summary["skipped"]
    assert home.calls == [("GET", "/api/sync/hello")]
    assert state(world)["paired"] is False
    assert go(world, pair=True)["ok"] and state(world)["paired"] is True
    assert go(world, pair=False)["ok"]


def test_a_round_without_a_key_says_sync_is_not_set_up(world, home, clock):
    with world.building("remote"):
        assert go(world)["skipped"] == "Sync isn't set up."
    assert home.calls == []


# ----------------------------------------------------------------------- failing and backing off


def test_a_failure_in_the_pull_keeps_the_pushes_ack(world, home, clock):
    full_job(world, "home", "h")
    own_job = full_job(world, "remote", "r")
    own_rev = job_of(world, "remote", own_job).sync_rev
    home.unreachable.add(("GET", "/api/sync/jobs"))

    summary = go(world)

    assert summary["ok"] is False and summary["error"] == UNREACHABLE
    saved = state(world)
    assert saved["acked_own"] == own_rev
    assert saved["since_home"] == "0"
    assert saved["failures"] == 1 and saved["last_error"] == UNREACHABLE
    assert job_of(world, "home", own_job) is not None


def test_backoff_doubles_up_to_thirty_minutes_and_a_success_resets_it(world, home, clock):
    home.unreachable.add(("GET", "/api/sync/hello"))
    delays = []
    for _ in range(6):
        assert go(world)["ok"] is False
        delays.append((datetime.fromisoformat(state(world)["next_attempt_at"]) - clock.now)
                      / timedelta(minutes=1))
        retry_after_backoff(clock, world)
    assert delays == [5, 10, 20, 30, 30, 30]
    assert state(world)["failures"] == 6

    home.unreachable.clear()
    assert go(world)["ok"]
    saved = state(world)
    assert (saved["failures"], saved["next_attempt_at"]) == (0, None)


def test_a_round_inside_the_backoff_window_is_skipped_and_force_ignores_it(world, home, clock):
    home.unreachable.add(("GET", "/api/sync/hello"))
    go(world)
    home.calls.clear()
    clock.now += timedelta(minutes=1)

    skipped = go(world)

    assert skipped["ok"] is False and "next try at" in skipped["skipped"].lower()
    assert home.calls == [] and state(world)["failures"] == 1
    forced = go(world, force=True)
    assert forced["ok"] is False and home.calls == [("GET", "/api/sync/hello")]
    assert state(world)["failures"] == 2


def test_a_version_mismatch_skips_the_round_and_changes_nothing(world, home, clock):
    lone_job(world, "home")
    mine = lone_job(world, "remote")
    world.home.execute(text("UPDATE alembic_version SET version_num = 'other'"))
    world.home.commit()

    summary = go(world)

    assert summary == {"ok": False, "skipped": VERSION}
    assert home.calls == [("GET", "/api/sync/hello")]
    assert world.seen("remote").get(models.Setting, status.STATE_KEY) is None
    assert job_of(world, "remote", mine).owner_machine is None
    assert [call for call in home.calls if call[0] == "POST"] == []


def test_a_hello_that_names_another_protocol_is_a_mismatch_too(world, home, clock):
    home.hello_patch = {"protocol": status.SYNC_PROTOCOL + 1}

    assert go(world) == {"ok": False, "skipped": VERSION}
    assert world.seen("remote").get(models.Setting, status.STATE_KEY) is None


def test_a_422_is_reported_by_code_never_by_its_body(world, home, clock, caplog):
    caplog.set_level(logging.DEBUG)
    full_job(world, "remote", "r")
    body = {"detail": [{"input": SENTINEL, "msg": SENTINEL}]}
    home.reply[("POST", "/api/sync/jobs")] = httpx.Response(422, json=body)

    summary = go(world)

    assert summary["ok"] is False and summary["error"].startswith("422")
    saved = state(world)
    raw = world.seen("remote").get(models.Setting, status.STATE_KEY).value
    for place in (summary["error"], saved["last_error"], raw, caplog.text, json.dumps(summary)):
        assert SENTINEL not in place and KEY not in place


def test_a_wrong_key_is_reported_as_a_key_problem(world, home, clock):
    world.key.write_text("a-different-key", encoding="utf-8")
    home.reply[("GET", "/api/sync/hello")] = httpx.Response(401, json={"detail": SENTINEL})

    summary = go(world)

    assert summary["error"] == "401: Sync key doesn't match."
    assert state(world)["failures"] == 1


def test_a_disk_error_while_applying_is_a_fixed_sentence(world, home, clock, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    full_job(world, "home", "h")

    def full(*args, **kwargs):
        raise OSError(28, "No space left", f"/secret/{SENTINEL}/file")

    monkeypatch.setattr(jobs_bundle, "apply_job", full)

    summary = go(world)

    assert summary["error"] == "Maestro couldn't save the files it received."
    saved = state(world)
    assert saved["last_error"] == summary["error"] and saved["failures"] == 1
    assert SENTINEL not in json.dumps(summary) + json.dumps(saved) + caplog.text
    assert saved["since_home"] == "0"


# ----------------------------------------------------------------------------------- pushing


def test_pages_are_cut_by_bytes_and_the_ack_follows_each_page(world, home, clock, monkeypatch):
    monkeypatch.setattr(sync_round, "PAGE_BYTES", 1)
    ids = [full_job(world, "remote", tag) for tag in "abc"]
    top = max(job_of(world, "remote", job_id).sync_rev for job_id in ids)

    summary = go(world)

    assert summary["steps"]["push"]["sent"] == 3
    assert len(home.posts("/api/sync/jobs")) == 3
    assert state(world)["acked_own"] == top
    assert all(job_of(world, "home", job_id) is not None for job_id in ids)


def test_a_refused_job_holds_the_ack_just_below_its_revision(world, home, clock):
    first, second = full_job(world, "remote", "one"), full_job(world, "remote", "two")
    first_rev = job_of(world, "remote", first).sync_rev
    with world.building("remote"):
        bundle = jobs_bundle.export_job(world.remote, first)
    with world.as_("home"):  # home already holds this job as its own: it refuses the push
        jobs_bundle.apply_job(world.home, bundle, sender_machine=world.machine_id("home"))

    summary = go(world)

    assert summary["ok"] and summary["steps"]["push"]["refused"] == 1
    assert state(world)["acked_own"] == first_rev - 1
    assert job_of(world, "home", second).owner_machine == world.machine_id("remote")


def test_an_own_job_too_large_to_send_is_skipped_and_the_round_goes_on(world, home, clock,
                                                                       monkeypatch):
    big = full_job(world, "remote", "big")
    rev = job_of(world, "remote", big).sync_rev
    monkeypatch.setattr(jobs_bundle, "DEFAULT_MAX_BYTES", 5)

    summary = go(world)

    assert summary["ok"] and summary["steps"]["push"]["skipped"] == 1
    assert home.posts("/api/sync/jobs") == [] and state(world)["acked_own"] == rev


def test_a_deleted_own_job_is_deleted_at_home_too(world, home, clock):
    gone = full_job(world, "remote", "r")
    assert go(world)["ok"] and job_of(world, "home", gone) is not None
    with world.building("remote"):
        world.remote.delete(world.remote.get(models.Job, gone))
        world.remote.commit()

    assert go(world)["ok"]

    assert job_of(world, "home", gone) is None


# --------------------------------------------------------------------------------- duplicates


def test_a_push_the_laptop_already_holds_unworked_drops_the_remote_job(world, home, clock):
    mine = lone_job(world, "remote", hash_="same-text")
    theirs = lone_job(world, "home", hash_="same-text")

    summary = go(world)

    assert summary["steps"]["push"]["dropped"] == 1
    assert job_of(world, "remote", mine) is None
    assert job_of(world, "remote", theirs).owner_machine == world.machine_id("home")
    assert job_of(world, "home", mine) is None


def test_a_job_with_work_on_it_is_kept_on_both_sides_under_a_replica_hash(world, home, clock):
    mine = lone_job(world, "remote", hash_="same-text", application=True)
    theirs = lone_job(world, "home", hash_="same-text")

    summary = go(world)

    assert summary["steps"]["push"]["kept_both"] == 1 and summary["steps"]["pull"]["kept_both"] == 1
    assert job_of(world, "remote", mine).owner_machine is None
    assert job_of(world, "remote", mine).raw_text_hash == "same-text"
    assert job_of(world, "remote", theirs).raw_text_hash == duplicates.replica_hash(theirs)
    assert job_of(world, "home", mine).raw_text_hash == duplicates.replica_hash(mine)
    assert job_of(world, "home", theirs).raw_text_hash == "same-text"
    assert go(world)["ok"]  # and the rewritten hash keeps applying


def test_a_pulled_job_whose_text_an_unworked_remote_job_holds_replaces_it(world, home, clock):
    mine = lone_job(world, "remote", hash_="same-text")
    theirs = lone_job(world, "home", hash_="same-text")
    status.update_state(world.remote, acked_own=10**6)  # the remote's copy was not pushed first

    summary = go(world)

    assert summary["steps"]["pull"]["dropped"] == 1
    assert job_of(world, "remote", mine) is None
    assert job_of(world, "remote", theirs).owner_machine == world.machine_id("home")


# ------------------------------------------------------------------------------------ pulling


def test_a_job_too_large_to_apply_is_skipped_and_never_stops_the_round(world, home, clock,
                                                                       monkeypatch):
    big = full_job(world, "home", "big")
    monkeypatch.setattr(jobs_bundle, "DEFAULT_MAX_BYTES", 5)

    summary = go(world)

    assert summary["ok"] and summary["steps"]["pull"]["skipped"] == 1
    assert job_of(world, "remote", big) is None
    assert state(world)["since_home"] != "0"


def test_a_deleted_home_job_is_deleted_here_but_never_an_own_job(world, home, clock):
    theirs = full_job(world, "home", "h")
    mine = full_job(world, "remote", "r")
    assert go(world)["ok"] and job_of(world, "remote", theirs) is not None
    with world.building("home"):
        world.home.delete(world.home.get(models.Job, theirs))
        world.home.commit()

    assert go(world)["ok"]

    assert job_of(world, "remote", theirs) is None and job_of(world, "remote", mine) is not None


# ---------------------------------------------------------------------------------- handovers


def test_an_offer_committed_at_home_is_healed_when_the_reply_is_lost(world, home, clock):
    offered = lone_job(world, "home")
    with world.building("home"):
        world.home.get(models.Job, offered).handover = "offered"
        world.home.commit()
    home.lose_reply.add(("POST", "/api/sync/handover/commit"))

    assert go(world)["ok"] is False

    remote_id, home_id = world.machine_id("remote"), world.machine_id("home")
    assert job_of(world, "home", offered).owner_machine == remote_id
    assert job_of(world, "remote", offered).owner_machine == home_id  # the local flip never ran
    home.lose_reply.clear()
    retry_after_backoff(clock, world)

    summary = go(world)

    assert summary["ok"] and summary["steps"]["reconcile"]["owned"] == 1
    here = job_of(world, "remote", offered)
    assert (here.owner_machine, here.handover) == (None, None)


def test_an_offer_is_taken_and_owned_in_one_round(world, home, clock):
    offered = lone_job(world, "home")
    with world.building("home"):
        world.home.get(models.Job, offered).handover = "offered"
        world.home.commit()

    summary = go(world)

    assert summary["steps"]["handovers"]["taken"] == 1
    here = job_of(world, "remote", offered)
    assert (here.owner_machine, here.handover) == (None, None)
    assert job_of(world, "home", offered).owner_machine == world.machine_id("remote")


def _ask_for_it_back(world, job_id):
    with world.as_("home"):
        return requests.enqueue_take_over(world.home, job_id).id


def test_a_return_is_granted_when_the_bot_is_not_applying(world, home, clock):
    job = full_job(world, "remote", "r")
    assert go(world)["ok"]
    request_id = _ask_for_it_back(world, job)

    summary = go(world)

    assert summary["steps"]["handovers"]["returned"] == 1
    assert job_of(world, "home", job).owner_machine is None
    here = job_of(world, "remote", job)
    assert (here.owner_machine, here.handover) == (world.machine_id("home"), None)
    answered = world.seen("home").get(models.SyncRequest, request_id)
    assert (answered.status, answered.reason) == ("applied", None)


def test_a_return_is_refused_while_a_proposal_is_approved(world, home, clock):
    job = full_job(world, "remote", "r")
    assert go(world)["ok"]
    with world.building("remote"):
        proposal = world.remote.scalars(select(models.ApplicationProposal)).one()
        proposal.status = "approved"
        world.remote.commit()
    request_id = _ask_for_it_back(world, job)

    summary = go(world)

    assert summary["steps"]["handovers"]["refused"] == 1
    assert job_of(world, "remote", job).owner_machine is None
    assert job_of(world, "home", job).owner_machine == world.machine_id("remote")
    answered = world.seen("home").get(models.SyncRequest, request_id)
    assert (answered.status, answered.reason) == ("refused", BUSY_APPLYING)


# ------------------------------------------------------------------------------------ requests


def _notes_request(world, side, job_id, application_id, notes):
    with world.as_(side):
        return requests.enqueue(getattr(world, side), "application_patch", job_id,
                                {"application_id": str(application_id),
                                 "fields": {"notes": notes}}).id


def _application_of(world, side, job_id):
    return world.seen(side).scalars(select(models.Application).where(
        models.Application.job_id == job_id, models.Application.status == "saved")).first()


def test_a_request_for_a_home_job_is_sent_and_its_answer_stored(world, home, clock):
    theirs = full_job(world, "home", "h")
    assert go(world)["ok"]
    application = _application_of(world, "home", theirs)
    request_id = _notes_request(world, "remote", theirs, application.id, "from the bot")

    summary = go(world)

    assert summary["steps"]["requests"]["sent"] == 1
    assert _application_of(world, "home", theirs).notes == "from the bot"
    stored = world.seen("remote").get(models.SyncRequest, request_id)
    assert stored.status == "applied" and stored.answered_at is not None
    assert go(world)["steps"]["requests"]["sent"] == 0


def test_a_pending_request_for_a_job_now_owned_here_is_applied_here_not_sent(world, home, clock):
    mine = full_job(world, "remote", "r")
    application = _application_of(world, "remote", mine)
    request_id = _notes_request(world, "remote", mine, application.id, "kept local")
    # the guard would queue this for a replica; the job became ours since, so it is a plain request
    summary = go(world)

    assert summary["steps"]["requests"]["applied_here"] == 1
    assert home.posts("/api/sync/requests") == []
    assert _application_of(world, "remote", mine).notes == "kept local"
    assert world.seen("remote").get(models.SyncRequest, request_id).status == "applied"


def test_a_repeated_home_request_is_answered_from_the_record_without_applying_twice(
        world, home, clock, monkeypatch):
    job = full_job(world, "remote", "r")
    assert go(world)["ok"]
    application = _application_of(world, "remote", job)
    request_id = _notes_request(world, "home", job, application.id, "once")
    applied = []
    real = application_status.apply_status_and_notes

    def counted(*args, **kwargs):
        applied.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(application_status, "apply_status_and_notes", counted)
    home.unreachable.add(("POST", "/api/sync/request-results"))

    assert go(world)["ok"] is False
    assert len(applied) == 1
    assert world.seen("home").get(models.SyncRequest, request_id).status == "sent"
    recorded = world.seen("remote").get(models.SyncRequest, request_id)
    assert (recorded.origin, recorded.status) == ("remote", "applied")
    home.unreachable.clear()
    retry_after_backoff(clock, world)

    assert go(world)["ok"]

    assert len(applied) == 1
    assert world.seen("home").get(models.SyncRequest, request_id).status == "applied"


def test_a_request_on_a_job_the_laptop_has_offered_is_refused_and_the_job_still_arrives(
        world, home, clock):
    theirs = full_job(world, "home", "h")
    assert go(world)["ok"]
    application = _application_of(world, "home", theirs)
    request_id = _notes_request(world, "remote", theirs, application.id, "too late")
    with world.building("home"):
        world.home.get(models.Job, theirs).handover = "offered"
        world.home.commit()

    summary = go(world)

    assert summary["steps"]["requests"]["refused"] == 1 and summary["steps"]["handovers"]["taken"] == 1
    stored = world.seen("remote").get(models.SyncRequest, request_id)
    assert stored.status == "refused" and "moving to your bot" in stored.reason
    assert job_of(world, "remote", theirs).owner_machine is None


def test_a_home_request_the_rules_refuse_is_answered_with_the_reason(world, home, clock):
    job = full_job(world, "remote", "r")
    assert go(world)["ok"]
    application = _application_of(world, "remote", job)
    with world.as_("home"):
        request_id = requests.enqueue(world.home, "application_patch", job,
                                      {"application_id": str(application.id),
                                       "fields": {"status": "no-such-status"}}).id

    summary = go(world)

    assert summary["steps"]["requests"]["refused"] == 1
    answered = world.seen("home").get(models.SyncRequest, request_id)
    assert answered.status == "refused" and answered.reason


# ----------------------------------------------------------------------------------- the route


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
def recorded_rounds(monkeypatch):
    calls = []

    def fake(db, **kwargs):
        calls.append(kwargs)
        return {"ok": True, "steps": {"push": {"sent": 2}}}

    monkeypatch.setattr(sync_round, "run_round", fake)
    return calls


def test_the_round_route_is_a_404_with_sync_off(client, recorded_rounds):
    assert client.post("/api/sync/round").status_code == 404
    assert recorded_rounds == []


def test_the_round_route_is_a_404_on_home(client, sync_on, recorded_rounds):
    assert client.post("/api/sync/round").status_code == 404


def test_the_round_route_refuses_an_origin(client, sync_remote, recorded_rounds):
    response = client.post("/api/sync/round", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 403 and recorded_rounds == []


def test_the_round_route_needs_no_key_and_returns_the_summary(client, sync_remote, recorded_rounds):
    response = client.post("/api/sync/round")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "steps": {"push": {"sent": 2}}}
    assert recorded_rounds == [{"force": False, "pair": False, "accept_profile_overwrite": False}]


def test_the_round_route_passes_the_flags_on(client, sync_remote, recorded_rounds):
    body = {"force": True, "pair": True, "accept_profile_overwrite": True}

    assert client.post("/api/sync/round", json=body).status_code == 200
    assert recorded_rounds == [body]


def test_the_round_route_rejects_a_bad_body_without_echoing_it(client, sync_remote, recorded_rounds):
    response = client.post("/api/sync/round", json={"force": SENTINEL})

    assert response.status_code == 422 and SENTINEL not in response.text


def test_a_second_round_at_once_is_a_409(client, sync_remote, monkeypatch):
    def busy(db, **kwargs):
        raise sync_round.RoundBusy

    monkeypatch.setattr(sync_round, "run_round", busy)

    response = client.post("/api/sync/round")

    assert (response.status_code, response.json()["detail"]) == (409, "A sync is already running.")


def test_run_round_holds_one_round_at_a_time(world, home, clock):
    assert sync_round._LOCK.acquire(blocking=False)
    try:
        with pytest.raises(sync_round.RoundBusy):
            go(world)
    finally:
        sync_round._LOCK.release()
    assert home.calls == [] and go(world)["ok"]
