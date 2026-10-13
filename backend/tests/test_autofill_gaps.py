"""The known-gaps list: widgets the engine could not operate, or the user fixed by hand.

A durable, value-free table (family hash, host, shape, outcome, count), so the engine's to-do list
outlives the 50-run trace limit. SYSTEM.md {#inv-autofill-telemetry-no-values}: no label, value or
option text can enter it, and the host is the only thing in it that names where you applied.
"""

import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from app.models.autofill_widget_gap import AutofillWidgetGap

BACKEND = Path(__file__).resolve().parents[1]
HOST = "careers.acme.example"


def gap(**overrides) -> dict:
    return {"family": "ab12cd", "host": HOST, "shape": "popup", "outcome": "cannot_operate", **overrides}


def post(client, *gaps: dict):
    return client.post("/api/autofill/gaps", json={"gaps": list(gaps)})


def rows(db_session) -> list[AutofillWidgetGap]:
    db_session.expire_all()
    return list(db_session.scalars(select(AutofillWidgetGap)).all())


# --- POST /api/autofill/gaps ----------------------------------------------------

def test_a_post_stores_one_row_per_gap_with_a_count_of_one(client, db_session):
    assert post(client, gap(), gap(shape="group", family="zz9")).status_code == 204

    stored = sorted(rows(db_session), key=lambda r: r.shape)
    assert [(r.family, r.host, r.shape, r.outcome, r.count) for r in stored] == [
        ("zz9", HOST, "group", "cannot_operate", 1),
        ("ab12cd", HOST, "popup", "cannot_operate", 1),
    ]
    assert all(r.first_seen_at == r.last_seen_at for r in stored)


def test_posting_the_same_gap_again_increments_its_count(client, db_session):
    post(client, gap())
    first = rows(db_session)[0]
    first_seen = first.first_seen_at
    # Push the stored last-seen into the past, so a column that never updates cannot pass.
    long_ago = first_seen - timedelta(days=30)
    first.last_seen_at = long_ago
    db_session.commit()

    post(client, gap())
    post(client, gap(), gap())

    (row,) = rows(db_session)
    assert row.count == 4
    assert row.first_seen_at == first_seen
    assert row.last_seen_at > long_ago


def test_the_same_gap_twice_in_one_post_is_one_row_with_both_counted(client, db_session):
    """Deduped in Python before the session sees it: two pending inserts for one unique key would collide."""
    assert post(client, gap(), gap(), gap(outcome="user_fixed")).status_code == 204

    by_outcome = {r.outcome: r.count for r in rows(db_session)}
    assert by_outcome == {"cannot_operate": 2, "user_fixed": 1}


def test_the_key_is_family_host_shape_and_outcome(client, db_session):
    post(client, gap(), gap(family="other1"), gap(host="jobs.globex.example"), gap(shape="text"),
         gap(outcome="unconfirmed"), gap(outcome="missing_technique"))

    assert len(rows(db_session)) == 6


@pytest.mark.parametrize("outcome", ["cannot_operate", "unconfirmed", "user_fixed", "missing_technique"])
def test_every_planned_outcome_is_accepted(client, outcome):
    assert post(client, gap(outcome=outcome)).status_code == 204


@pytest.mark.parametrize("shape", ["text", "date", "select", "group", "search", "popup", "unknown"])
def test_every_inventory_shape_is_accepted(client, shape):
    assert post(client, gap(shape=shape)).status_code == 204


@pytest.mark.parametrize("extra", [{"label": "Pronouns"}, {"value": "she/her"}, {"options": ["Yes", "No"]},
                                   {"count": 5}, {"rule_id": "r1"}])
def test_any_extra_key_is_refused_and_nothing_is_stored(client, db_session, extra):
    """The privacy backstop: a label, a value or option text 422s instead of being stored."""
    assert post(client, gap(**extra)).status_code == 422
    assert rows(db_session) == []


def test_the_batch_itself_refuses_extra_keys(client, db_session):
    response = client.post("/api/autofill/gaps", json={"gaps": [gap()], "page_host": HOST})

    assert response.status_code == 422 and rows(db_session) == []


