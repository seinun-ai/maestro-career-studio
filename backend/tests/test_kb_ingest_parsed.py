"""POST /api/kb/ingest-parsed — caller-parsed resumes, KB-only, no LLM."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_db
from app.main import app
from app.models.base_resume import BaseResume
from app.models.career_kb import KBEntity, KBPoint
from app.models.setting import Setting
from app.services.kb_import import KB_SEEDED_FLAG

MCP_HEADERS = {
    "X-Maestro-CS-Origin": "mcp",
    "X-Maestro-CS-Origin-Detail": "Claude Desktop",
}


def _resume(**sections):
    base = {
        "contact": {"name": "A", "email": "a@x.com"},
        "summary": None,
        "skills": [],
        "experience": [],
        "projects": [],
        "education": [],
        "certifications": [],
    }
    base.update(sections)
    return base


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def no_llm(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("call_openai must not be invoked on ingest-parsed")
    monkeypatch.setattr("app.services.llm.call_openai", boom)


def test_ingest_parsed_happy_path_returns_ids(client, db_session, no_llm):
    payload = {
        "sources": [{
            "key": "ds_resume",
            "data": _resume(
                experience=[{
                    "company": "Acme", "role": "Engineer", "start_date": "2021",
                    "bullets": ["Shipped the pipeline"],
                }],
                projects=[{"name": "Orbit", "bullets": ["Built Orbit"]}],
            ),
        }],
    }
    r = client.post("/api/kb/ingest-parsed", json=payload, headers=MCP_HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["entities_created"] == 2
    assert len(body["entities"]) == 2
    assert {(e["kind"], e["title"], e["org"], e["created"]) for e in body["entities"]} == {
        ("experience", "Engineer", "Acme", True),
        ("project", "Orbit", None, True),
    }
    assert len(body["points"]) == 2
    assert body["points_created"] == 2
    assert {p["text"] for p in body["points"]} == {"Shipped the pipeline", "Built Orbit"}
    assert db_session.scalars(select(BaseResume)).all() == []

    # Every returned id must resolve to a real row with the right linkage.
    entity_ids = {e["id"] for e in body["entities"]}
    for item in body["points"]:
        point = db_session.get(KBPoint, item["id"])
        assert point is not None
        assert str(point.entity_id) == item["entity_id"]
        assert item["entity_id"] in entity_ids
        assert point.text == item["text"]
        assert point.state == "draft"
        assert point.approved_at is None
        assert point.origin == "mcp"
        assert point.origin_detail == "Claude Desktop"


def test_ingest_parsed_atomic_422_persists_nothing(client, db_session, no_llm):
    good = _resume(projects=[{"name": "Orbit", "bullets": ["Built Orbit"]}])
    bad = {"contact": {"name": "A"}}  # missing required email
    r = client.post("/api/kb/ingest-parsed", json={
        "sources": [
            {"key": "good", "data": good},
            {"key": "bad", "data": bad},
        ],
    })
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    # FastAPI's own shape, so a client parses one dialect for this endpoint.
    assert detail == [{
        "loc": ["body", "sources", 1, "data", "contact", "email"],
        "msg": "Field required",
        "type": "missing",
    }]
    assert db_session.scalars(select(KBEntity)).all() == []
    assert db_session.scalars(select(KBPoint)).all() == []
    assert db_session.get(Setting, KB_SEEDED_FLAG) is None


def test_ingest_parsed_ctx_bearing_validation_error_is_422_not_500(client, db_session, no_llm):
    """A ResumeData validator that raises ValueError puts the exception object
    in the pydantic error's ctx; serializing it into the 422 detail is a 500."""
    bad = _resume(extra_sections=[{
        "type": "bullets", "key": "summary", "title": "Summary", "bullets": ["x"],
    }])
    r = client.post("/api/kb/ingest-parsed", json={"sources": [{"key": "ds", "data": bad}]})
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert len(detail) == 1
    assert detail[0]["loc"][:4] == ["body", "sources", 0, "data"]
    # A validator-raised ValueError — the exact error whose ctx cannot be
    # json-serialized. The detail must carry no ctx at all.
    assert detail[0]["msg"].startswith("Value error")
    assert set(detail[0]) == {"loc", "msg", "type"}
    assert db_session.scalars(select(KBEntity)).all() == []


