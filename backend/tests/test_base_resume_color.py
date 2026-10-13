"""A base resume's colour hue: picked on every create path, changed only through identity.

The hue is identity metadata like the anchors: choosing it must never touch the
document, its versions or its rendered artifacts, and a 422 saves nothing.
"""

import io
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.main import app
from app.models.base_resume import BaseResume
from app.models.resume_version import ResumeVersion
from app.services import kb_consolidation, kb_import, seeding
from app.services.resume_colors import PRESET_HUES

from tests.test_base_resume_from_kb import _entity, _profile
from tests.test_base_resume_role_category import SAMPLE, _client


@pytest.fixture
def renders(monkeypatch):
    """Every render the router asked for, so a test can assert there were none."""
    calls: list[str] = []

    def fake(slug, db, **kw):
        calls.append(slug)
        return db.get(BaseResume, slug)

    monkeypatch.setattr("app.routers.base_resumes.base_resume_render.render_base_resume", fake)
    return calls


@pytest.fixture
def client(db_session, tmp_path, monkeypatch, renders):
    monkeypatch.setattr("app.routers.base_resumes.settings.base_resumes_dir", tmp_path)
    monkeypatch.setattr(kb_consolidation, "prefetch_prompts", lambda s: None)
    return _client(db_session)


def teardown_function():
    app.dependency_overrides.clear()


def _add(db_session, slug, **kw) -> BaseResume:
    row = BaseResume(slug=slug, data_json=SAMPLE, **kw)
    db_session.add(row)
    db_session.commit()
    return row


def _create(client, slug, **extra):
    return client.post("/api/base-resumes", json={"slug": slug, "data": SAMPLE, **extra})


def _hues(client) -> dict[str, int | None]:
    rows = client.get("/api/base-resumes?include_archived=true").json()
    return {r["slug"]: r["color_hue"] for r in rows}


# --- create -----------------------------------------------------------------

def test_create_picks_a_preset_no_other_resume_has(client, db_session):
    _add(db_session, "one", color_hue=PRESET_HUES[0])
    _add(db_session, "two", color_hue=PRESET_HUES[1])

    res = _create(client, "fresh")

    assert res.status_code == 200, res.text
    hue = res.json()["color_hue"]
    assert hue in PRESET_HUES[2:]
    assert _hues(client)["fresh"] == hue


def test_create_keeps_a_hue_the_caller_chose(client):
    res = _create(client, "chosen", color_hue=200)
    assert res.status_code == 200, res.text
    assert res.json()["color_hue"] == 200
    assert _hues(client)["chosen"] == 200


@pytest.mark.parametrize("bad", [360, -1])
def test_create_rejects_a_hue_out_of_range_and_saves_nothing(client, db_session, bad):
    res = _create(client, "bad_hue", color_hue=bad)
    assert res.status_code == 422
    assert db_session.get(BaseResume, "bad_hue") is None


def test_archived_and_deleted_resumes_do_not_hold_a_colour(client, db_session):
    # Eight presets are live; the other two are held only by an archived and a
    # soft-deleted resume, so both are free to take.
    for i, hue in enumerate(PRESET_HUES[:8]):
        _add(db_session, f"live{i}", color_hue=hue)
    _add(db_session, "archived", color_hue=PRESET_HUES[8], archived_at=datetime.now(timezone.utc))
    _add(db_session, "deleted", color_hue=PRESET_HUES[9], deleted_at=datetime.now(timezone.utc))

    assert _create(client, "fresh").json()["color_hue"] in {PRESET_HUES[8], PRESET_HUES[9]}


def test_with_every_preset_live_the_pick_is_still_a_preset(client, db_session):
    for i, hue in enumerate(PRESET_HUES):
        _add(db_session, f"live{i}", color_hue=hue)
    assert _create(client, "eleventh").json()["color_hue"] in PRESET_HUES


# --- the other create doors --------------------------------------------------