@pytest.mark.parametrize("bad", [
    {"family": ""}, {"family": "f:ab12"}, {"family": "AB12"}, {"family": "a" * 25}, {"family": "a b"},
    {"host": ""}, {"host": "Careers.Acme.example"}, {"host": "a" * 254}, {"host": "acme.example/path"},
    {"host": "Pronouns, she/her"}, {"shape": "slider"}, {"shape": ""}, {"outcome": "filled"},
    {"outcome": ""},
], ids=lambda bad: next(iter(bad)) + "=" + str(next(iter(bad.values())))[:12])
def test_a_malformed_gap_is_refused_and_nothing_is_stored(client, db_session, bad):
    assert post(client, gap(**bad)).status_code == 422
    assert rows(db_session) == []


def test_at_most_forty_gaps_per_post(client, db_session):
    forty = [gap(family=f"f{n}") for n in range(40)]
    assert post(client, *forty).status_code == 204
    assert len(rows(db_session)) == 40

    # The 41st is as valid as the rest, so only the cap can refuse it.
    assert post(client, *forty, gap(family="f40")).status_code == 422
    stored = rows(db_session)
    assert len(stored) == 40 and {r.count for r in stored} == {1}


def test_an_empty_post_is_accepted_and_stores_nothing(client, db_session):
    assert post(client).status_code == 204
    assert rows(db_session) == []


def test_a_host_with_a_port_is_accepted(client):
    assert post(client, gap(host="localhost:3000")).status_code == 204


# --- GET /api/autofill/gaps/summary ---------------------------------------------

def test_the_summary_of_nothing_is_zeros_and_an_empty_top(client):
    assert client.get("/api/autofill/gaps/summary").json() == {
        "kinds": 0, "sites": 0, "user_fixed": 0, "top": []}


def test_the_summary_ranks_by_count_and_names_no_host(client):
    # popup@ab12cd: 3 hits over two sites; group@zz9: 2 hits on one site; text@ab12cd: 1 hit.
    post(client, gap(), gap(), gap(host="jobs.globex.example"))
    post(client, gap(family="zz9", shape="group", outcome="unconfirmed"),
         gap(family="zz9", shape="group", outcome="unconfirmed"))
    post(client, gap(shape="text", outcome="missing_technique"))

    body = client.get("/api/autofill/gaps/summary").json()

    assert body["top"] == [
        {"family": "ab12cd", "shape": "popup", "outcome": "cannot_operate", "count": 3, "sites": 2},
        {"family": "zz9", "shape": "group", "outcome": "unconfirmed", "count": 2, "sites": 1},
        {"family": "ab12cd", "shape": "text", "outcome": "missing_technique", "count": 1, "sites": 1},
    ]
    assert body["sites"] == 2
    assert HOST not in str(body) and "globex" not in str(body)


def test_kinds_are_distinct_family_and_shape_and_user_fixed_counts_the_kinds_you_fixed(client):
    post(client, gap(), gap(outcome="user_fixed"),                      # one kind: cannot_operate AND fixed
         gap(family="zz9", shape="group"),                              # a second kind, never fixed
         gap(family="yy8", shape="text", outcome="user_fixed"))         # a third kind, only fixed

    body = client.get("/api/autofill/gaps/summary").json()

    assert (body["kinds"], body["user_fixed"], body["sites"]) == (3, 2, 1)


def test_the_summary_lists_at_most_ten_top_kinds_and_orders_ties_stably(client):
    post(client, *[gap(family=f"fam{n:02d}") for n in range(15)])

    top = client.get("/api/autofill/gaps/summary").json()["top"]

    assert len(top) == 10
    assert [t["family"] for t in top] == [f"fam{n:02d}" for n in range(10)]


# --- DELETE /api/autofill/telemetry ---------------------------------------------

def test_clearing_telemetry_also_clears_the_gaps_because_they_hold_hosts(client, db_session):
    post(client, gap(), gap(host="jobs.globex.example"))
    assert len(rows(db_session)) == 2

    response = client.delete("/api/autofill/telemetry")

    assert response.status_code == 200
    assert rows(db_session) == []
    assert client.get("/api/autofill/gaps/summary").json()["top"] == []