def test_ingest_parsed_rejects_duplicate_source_keys(client, db_session, no_llm):
    src = _resume(projects=[{"name": "Orbit", "bullets": ["Built Orbit"]}])
    r = client.post("/api/kb/ingest-parsed", json={
        "sources": [{"key": "ds", "data": src}, {"key": "ds", "data": src}],
    })
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail[0]["loc"] == ["body", "sources", 1, "key"]
    assert "duplicate source key" in detail[0]["msg"]
    assert db_session.scalars(select(KBEntity)).all() == []


def test_ingest_parsed_merge_on_rerun(client, db_session, no_llm):
    src = {"key": "ds", "data": _resume(projects=[{"name": "Orbit", "bullets": ["Built Orbit"]}])}
    first = client.post("/api/kb/ingest-parsed", json={"sources": [src]})
    second = client.post("/api/kb/ingest-parsed", json={"sources": [src]})
    assert first.status_code == second.status_code == 200
    assert first.json()["entities_created"] == 1
    assert second.json()["entities_created"] == 0
    assert second.json()["entities_matched"] == 1
    assert second.json()["points"] == []
    assert second.json()["duplicates_skipped"] == 1
    assert len(db_session.scalars(select(KBEntity)).all()) == 1
    assert len(db_session.scalars(select(KBPoint)).all()) == 1


def test_ingest_parsed_sets_kb_seeded_only_when_something_landed(client, db_session, no_llm):
    empty = client.post("/api/kb/ingest-parsed", json={
        "sources": [{"key": "ds", "data": _resume()}],
    })
    assert empty.status_code == 200, empty.text
    # A content-free ingest must not burn the one-shot seed flag.
    assert db_session.get(Setting, KB_SEEDED_FLAG) is None

    r = client.post("/api/kb/ingest-parsed", json={
        "sources": [{"key": "ds", "data": _resume(
            projects=[{"name": "Orbit", "bullets": ["Built Orbit"]}],
        )}],
    })
    assert r.status_code == 200, r.text
    row = db_session.get(Setting, KB_SEEDED_FLAG)
    assert row is not None and row.value == "1"


def test_ingest_parsed_never_calls_openai(client, no_llm):
    r = client.post("/api/kb/ingest-parsed", json={
        "sources": [{"key": "ds", "data": _resume(
            experience=[{
                "company": "Acme", "role": "Engineer", "start_date": "2021",
                "bullets": ["Did a thing"],
            }],
        )}],
    })
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("key", ["My Resume!", "_leading", "UPPER", ""])
def test_ingest_parsed_rejects_bad_key_charset(client, db_session, no_llm, key):
    r = client.post("/api/kb/ingest-parsed", json={
        "sources": [{"key": key, "data": _resume()}],
    })
    assert r.status_code == 422
    assert db_session.scalars(select(KBEntity)).all() == []


def test_ingest_parsed_forbids_unknown_body_keys(client, no_llm):
    r = client.post("/api/kb/ingest-parsed", json={
        "sources": [{"key": "ds", "data": _resume()}],
        "origin_detail": "Claude Desktop",  # provenance is a header now
    })
    assert r.status_code == 422, r.text


def test_ingest_parsed_caps_the_batch_at_twenty_sources(client, no_llm):
    sources = [{"key": f"r{i}", "data": _resume()} for i in range(21)]
    r = client.post("/api/kb/ingest-parsed", json={"sources": sources})
    assert r.status_code == 422, r.text