def test_duplicate_gets_a_different_hue_from_its_source(client, db_session):
    _add(db_session, "source", color_hue=PRESET_HUES[3])

    res = client.post("/api/base-resumes/source/duplicate", json={"new_slug": "copy"})

    assert res.status_code == 200, res.text
    assert res.json()["color_hue"] in PRESET_HUES
    assert res.json()["color_hue"] != PRESET_HUES[3]


def test_duplicating_an_archived_source_never_reuses_its_hue(client, db_session):
    # The source's hue is the only preset no live resume holds, so a pick that
    # only looked at live resumes would hand it straight back.
    for i, hue in enumerate(PRESET_HUES[:9]):
        _add(db_session, f"live{i}", color_hue=hue)
    _add(db_session, "source", color_hue=PRESET_HUES[9], archived_at=datetime.now(timezone.utc))

    for i in range(10):
        res = client.post("/api/base-resumes/source/duplicate", json={"new_slug": f"copy{i}"})
        assert res.status_code == 200, res.text
        assert res.json()["color_hue"] in PRESET_HUES[:9]


def test_duplicate_keeps_a_hue_the_caller_chose(client, db_session):
    _add(db_session, "source", color_hue=PRESET_HUES[3])
    res = client.post("/api/base-resumes/source/duplicate", json={"new_slug": "copy", "color_hue": 17})
    assert res.json()["color_hue"] == 17
    res = client.post("/api/base-resumes/source/duplicate", json={"new_slug": "bad", "color_hue": 360})
    assert res.status_code == 422
    assert db_session.get(BaseResume, "bad") is None


def test_from_kb_passes_the_hue_through_or_picks_one(client, db_session):
    _profile(db_session)
    keep = _entity(db_session, "experience", "Data Engineer", "Acme")
    body = {"entity_ids": [str(keep.id)], "role_category": "data_engineer"}

    chosen = client.post("/api/base-resumes/from-kb", json={**body, "slug": "chosen", "color_hue": 222})
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["color_hue"] == 222

    picked = client.post("/api/base-resumes/from-kb", json={**body, "slug": "picked"})
    assert picked.status_code == 200, picked.text
    assert picked.json()["color_hue"] in PRESET_HUES


def _fake_parse(monkeypatch):
    monkeypatch.setattr(
        kb_consolidation, "parse_resume_text", lambda session, text: (json.loads(json.dumps(SAMPLE)), [])
    )


def _import(client, name, **form):
    return client.post(
        "/api/base-resumes/import",
        files={"file": (name, io.BytesIO(b"text"), "text/plain")},
        data=form,
    )


def test_import_passes_the_hue_through_or_picks_one(client, monkeypatch):
    _fake_parse(monkeypatch)

    chosen = _import(client, "a.txt", color_hue="222")
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["color_hue"] == 222

    picked = _import(client, "b.txt")
    assert picked.status_code == 200, picked.text
    assert picked.json()["color_hue"] in PRESET_HUES


