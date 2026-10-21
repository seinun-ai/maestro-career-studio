"""The application status-event log: one dated row per status change (docs/entities/application.md).

The table, its migration and backfill; then the one writer, `application_status.set_status`, which
every path that changes a status goes through.
"""

import ast
from contextlib import closing, contextmanager
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sqlite3
from types import SimpleNamespace
import uuid

from alembic import command
from alembic.config import Config
import pytest
import sqlalchemy as sa

from app import models
from app.config import settings
from app.services.sync import hooks, status as sync_status

BEFORE = "ff9591f140f7"
REVISION = "c5b4833bcc54"
STAMP = "2026-09-01 10:00:00.000000"


def _config(path: Path) -> Config:
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    return cfg


def _tables(db) -> set[str]:
    return {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


# ---------------------------------------------------------------------------- the table


def test_a_fresh_database_has_the_table_its_index_and_a_cascading_link(_test_engine):
    inspector = sa.inspect(_test_engine)
    columns = {column["name"]: column for column in inspector.get_columns("application_status_events")}
    assert set(columns) == {"id", "application_id", "from_status", "to_status", "at", "source",
                            "backfilled"}
    assert not columns["to_status"]["nullable"] and columns["from_status"]["nullable"]
    assert not columns["at"]["nullable"] and not columns["source"]["nullable"]
    indexes = {index["name"]: index["column_names"]
               for index in inspector.get_indexes("application_status_events")}
    assert indexes["ix_status_events_app_at"] == ["application_id", "at"]
    (link,) = inspector.get_foreign_keys("application_status_events")
    assert link["referred_table"] == "applications" and link["options"]["ondelete"] == "CASCADE"


def _job_and_application(db, **fields):
    job = models.Job(id=uuid.uuid4(), raw_text="Example role", raw_text_hash=uuid.uuid4().hex)
    db.add(job)
    db.flush()
    application = models.Application(id=uuid.uuid4(), job_id=job.id, base_resume="base", **fields)
    db.add(application)
    db.flush()
    return job, application


def _event(application, to_status="applied", **fields):
    return models.ApplicationStatusEvent(application_id=application.id, to_status=to_status,
                                         source="you", **fields)


def test_an_event_stores_an_aware_time_and_is_not_backfilled_by_default(db_session):
    _, application = _job_and_application(db_session)
    db_session.add(_event(application, from_status="draft"))
    db_session.commit()
    db_session.expire_all()
    (row,) = db_session.scalars(sa.select(models.ApplicationStatusEvent)).all()
    assert (row.from_status, row.to_status, row.source, row.backfilled) == ("draft", "applied", "you", False)
    assert row.at.tzinfo is not None


def test_deleting_an_application_deletes_its_events(db_session):
    _, application = _job_and_application(db_session)
    db_session.add_all([_event(application), _event(application, "interviewing")])
    db_session.commit()
    db_session.delete(application)
    db_session.commit()
    assert db_session.scalar(sa.select(sa.func.count()).select_from(models.ApplicationStatusEvent)) == 0


def test_deleting_a_job_deletes_its_applications_events(db_session):
    job, application = _job_and_application(db_session)
    db_session.add(_event(application))
    db_session.commit()
    db_session.delete(job)
    db_session.commit()
    assert db_session.scalar(sa.select(sa.func.count()).select_from(models.ApplicationStatusEvent)) == 0


def test_an_event_belongs_to_its_applications_job_under_sync(db_session, tmp_path, monkeypatch):
    """The flush guard ties the row to its job: allowed on this copy's job and stamped, refused on a
    replica (SYSTEM.md {#inv-flush-guard})."""
    monkeypatch.setattr(settings, "settings_dir", tmp_path / "settings")
    monkeypatch.setattr(settings, "sync_key_file", tmp_path / "absent-key")
    monkeypatch.setattr(settings, "sync_remote_url", "")
    job, application = _job_and_application(db_session)
    replica = models.Job(id=uuid.uuid4(), raw_text="Other role", raw_text_hash=uuid.uuid4().hex,
                         owner_machine="other-machine")
    db_session.add(replica)
    db_session.flush()
    theirs = models.Application(id=uuid.uuid4(), job_id=replica.id, base_resume="base")
    db_session.add(theirs)
    db_session.commit()
    sync_status.create_key()

    before = job.sync_rev
    db_session.add(_event(application))
    db_session.commit()
    assert job.sync_rev > before

    db_session.add(_event(theirs))
    try:
        db_session.flush()
    except hooks.NotOwnedHere:
        db_session.rollback()
    else:
        raise AssertionError("an event on the other copy's job was written")


# ---------------------------------------------------------------------------- the migration


def _seed_before(path: Path) -> dict[str, str | None]:
    """Applications at the revision before the log: three with a status, two without."""
    statuses = {"applied": "applied", "draft": "draft", "rejected": "rejected", "none-a": None,
                "none-b": None}
    with closing(sqlite3.connect(path)) as db:
        job_id = uuid.uuid4().hex
        db.execute("INSERT INTO jobs (id, raw_text, raw_text_hash) VALUES (?, 'jd', 'hash-1')",
                   (job_id,))
        for name, value in statuses.items():
            db.execute(
                "INSERT INTO applications (id, job_id, base_resume, status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, job_id, name, value, STAMP, f"2026-09-0{len(name) % 9 + 1} 08:30:00.000000"),
            )
        db.commit()
    return statuses


def test_the_migration_backfills_one_marked_event_per_status_and_round_trips(tmp_path):
    path = tmp_path / "events.sqlite3"
    cfg = _config(path)
    command.upgrade(cfg, BEFORE)
    statuses = _seed_before(path)

    command.upgrade(cfg, REVISION)
    with closing(sqlite3.connect(path)) as db:
        rows = db.execute(
            "SELECT a.base_resume, e.from_status, e.to_status, e.at = a.updated_at, e.source,"
            " e.backfilled, length(e.id) FROM application_status_events e"
            " JOIN applications a ON a.id = e.application_id ORDER BY a.base_resume"
        ).fetchall()
    with_status = sorted(name for name, value in statuses.items() if value)
    assert [row[0] for row in rows] == with_status
    for name, from_status, to_status, same_time, source, backfilled, id_length in rows:
        assert (from_status, to_status, same_time, source, backfilled, id_length) == (
            None, statuses[name], 1, "backfill", 1, 32), name

    command.downgrade(cfg, BEFORE)
    with closing(sqlite3.connect(path)) as db:
        assert "application_status_events" not in _tables(db)
        assert db.execute("SELECT count(*) FROM applications").fetchone() == (len(statuses),)

    command.upgrade(cfg, "head")
    with closing(sqlite3.connect(path)) as db:
        assert "application_status_events" in _tables(db)
        assert db.execute("SELECT count(*) FROM application_status_events").fetchone() == (
            len(with_status),)


# ---------------------------------------------------------------------------- set_status

BACKEND = Path(__file__).resolve().parents[1]
EXT = {"Origin": "chrome-extension://abcdefghijklmnopabcdefghijklmnop"}
MCP = {"X-Maestro-CS-Origin": "mcp", "X-Maestro-CS-Origin-Detail": "claude-ai"}
RESUME = {"contact": {"name": "Example Applicant", "email": "applicant@example.test"},
          "summary": "Original summary", "skills": [{"category": "Tools", "items": ["Python"]}]}


def _events(db, application) -> list[tuple]:
    db.expire_all()
    rows = db.scalars(sa.select(models.ApplicationStatusEvent)
                      .where(models.ApplicationStatusEvent.application_id == application.id)
                      .order_by(models.ApplicationStatusEvent.at, models.ApplicationStatusEvent.id))
    return [(row.from_status, row.to_status, row.source, row.backfilled) for row in rows]


@pytest.fixture
def draft(db_session):
    _, application = _job_and_application(db_session, status="draft")
    db_session.commit()
    return application


def _fake_ctx(name: str):
    return SimpleNamespace(session=SimpleNamespace(
        client_params=SimpleNamespace(clientInfo=SimpleNamespace(name=name))))


@pytest.fixture
def mcp_tools(client, monkeypatch):
    """The MCP server's own tool functions, talking to this test's app in process."""
    from mcp_server import client as mcp_client
    from mcp_server import server as srv

    @contextmanager
    def in_process(**_):
        yield client

    monkeypatch.setattr(mcp_client, "new_client", in_process)
    monkeypatch.setattr(srv, "_client", mcp_client.BackendClient("http://testserver"))
    return srv


def test_a_status_change_on_the_web_writes_one_event_said_by_you(client, db_session, draft):
    response = client.patch(f"/api/applications/{draft.id}", json={"status": "applied"})
    assert response.status_code == 200, response.text
    assert _events(db_session, draft) == [("draft", "applied", "you", False)]


def test_the_same_status_again_or_a_notes_edit_writes_nothing(client, db_session, draft):
    for body in ({"status": "applied"}, {"status": "applied"}, {"notes": "Called back"}):
        assert client.patch(f"/api/applications/{draft.id}", json=body).status_code == 200
    assert _events(db_session, draft) == [("draft", "applied", "you", False)]


def test_an_agents_change_is_said_by_its_client_name(client, db_session, draft):
    response = client.patch(f"/api/applications/{draft.id}", json={"status": "interviewing"},
                            headers=MCP)
    assert response.status_code == 200, response.text
    assert _events(db_session, draft) == [("draft", "interviewing", "claude-ai", False)]


def test_the_mcp_update_tool_names_its_client(mcp_tools, db_session, draft):
    mcp_tools.update_application(str(draft.id), status="interviewing", ctx=_fake_ctx("codex-mcp"))
    assert _events(db_session, draft) == [("draft", "interviewing", "codex-mcp", False)]


def test_a_change_read_from_mail_is_said_by_mail(mcp_tools, db_session, draft):
    mcp_tools.update_application(str(draft.id), status="rejected", from_email=True,
                                 ctx=_fake_ctx("claude-ai"))
    assert _events(db_session, draft) == [("draft", "rejected", "mail", False)]


def test_a_client_naming_itself_like_a_source_word_is_recorded_as_mcp(client, db_session, draft):
    headers = {**MCP, "X-Maestro-CS-Origin-Detail": "you"}
    client.patch(f"/api/applications/{draft.id}", json={"status": "applied"}, headers=headers)
    assert _events(db_session, draft) == [("draft", "applied", "mcp", False)]


def test_the_companions_change_is_said_by_the_companion(client, db_session, draft):
    response = client.patch(f"/api/applications/{draft.id}", json={"status": "applied"}, headers=EXT)
    assert response.status_code == 200, response.text
    assert _events(db_session, draft) == [("draft", "applied", "companion", False)]


def _approved(db_session):
    from tests.test_proposal_state_machine import _mk_proposal

    prop = _mk_proposal(db_session)
    prop.status = "approved"
    db_session.commit()
    return prop, db_session.get(models.Application, prop.application_id)


def test_mark_submitted_through_mcp_names_its_client(mcp_tools, db_session):
    prop, application = _approved(db_session)
    mcp_tools.mark_submitted(str(prop.id), user_attested=True, channel="chat",
                             note="The user saw the confirmation email", ctx=_fake_ctx("claude-ai"))
    assert _events(db_session, application) == [("draft", "applied", "claude-ai", False)]


def test_the_companions_submit_is_said_by_the_companion(client, db_session, tmp_path, monkeypatch):
    from tests.test_proposal_state_machine import _mk_proposal

    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    prop = _mk_proposal(db_session)
    prop.status = "accepted"
    db_session.commit()
    body = {"confirmation": {"host": "acme.example", "path": "/done", "text": "Thank you"}}
    response = client.post(f"/api/proposals/{prop.id}/companion-submitted", json=body, headers=EXT)
    assert response.status_code == 200, response.text
    application = db_session.get(models.Application, prop.application_id)
    assert _events(db_session, application) == [("draft", "applied", "companion", False)]


def test_a_new_draft_counts_as_a_change_from_none(client, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "base_resumes_dir", tmp_path)
    monkeypatch.setattr(settings, "applications_dir", tmp_path / "applications")
    (tmp_path / "events_base.json").write_text(json.dumps(RESUME))
    db_session.add(models.BaseResume(slug="events_base", data_json=RESUME))
    job = models.Job(id=uuid.uuid4(), raw_text="Example role", raw_text_hash=uuid.uuid4().hex)
    db_session.add(job)
    db_session.commit()
    response = client.post("/api/applications/from-base",
                           json={"job_id": str(job.id), "base_resume": "events_base", "ops": []})
    assert response.status_code == 200, response.text
    application = db_session.get(models.Application, uuid.UUID(response.json()["id"]))
    assert _events(db_session, application) == [(None, "draft", "from_base", False)]


def test_set_status_writes_the_column_and_one_event_only_on_a_change(db_session, draft):
    from app.services import application_status

    assert application_status.set_status(db_session, draft, "draft", "you") is None
    event = application_status.set_status(db_session, draft, "offered", "mail")
    assert (event.from_status, event.to_status, event.source) == ("draft", "offered", "mail")
    db_session.commit()
    assert draft.status == "offered"
    assert _events(db_session, draft) == [("draft", "offered", "mail", False)]


def test_set_status_on_a_new_application_ties_the_event_to_it_before_the_flush(db_session, tmp_path,
                                                                              monkeypatch):
    """With sync on the flush guard reads application_id before the flush: a new application's
    first event must already carry it (SYSTEM.md {#inv-flush-guard})."""
    from app.services import application_status

    monkeypatch.setattr(settings, "settings_dir", tmp_path / "settings")
    monkeypatch.setattr(settings, "sync_key_file", tmp_path / "absent-key")
    monkeypatch.setattr(settings, "sync_remote_url", "")
    sync_status.create_key()
    job = models.Job(id=uuid.uuid4(), raw_text="Example role", raw_text_hash=uuid.uuid4().hex)
    db_session.add(job)
    db_session.flush()
    application = models.Application(job_id=job.id, base_resume="base")
    db_session.add(application)
    event = application_status.set_status(db_session, application, "draft", "tailor")
    assert event.application_id == application.id is not None
    db_session.commit()
    assert _events(db_session, application) == [(None, "draft", "tailor", False)]


def _request(job, payload):
    from app.services.sync.request_apply import RequestIn

    return RequestIn(id=uuid.uuid4(), kind="application_patch", job_id=job.id, payload=payload,
                     created_at=datetime.now(UTC))


@pytest.mark.parametrize(("sent", "recorded"), [("claude-ai", "claude-ai"), (None, "sync")])
def test_the_owner_records_the_source_a_queued_request_carries(db_session, draft, sent, recorded):
    from app.services.sync import request_apply

    payload = {"application_id": str(draft.id), "fields": {"status": "applied"}}
    if sent:
        payload["source"] = sent
    job = db_session.get(models.Job, draft.job_id)
    assert request_apply.settle(db_session, _request(job, payload)) == ("applied", None)
    assert _events(db_session, draft) == [("draft", "applied", recorded, False)]


def test_a_queued_status_patch_carries_its_source(client, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path / "settings")
    monkeypatch.setattr(settings, "sync_key_file", tmp_path / "absent-key")
    monkeypatch.setattr(settings, "sync_remote_url", "")
    job = models.Job(id=uuid.uuid4(), raw_text="Example role", raw_text_hash=uuid.uuid4().hex,
                     owner_machine="other-machine")
    db_session.add(job)
    db_session.flush()
    application = models.Application(id=uuid.uuid4(), job_id=job.id, base_resume="base",
                                     status="draft")
    db_session.add(application)
    db_session.commit()
    sync_status.create_key()
    response = client.patch(f"/api/applications/{application.id}", json={"status": "applied"},
                            headers=MCP)
    assert response.status_code == 202, response.text
    (row,) = db_session.scalars(sa.select(models.SyncRequest)).all()
    assert row.payload_json == {"application_id": str(application.id),
                                "fields": {"status": "applied"}, "source": "claude-ai"}
    assert _events(db_session, application) == []


# ---------------------------------------------------------------------------- the one writer

ALLOWED_WRITER = BACKEND / "app" / "services" / "application_status.py"
SCANNED = (BACKEND / "app", BACKEND / "mcp_server")
_APPLICATION_WORDS = {"app", "apps", "application", "applications"}
# Values that are an Application whatever the name they are bound to.
_APPLICATION_VALUE = re.compile(
    r"^Application\(|\.get\(Application\b|newest_for_job\(|select\(Application\)|select\(Application,")


def _named_like_an_application(name: str) -> bool:
    return any(word in _APPLICATION_WORDS for word in name.lower().split("_"))


def _application_names(tree: ast.AST) -> set[str]:
    """Names this module binds to an Application: by value, by annotation or by loop source."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _APPLICATION_VALUE.search(ast.unparse(node.value)):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, (ast.AnnAssign, ast.arg)) and node.annotation is not None:
            target = node.target if isinstance(node, ast.AnnAssign) else node
            name = target.id if isinstance(target, ast.Name) else getattr(target, "arg", None)
            if name and re.search(r"\bApplication\b", ast.unparse(node.annotation)):
                names.add(name)
        elif isinstance(node, (ast.For, ast.comprehension)) and isinstance(node.target, ast.Name):
            if _APPLICATION_VALUE.search(ast.unparse(node.iter)):
                names.add(node.target.id)
    return names


def _is_application(node: ast.AST, known: set[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in known or _named_like_an_application(node.id)
    if isinstance(node, ast.Attribute):
        return _named_like_an_application(node.attr)
    return False


def _stores(node: ast.AST):
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    for target in targets:
        yield from (target.elts if isinstance(target, (ast.Tuple, ast.List)) else [target])


def status_writes(source: str) -> list[int]:
    """Lines that write an application's status: `x.status = …`, `setattr(x, "status", …)`,
    `Application(status=…)` or `update(Application).values(status=…)`."""
    tree = ast.parse(source)
    known = _application_names(tree)
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            lines += [node.lineno for target in _stores(node) if isinstance(target, ast.Attribute)
                      and target.attr == "status" and _is_application(target.value, known)]
        elif isinstance(node, ast.Call):
            func = ast.unparse(node.func)
            keywords = {keyword.arg for keyword in node.keywords}
            if func == "setattr" and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) \
                    and node.args[1].value == "status" and _is_application(node.args[0], known):
                lines.append(node.lineno)
            elif func.endswith("Application") and func.split(".")[-1] == "Application" \
                    and "status" in keywords:
                lines.append(node.lineno)
            elif func.endswith(".values") and "update(Application)" in func and "status" in keywords:
                lines.append(node.lineno)
    return sorted(set(lines))


@pytest.mark.parametrize("snippet", [
    "app_row.status = 'applied'",
    "application.status = value",
    "existing_application.status, other.x = 'a', 1",
    "row = db.get(Application, i)\nrow.status = 'x'",
    "row = session.scalar(select(Application).where(Application.id == i))\nrow.status = 'x'",
    "def f(row: Application):\n    row.status = 'x'",
    "for row in db.scalars(select(Application)):\n    row.status = 'x'",
    "prop.application.status = 'x'",
    "setattr(app, 'status', 'x')",
    "Application(job_id=j, base_resume='b', status='draft')",
    "models.Application(job_id=j, status='draft')",
    "db.execute(update(Application).values(status='applied'))",
])
def test_the_scan_finds_an_application_status_write(snippet):
    assert status_writes(snippet)


@pytest.mark.parametrize("snippet", [
    "prop.status = 'expired'",
    "tailoring.status = 'tailored'",
    "row = db.get(Template, i)\nrow.status = 'draft'",
    "row.status, row.reason = 'refused', reason",
    "ApplicationProposal(job_id=j, status='pending_review')",
    "document.ingest_status = 'failed'",
    "status = 'clear'",
    "db.execute(update(TailoringSession).values(status='superseded'))",
    "for name in ('status', 'notes'):\n    setattr(row, name, values[name])",
])
def test_the_scan_leaves_other_models_statuses_alone(snippet):
    assert status_writes(snippet) == []


def test_only_set_status_writes_an_application_status():
    """SYSTEM.md {#inv-status-through-set-status}: every writer of Application.status goes through
    services/application_status.set_status, so no change skips the dated log."""
    offenders = []
    for root in SCANNED:
        for path in sorted(root.rglob("*.py")):
            if path == ALLOWED_WRITER or "tests" in path.relative_to(root).parts:
                continue
            offenders += [f"{path.relative_to(BACKEND)}:{line}"
                          for line in status_writes(path.read_text(encoding="utf-8"))]
    assert offenders == [], "write the status through application_status.set_status"