def test_ingest_parsed_warns_that_extra_sections_are_dropped(client, no_llm):
    r = client.post("/api/kb/ingest-parsed", json={"sources": [{
        "key": "ds",
        "data": _resume(
            projects=[{"name": "Orbit", "bullets": ["Built Orbit"]}],
            extra_sections=[{"type": "bullets", "key": "publications",
                             "title": "Publications", "bullets": ["A paper"]}],
        ),
    }]})
    assert r.status_code == 200, r.text
    warnings = r.json()["warnings"]
    assert any("extra_sections" in w for w in warnings), warnings


def test_ingest_parsed_registered_in_openapi(client):
    spec = client.get("/openapi.json").json()
    assert "/api/kb/ingest-parsed" in spec["paths"]
    assert "post" in spec["paths"]["/api/kb/ingest-parsed"]
    key_schema = spec["components"]["schemas"]["IngestParsedSource"]["properties"]["key"]
    assert key_schema["pattern"] == "^[a-z0-9][a-z0-9_]*$"


@pytest.fixture
def base_resume_side_effects(monkeypatch, tmp_path):
    """from-kb writes the resume JSON to disk and renders it; neither belongs
    in this test's blast radius."""
    from app.models.base_resume import BaseResume as _BaseResume

    monkeypatch.setattr("app.routers.base_resumes.settings.base_resumes_dir", tmp_path)
    monkeypatch.setattr(
        "app.routers.base_resumes.base_resume_render.render_base_resume",
        lambda slug, db, **kw: db.get(_BaseResume, slug),
    )


def _bullets(data: dict) -> list[str]:
    return [
        bullet
        for section in ("experience", "projects")
        for entry in data[section]
        for bullet in entry["bullets"]
    ]


def test_onboarding_round_trip_ingest_approve_compose(
    client, db_session, no_llm, base_resume_side_effects
):
    """The whole arc against real rows: ingested drafts do not compose, the
    same ids approved through bulk-state do, and the composed base carries the
    exact bullet texts that were ingested."""
    ingest = client.post("/api/kb/ingest-parsed", json={"sources": [{
        "key": "ds_resume",
        "data": _resume(
            experience=[{
                "company": "Acme", "role": "Engineer", "start_date": "2021",
                "bullets": ["Shipped the ingestion pipeline", "Owned on-call"],
            }],
            projects=[{"name": "Orbit", "bullets": ["Built Orbit"]}],
        ),
    }]}, headers=MCP_HEADERS)
    assert ingest.status_code == 200, ingest.text
    report = ingest.json()
    point_ids = [p["id"] for p in report["points"]]
    entity_ids = [e["id"] for e in report["entities"]]
    assert len(point_ids) == 3
    assert len(entity_ids) == 2

    for pid in point_ids:
        row = db_session.get(KBPoint, pid)
        assert row is not None and row.state == "draft"

    # Drafts contribute NO bullets: the entries compose as bare headers.
    probe = client.post("/api/base-resumes/from-kb", json={
        "entity_ids": entity_ids, "role_label": "Draft probe",
    })
    assert probe.status_code == 200, probe.text
    assert _bullets(probe.json()["data"]) == []

    approve = client.post("/api/kb/points/bulk-state", json={
        "ids": point_ids, "state": "approved",
    })
    assert approve.status_code == 200, approve.text
    assert [row["ok"] for row in approve.json()["results"]] == [True, True, True]
    assert {row["id"] for row in approve.json()["results"]} == set(point_ids)
    for pid in point_ids:
        db_session.expire_all()
        row = db_session.get(KBPoint, pid)
        assert row.state == "approved"
        assert row.approved_at is not None

    created = client.post("/api/base-resumes/from-kb", json={
        "entity_ids": entity_ids, "role_category": "data_scientist",
    })
    assert created.status_code == 200, created.text
    assert sorted(_bullets(created.json()["data"])) == sorted(
        ["Shipped the ingestion pipeline", "Owned on-call", "Built Orbit"]
    )
