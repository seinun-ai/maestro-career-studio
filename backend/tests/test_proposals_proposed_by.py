"""Who filed a proposal (plan appendix A9): the MCP client's name from the origin
headers, "you" for the web app's own queue, NULL when unknown. Additive on
every read, backfilled for the web app's past promotions, and carried by the
legacy Postgres import (which stays strict about missing columns)."""

import sqlite3
import uuid
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient

from app.main import app
from app.models.application_proposal import ApplicationProposal
from app.tools import migrate_from_postgres as importer
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
    return {**_MCP, "X-Maestro-CS-Origin-Detail": name}


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


@pytest.mark.parametrize("declared", ["you", "You", " YOU "])
def test_a_client_that_declares_itself_you_is_still_an_agent(db_session, declared):
    # clientInfo.name is self-declared: a client calling itself "you" would
    # otherwise read as the web app's own "Queued by you".
    job = _mk_job(db_session, company="Theta", source="agent")
    r = _file(job, _as_client(declared), proposed_by="you")
    assert r.status_code == 201
    assert r.json()["proposed_by"] is None


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


def test_the_legacy_import_refuses_a_source_without_the_column(tmp_path):
    # The importer stays strict: a model column the source lacks fails closed,
    # which is why the boxed Postgres chain carries its own revision.
    src, dst = tmp_path / "src.sqlite3", tmp_path / "dst.sqlite3"
    command.upgrade(_sqlite_cfg(src), SQLITE_BASELINE)
    command.upgrade(_sqlite_cfg(dst), "head")
    with pytest.raises(importer.ExportError, match=r"application_proposals: source lacks \['proposed_by'\]"):
        importer.copy_database(f"sqlite:///{src}", f"sqlite:///{dst}", log=lambda *_: None)


def test_the_legacy_chain_adds_the_column_at_its_head():
    scripts = ScriptDirectory.from_config(Config(str(importer.LEGACY_INI)))
    (head,) = scripts.get_heads()
    revision = scripts.get_revision(head)
    assert revision.down_revision == "85a1bb628e28"
    source = Path(revision.path).read_text()
    assert 'op.add_column("application_proposals", sa.Column("proposed_by"' in source
    assert PROMOTED in source