def test_the_gaps_start_again_after_a_clear(client, db_session):
    post(client, gap(), gap())
    client.delete("/api/autofill/telemetry")

    post(client, gap())

    (row,) = rows(db_session)
    assert row.count == 1


# --- sync -------------------------------------------------------------------------

def test_the_table_stays_on_this_machine_like_the_other_autofill_telemetry():
    from app.services.sync import registry

    assert registry.TABLES["autofill_widget_gaps"] == registry.LOCAL


# --- the migration ----------------------------------------------------------------

def _config(tmp_path):
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{tmp_path / 'gaps.sqlite3'}")
    return cfg


def _tables(path):
    with closing(sqlite3.connect(path)) as db:
        return {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def test_migration_creates_the_table_and_downgrade_drops_it(tmp_path):
    cfg = _config(tmp_path)
    path = tmp_path / "gaps.sqlite3"
    command.upgrade(cfg, "d3ea5090cc80")
    assert "autofill_widget_gaps" not in _tables(path)

    command.upgrade(cfg, "head")

    assert "autofill_widget_gaps" in _tables(path)
    with closing(sqlite3.connect(path)) as db:
        columns = {r[1] for r in db.execute("PRAGMA table_info(autofill_widget_gaps)")}
        assert columns == {"id", "family", "host", "shape", "outcome", "count", "first_seen_at", "last_seen_at"}
        insert = ("INSERT INTO autofill_widget_gaps (id, family, host, shape, outcome, count) "
                  "VALUES (?, 'ab12cd', 'h.example', 'popup', 'cannot_operate', 1)")
        db.execute(insert, ("1",))
        db.commit()
        with pytest.raises(sqlite3.IntegrityError):   # unique on (family, host, shape, outcome)
            db.execute(insert, ("2",))

    command.downgrade(cfg, "d3ea5090cc80")

    assert "autofill_widget_gaps" not in _tables(path)


# --- fill_trace.py report ---------------------------------------------------------

def _report(db: Path, tmp_path) -> subprocess.CompletedProcess:
    env = {**os.environ, "SETTINGS_DIR": str(tmp_path), "LOGS_DIR": str(tmp_path)}
    return subprocess.run([sys.executable, "-m", "scripts.fill_trace", "--db", str(db), "report"], cwd=BACKEND,
                          capture_output=True, text=True, env=env, timeout=120)


def _migrated(tmp_path) -> Path:
    path = tmp_path / "copy" / "copy.sqlite3"
    path.parent.mkdir()
    cfg = _config(tmp_path)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    command.upgrade(cfg, "head")
    return path


def test_report_prints_the_gaps_section_from_a_database_copy(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.schemas.autofill_gaps import GapIn
    from app.services import autofill_gaps

    path = _migrated(tmp_path)
    engine = create_engine(f"sqlite:///{path}")
    with Session(engine) as session:
        autofill_gaps.record(session, [GapIn(**gap()), GapIn(**gap()), GapIn(**gap(host="jobs.globex.example")),
                                       GapIn(**gap(family="zz9", shape="group", outcome="user_fixed"))])
        session.commit()
    engine.dispose()

    done = _report(path, tmp_path)

    assert done.returncode == 0, done.stderr
    section = done.stdout.split("== Known gaps ==\n", 1)[1].split("\n\n", 1)[0].splitlines()
    assert section == [
        "kinds=2  sites=2  user_fixed=1",
        "family=ab12cd  shape=popup  outcome=cannot_operate  count=3  sites=2",
        "family=zz9  shape=group  outcome=user_fixed  count=1  sites=1",
    ]
    assert "acme" not in done.stdout and "globex" not in done.stdout   # the report names no host


def test_report_on_an_empty_database_says_there_are_no_gaps(tmp_path):
    done = _report(_migrated(tmp_path), tmp_path)

    assert done.returncode == 0, done.stderr
    assert "== Known gaps ==\n(no data)" in done.stdout