def test_kb_import_mints_each_base_with_a_distinct_preset(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(kb_import.base_resume_data.settings, "base_resumes_dir", tmp_path)
    monkeypatch.setattr(
        kb_import.base_resume_render, "render_base_resume", lambda slug, db, **kw: None
    )
    for slug in ("first", "second", "third"):
        kb_import._mint_base(
            db_session, slug=slug, display_name=slug, data=SAMPLE, parse_warnings=[]
        )

    hues = [db_session.get(BaseResume, s).color_hue for s in ("first", "second", "third")]
    assert all(h in PRESET_HUES for h in hues)
    assert len(set(hues)) == 3


def test_seeding_gives_every_dropped_in_resume_its_own_preset(db_session, tmp_path, monkeypatch):
    names = [f"resume_{i}" for i in range(4)]
    for name in names:
        (tmp_path / f"{name}.json").write_text(json.dumps(SAMPLE), encoding="utf-8")
    monkeypatch.setattr(seeding.settings, "base_resumes_dir", tmp_path)
    monkeypatch.setattr(seeding.base_resume_render, "render_base_resume", lambda slug, s, **kw: None)
    _add(db_session, "existing", color_hue=PRESET_HUES[0])

    seeding.seed_base_resumes(db_session)

    hues = [db_session.get(BaseResume, n).color_hue for n in names]
    assert all(h in PRESET_HUES[1:] for h in hues)
    assert len(set(hues)) == 4


# --- identity -----------------------------------------------------------------

def test_identity_sets_the_hue_without_touching_the_document(client, db_session, renders):
    stamp = datetime(2026, 1, 2, tzinfo=timezone.utc)
    _add(db_session, "tinted", color_hue=5, pdf_path="/kept.pdf", pdf_pages=2, pdf_rendered_at=stamp)

    res = client.patch("/api/base-resumes/tinted/identity", json={"color_hue": 230})

    assert res.status_code == 200, res.text
    assert res.json()["color_hue"] == 230
    db_session.expire_all()
    row = db_session.get(BaseResume, "tinted")
    assert row.color_hue == 230
    assert row.data_json == SAMPLE
    assert row.pdf_path == "/kept.pdf" and row.pdf_pages == 2 and row.pdf_rendered_at == stamp
    assert db_session.query(ResumeVersion).count() == 0
    assert renders == []


def test_identity_leaves_the_hue_alone_when_omitted_and_clears_it_on_null(client, db_session):
    _add(db_session, "tinted", color_hue=5)

    assert client.patch("/api/base-resumes/tinted/identity", json={"company": "Acme"}).json()["color_hue"] == 5
    assert client.patch("/api/base-resumes/tinted/identity", json={"color_hue": None}).json()["color_hue"] is None


def test_identity_rejects_a_bad_hue_and_saves_none_of_the_request(client, db_session):
    _add(db_session, "tinted", color_hue=5, company="Keep")

    res = client.patch("/api/base-resumes/tinted/identity", json={"color_hue": 400, "company": "Changed"})

    assert res.status_code == 422
    db_session.expire_all()
    row = db_session.get(BaseResume, "tinted")
    assert (row.color_hue, row.company) == (5, "Keep")


def test_the_list_and_detail_carry_the_hue(client, db_session):
    _add(db_session, "tinted", color_hue=300)
    assert _hues(client)["tinted"] == 300
    assert client.get("/api/base-resumes/tinted").json()["color_hue"] == 300


# --- the migration --------------------------------------------------------------

def test_migration_backfills_live_resumes_with_distinct_presets_and_round_trips(tmp_path):
    path = tmp_path / "hues.sqlite3"
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    command.upgrade(cfg, "cf0804d00ae2")
    with closing(sqlite3.connect(path)) as db:
        for slug, deleted in [("a", None), ("b", None), ("gone", "2026-01-01 00:00:00"), ("c", None)]:
            db.execute(
                "INSERT INTO base_resumes (slug, data_json, role_category, deleted_at, created_at, updated_at)"
                " VALUES (?, '{}', 'unknown', ?, '2026-01-01 00:00:00', '2026-01-01 00:00:00')",
                (slug, deleted),
            )
        db.commit()

    command.upgrade(cfg, "head")
    with closing(sqlite3.connect(path)) as db:
        hues = dict(db.execute("SELECT slug, color_hue FROM base_resumes"))
    assert [hues[s] for s in ("a", "b", "c")] == list(PRESET_HUES[:3])
    assert hues["gone"] is None

    command.downgrade(cfg, "cf0804d00ae2")
    with closing(sqlite3.connect(path)) as db:
        assert "color_hue" not in {r[1] for r in db.execute("PRAGMA table_info(base_resumes)")}
        assert db.execute("SELECT count(*) FROM base_resumes").fetchone()[0] == 4
