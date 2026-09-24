"""Who filed a proposal (plan appendix A9): the MCP client's name from the origin
headers, "you" for the web app's own queue, NULL when unknown. Additive on
every read, and backfilled for the web app's past promotions."""

import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.main import app
from app.models.application_proposal import ApplicationProposal
from app.services import proposals as svc
from mcp_server.client import _origin_headers
from tests.test_proposals_models import _mk_job

client = TestClient(app)
_MCP = {"X-Maestro-CS-Origin": "mcp"}
BACKEND_DIR = Path(__file__).resolve().parents[1]
SQLITE_BASELINE = "871d0425b64c"
PROMOTED = "Promoted from the tracker by the user"


def _file(job, headers=None, **body):
    return client.post(
        "/api/proposals", json={"job_id": str(job.id), **body}, headers=headers or {}
    )


def _as_client(name):
    """The headers the MCP server really sends for a client of that name."""
    return _origin_headers(name)


def _sqlite_cfg(path: Path) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    return cfg


def test_the_column_round_trips(db_session):
    job = _mk_job(db_session, company="Acme", source="agent")
    prop = ApplicationProposal(job_id=job.id, proposed_by="claude-ai")
    db_session.add(prop)
    db_session.commit()
    db_session.expire_all()
    assert db_session.get(ApplicationProposal, prop.id).proposed_by == "claude-ai"


def test_an_mcp_proposal_records_the_clients_name(db_session):
    job = _mk_job(db_session, company="Acme", source="agent")
    r = _file(job, _as_client("claude-ai"))
    assert r.status_code == 201
    pid = r.json()["id"]
    assert r.json()["proposed_by"] == "claude-ai"
    assert client.get(f"/api/proposals/{pid}").json()["proposed_by"] == "claude-ai"
    listed = {i["id"]: i for i in client.get("/api/proposals").json()["items"]}
    assert listed[pid]["proposed_by"] == "claude-ai"


def test_an_unnamed_mcp_client_is_unknown_and_cannot_claim_you(db_session):
    job = _mk_job(db_session, company="Beta", source="agent")
    r = _file(job, _MCP, proposed_by="you")
    assert r.status_code == 201
    assert r.json()["proposed_by"] is None


_DISGUISED_YOU = ["\ufeffyou", "you\u200b", "\uff59\uff4f\uff55", "Y O U"]


@pytest.mark.parametrize("declared", ["you", "You", " YOU ", *_DISGUISED_YOU])
def test_a_client_that_declares_itself_you_is_still_an_agent(db_session, declared):
    # clientInfo.name is self-declared: a client calling itself "you" would
    # otherwise read as the web app's own "Queued by you".
    job = _mk_job(db_session, company="Theta", source="agent")
    r = _file(job, _as_client(declared), proposed_by="you")
    assert r.status_code == 201
    assert r.json()["proposed_by"] is None


@pytest.mark.parametrize("declared", [*_DISGUISED_YOU, "\u200b\ufeff"])
def test_the_filer_rule_sees_through_a_disguised_you(declared):
    # A BOM, a zero-width space, fullwidth letters or inner spaces must not
    # turn "you" into a name that reads as the web app's "Queued by you".
    assert svc.proposal_filer("mcp", declared, "you") is None


@pytest.mark.parametrize("name", ["Café Agent", "クロード"])
def test_a_non_ascii_client_name_is_stored_as_itself(db_session, name):
    job = _mk_job(db_session, company="Kappa", source="agent")
    r = _file(job, _as_client(name))
    assert r.status_code == 201
    assert r.json()["proposed_by"] == name
    assert client.get(f"/api/proposals/{r.json()['id']}").json()["proposed_by"] == name


def test_the_web_apps_queue_says_you(db_session):
    job = _mk_job(db_session, company="Gamma")
    r = _file(job, proposed_by="you")
    assert r.status_code == 201
    assert r.json()["proposed_by"] == "you"


def test_a_body_without_a_filer_is_unknown(db_session):
    job = _mk_job(db_session, company="Iota")
    assert _file(job).json()["proposed_by"] is None


def test_a_body_can_only_say_you(db_session):
    job = _mk_job(db_session, company="Delta")
    assert _file(job, proposed_by="Claude").status_code == 422


def test_a_repeat_filing_keeps_the_first_filer(db_session):
    job = _mk_job(db_session, company="Epsilon", source="agent")
    first = _file(job, _as_client("codex-mcp-client"))
    again = _file(job, _as_client("claude-ai"))
    assert again.status_code == 200
    assert again.json()["proposed_by"] == first.json()["proposed_by"] == "codex-mcp-client"


