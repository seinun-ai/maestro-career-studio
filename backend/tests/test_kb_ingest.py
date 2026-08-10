import uuid

import pytest
from fastapi.testclient import TestClient

from app.models.career_kb import KBDocument, KBPoint


@pytest.fixture
def client(db_session):
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _fake_llm(payload):
    def fake(*, prompt, model, response_format="json", **kw):
        return payload

    return fake


def test_upload_extracts_and_mints(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.kb_ingest.settings.kb_documents_dir", tmp_path)
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _fake_llm({"points": [{"text": "Cut latency 30% via caching"}]}),
    )
    eid = client.post("/api/kb/entities", json={"kind": "project", "title": "X"}).json()["id"]
    r = client.post(
        f"/api/kb/entities/{eid}/documents",
        files={"file": ("r.md", b"# report\nwe cut latency", "text/markdown")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ingest_status"] == "minted"

    drafts = client.get("/api/kb/points?state=draft").json()
    assert drafts[0]["text"] == "Cut latency 30% via caching"
    assert drafts[0]["origin"] == "ingested"
    assert drafts[0]["source_document_id"] == body["id"]

    # original bytes are mirrored under kb_documents_dir/<id>/<filename>
    assert (tmp_path / body["id"] / "r.md").read_bytes() == b"# report\nwe cut latency"


def test_mint_skips_normalized_duplicates(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.kb_ingest.settings.kb_documents_dir", tmp_path)
    # The LLM returns the same claim with different case/whitespace; normalization
    # must fold it onto the existing approved point so no new draft is created.
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _fake_llm({"points": [{"text": "cut  LATENCY 30% via caching"}]}),
    )
    eid = client.post("/api/kb/entities", json={"kind": "project", "title": "X"}).json()["id"]
    client.post(f"/api/kb/entities/{eid}/points", json={"text": "Cut latency 30% via caching"})

    r = client.post(
        f"/api/kb/entities/{eid}/documents",
        files={"file": ("r.md", b"# report\nwe cut latency", "text/markdown")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ingest_status"] == "minted"
    assert "skipped" in body["ingest_summary"]

    drafts = client.get("/api/kb/points?state=draft").json()
    assert drafts == []


def test_upload_unextractable_marks_failed(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.kb_ingest.settings.kb_documents_dir", tmp_path)
    # No LLM patch: an unextractable upload must never reach the mint call.
    eid = client.post("/api/kb/entities", json={"kind": "project", "title": "X"}).json()["id"]
    r = client.post(
        f"/api/kb/entities/{eid}/documents",
        files={"file": ("data.xyz", b"\x00\x01\x02", "application/octet-stream")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ingest_status"] == "failed"
    assert body["ingest_summary"]  # carries the extraction failure reason

    assert client.get("/api/kb/points?state=draft").json() == []


def test_upload_filename_path_traversal_is_neutralized(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.kb_ingest.settings.kb_documents_dir", tmp_path)
    monkeypatch.setattr("app.services.llm.call_openai", _fake_llm({"points": [{"text": "p"}]}))
    eid = client.post("/api/kb/entities", json={"kind": "project", "title": "X"}).json()["id"]
    r = client.post(
        f"/api/kb/entities/{eid}/documents",
        files={"file": ("../../../../evil.md", b"hello", "text/markdown")},
    )
    assert r.status_code == 200
    body = r.json()
    # stored filename is the basename; nothing was written outside the per-doc dir
    assert body["filename"] == "evil.md"
    assert (tmp_path / body["id"] / "evil.md").exists()
    # no escape: the traversal target must NOT exist
    assert not (tmp_path.parent / "evil.md").exists()


def test_upload_corrupt_pdf_marks_failed_not_500(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.kb_ingest.settings.kb_documents_dir", tmp_path)
    eid = client.post("/api/kb/entities", json={"kind": "project", "title": "X"}).json()["id"]
    r = client.post(
        f"/api/kb/entities/{eid}/documents",
        files={"file": ("broken.pdf", b"%PDF-1.4 not really a pdf", "application/pdf")},
    )
    assert r.status_code == 200
    assert r.json()["ingest_status"] == "failed"
    assert r.json()["ingest_summary"]


def test_remint_endpoint_reruns(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _fake_llm({"points": [{"text": "Shipped feature X"}]}),
    )
    eid = client.post("/api/kb/entities", json={"kind": "project", "title": "X"}).json()["id"]
    doc = KBDocument(
        entity_id=uuid.UUID(eid),
        filename="notes.md",
        mime="text/markdown",
        text_content="we shipped feature X after weeks of work",
        ingest_status="failed",
        ingest_summary="mint failed: boom",
    )
    db_session.add(doc)
    db_session.commit()
    did = str(doc.id)

    r = client.post(f"/api/kb/documents/{did}/mint")
    assert r.status_code == 200
    assert r.json()["ingest_status"] == "minted"

    drafts = client.get("/api/kb/points?state=draft").json()
    assert any(d["text"] == "Shipped feature X" for d in drafts)


def test_capture_into_existing_entity(client, monkeypatch):
    eid = client.post("/api/kb/entities", json={"kind": "project", "title": "Orbit"}).json()["id"]
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _fake_llm({"entity_id": eid, "new_entity": None, "points": ["Added agentic retrieval"]}),
    )
    r = client.post("/api/kb/capture", json={"text": "did agentic retrieval on orbit"})
    assert r.status_code == 200
    assert r.json()["entity_id"] == eid
    drafts = client.get("/api/kb/points?state=draft").json()
    assert any(d["text"] == "Added agentic retrieval" and d["origin"] == "manual" for d in drafts)


def test_capture_proposes_new_entity_ongoing(client, monkeypatch, db_session):
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _fake_llm(
            {
                "entity_id": None,
                "new_entity": {"kind": "project", "title": "NewThing", "org": None},
                "points": ["Shipped v1"],
            }
        ),
    )
    r = client.post("/api/kb/capture", json={"text": "started NewThing, shipped v1"})
    assert r.status_code == 200
    # the created entity is ongoing
    ents = client.get("/api/kb/entities?kind=project").json()
    match = [e for e in ents if e["title"] == "NewThing"]
    assert match and match[0]["status"] == "ongoing"


def test_capture_with_entity_hint_forces_placement(client, monkeypatch):
    a = client.post("/api/kb/entities", json={"kind": "project", "title": "A"}).json()["id"]
    b = client.post("/api/kb/entities", json={"kind": "project", "title": "B"}).json()["id"]
    # even if the LLM names A, the request hint = B must win (placement forced)
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _fake_llm({"entity_id": a, "new_entity": None, "points": ["hinted point"]}),
    )
    r = client.post("/api/kb/capture", json={"text": "stuff", "entity_id": b})
    assert r.status_code == 200
    assert r.json()["entity_id"] == b


def test_capture_bad_llm_entity_id_400(client, monkeypatch):
    client.post("/api/kb/entities", json={"kind": "project", "title": "Only"})
    import uuid as _uuid

    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _fake_llm({"entity_id": str(_uuid.uuid4()), "new_entity": None, "points": ["x"]}),
    )
    r = client.post("/api/kb/capture", json={"text": "dump"})
    assert r.status_code == 400


def test_capture_missing_hint_entity_404(client, monkeypatch):
    import uuid as _uuid

    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _fake_llm({"entity_id": None, "new_entity": None, "points": []}),
    )
    r = client.post("/api/kb/capture", json={"text": "dump", "entity_id": str(_uuid.uuid4())})
    assert r.status_code == 404


def test_capture_invalid_kind_falls_back_to_project(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _fake_llm(
            {
                "entity_id": None,
                "new_entity": {"kind": "job", "title": "Acme SWE", "org": None},
                "points": ["shipped"],
            }
        ),
    )
    r = client.post("/api/kb/capture", json={"text": "joined acme, shipped"})
    assert r.status_code == 200
    ents = client.get("/api/kb/entities").json()
    match = [e for e in ents if e["title"] == "Acme SWE"]
    assert match and match[0]["kind"] == "project"


def test_capture_non_string_title_400(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _fake_llm(
            {
                "entity_id": None,
                "new_entity": {"kind": "project", "title": 123, "org": None},
                "points": ["x"],
            }
        ),
    )
    r = client.post("/api/kb/capture", json={"text": "dump"})
    assert r.status_code == 400


def test_delete_document_keeps_points_nulls_source(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.kb_ingest.settings.kb_documents_dir", tmp_path)
    monkeypatch.setattr(
        "app.services.llm.call_openai",
        _fake_llm({"points": [{"text": "Built a data pipeline"}]}),
    )
    eid = client.post("/api/kb/entities", json={"kind": "project", "title": "X"}).json()["id"]
    r = client.post(
        f"/api/kb/entities/{eid}/documents",
        files={"file": ("r.md", b"# report\nbuilt a pipeline", "text/markdown")},
    )
    did = r.json()["id"]
    drafts = client.get("/api/kb/points?state=draft").json()
    assert drafts[0]["source_document_id"] == did
    pid = uuid.UUID(drafts[0]["id"])
    # the file dir exists before deletion
    assert (tmp_path / did).exists()

    dr = client.delete(f"/api/kb/documents/{did}")
    assert dr.status_code == 204

    # The SET NULL happens at the DB level; the shared session still holds the
    # stale in-memory point, so expire it to observe the nulled FK.
    db_session.expire_all()
    point = db_session.get(KBPoint, pid)
    assert point is not None
    assert point.source_document_id is None
    # the mirrored file dir was cleaned up too
    assert not (tmp_path / did).exists()