def test_job_reads_carry_the_newest_proposals_filer(db_session):
    job = _mk_job(db_session, company="Zeta", source="agent")
    bare = _mk_job(db_session, company="Eta", source="agent")
    _file(job, _as_client("claude-ai"))
    listed = {j["id"]: j for j in client.get("/api/jobs?limit=500").json()}
    assert listed[str(job.id)]["proposal_proposed_by"] == "claude-ai"
    assert listed[str(bare.id)]["proposal_proposed_by"] is None
    detail = client.get(f"/api/jobs/{job.id}/detail").json()
    assert detail["job"]["proposal_proposed_by"] == "claude-ai"
    bare_detail = client.get(f"/api/jobs/{bare.id}/detail").json()
    assert bare_detail["job"]["proposal_proposed_by"] is None


def test_job_reads_show_the_newest_filer_not_the_first(db_session):
    # Two proposals, two filers: the older one closed a day earlier. Inserted
    # oldest first, so a query that forgot to order newest first reads it.
    job = _mk_job(db_session, company="Lambda", source="agent")
    now = datetime.now(UTC)
    for filer, status, created_at in [
        ("codex-mcp-client", "rejected", now - timedelta(days=1)),
        ("claude-ai", "pending_review", now),
    ]:
        db_session.add(ApplicationProposal(
            job_id=job.id, proposed_by=filer, status=status, created_at=created_at,
        ))
        db_session.commit()
    listed = {j["id"]: j for j in client.get("/api/jobs?limit=500").json()}
    assert listed[str(job.id)]["proposal_proposed_by"] == "claude-ai"
    detail = client.get(f"/api/jobs/{job.id}/detail").json()
    assert detail["job"]["proposal_proposed_by"] == "claude-ai"


def _seed_pre_column_proposals(path: Path) -> tuple[str, str]:
    job, promoted, hunted = (uuid.uuid4().hex for _ in range(3))
    with closing(sqlite3.connect(path)) as conn:
        conn.execute(
            "INSERT INTO jobs (id, raw_text, raw_text_hash) VALUES (?, 'JD', 'h')", (job,)
        )
        conn.executemany(
            "INSERT INTO application_proposals (id, job_id, plan_json) VALUES (?, ?, ?)",
            [
                (promoted, job, f'{{"summary": "{PROMOTED}"}}'),
                (hunted, job, '{"summary": "Strong fit"}'),
            ],
        )
        conn.commit()
    return promoted, hunted


def test_the_migration_backfills_the_web_apps_own_promotions(tmp_path):
    path = tmp_path / "m.sqlite3"
    cfg = _sqlite_cfg(path)
    command.upgrade(cfg, SQLITE_BASELINE)
    promoted, hunted = _seed_pre_column_proposals(path)
    command.upgrade(cfg, "head")
    with closing(sqlite3.connect(path)) as conn:
        rows = dict(conn.execute("SELECT id, proposed_by FROM application_proposals"))
    assert rows == {promoted: "you", hunted: None}


def _proposal_table(path: Path) -> tuple[list[str], list[tuple], list[tuple], list[str]]:
    """Columns, their definitions, foreign keys and indexes. Batch mode rebuilds
    the table, so the stored CREATE text differs in quoting and FK order."""
    with closing(sqlite3.connect(path)) as conn:
        info = conn.execute("PRAGMA table_info(application_proposals)").fetchall()
        fks = conn.execute("PRAGMA foreign_key_list(application_proposals)").fetchall()
        indexes = conn.execute("PRAGMA index_list(application_proposals)").fetchall()
    return (
        [row[1] for row in info],
        info,
        sorted(row[2:] for row in fks),
        sorted(row[1] for row in indexes),
    )


def test_the_migration_round_trips_from_head_to_the_baseline_and_back(tmp_path):
    baseline, path = tmp_path / "base.sqlite3", tmp_path / "rt.sqlite3"
    command.upgrade(_sqlite_cfg(baseline), SQLITE_BASELINE)
    cfg = _sqlite_cfg(path)
    command.upgrade(cfg, "head")
    assert "proposed_by" in _proposal_table(path)[0]
    command.downgrade(cfg, SQLITE_BASELINE)
    assert _proposal_table(path) == _proposal_table(baseline)
    assert "proposed_by" not in _proposal_table(path)[0]
    command.upgrade(cfg, "head")
    assert "proposed_by" in _proposal_table(path)[0]

