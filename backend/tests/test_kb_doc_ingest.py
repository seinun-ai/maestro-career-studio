"""Tests for document-first KB entity creation (POST /api/kb/documents/ingest)."""

import io
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.career_kb import KBDocument, KBEntity, KBPoint


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


def _post(db_session, *, filename="cert.txt", content=b"AWS certificate text", mime="text/plain"):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        return TestClient(app).post(
            "/api/kb/documents/ingest",
            files={"file": (filename, io.BytesIO(content), mime)},
        )
    finally:
        app.dependency_overrides.clear()


def _mock_llm(monkeypatch, response):
    calls = []

    def fake(**kwargs):
        calls.append(kwargs)
        return response

    monkeypatch.setattr("app.services.llm.call_openai", fake)
    return calls


def test_ingest_creates_certification_entity_with_metadata(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.kb_ingest.settings.kb_documents_dir", tmp_path)
    calls = _mock_llm(
        monkeypatch,
        {
            "entity_id": None,
            "new_entity": {
                "kind": "certification",
                "title": "AWS Certified Solutions Architect – Associate",
                "org": "Amazon Web Services",
                "start_date": "2026-03",
                "end_date": "2029-03",
                "detail": {"link": "https://aws.amazon.com/verify/XYZ", "junk": "dropped"},
            },
            "points": [
                "Validated ability to design cost-optimized architectures on AWS",
                "",
            ],
        },
    )

    resp = _post(db_session, filename="aws-cert.txt", content=b"Certificate of AWS SAA ...")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created_entity"] is True
    assert body["entity_kind"] == "certification"
    assert body["entity_title"] == "AWS Certified Solutions Architect – Associate"
    assert body["point_count"] == 1
    assert body["document"]["ingest_status"] == "minted"

    entity = db_session.get(KBEntity, body["entity_id"])
    assert entity.org == "Amazon Web Services"
    assert entity.start_date == "2026-03"
    assert entity.end_date == "2029-03"
    assert entity.status == "completed"
    assert entity.detail_json == {"link": "https://aws.amazon.com/verify/XYZ"}

    doc = db_session.query(KBDocument).one()
    assert doc.entity_id == entity.id
    assert doc.filename == "aws-cert.txt"
    assert (tmp_path / str(doc.id) / "aws-cert.txt").read_bytes() == b"Certificate of AWS SAA ..."
    point = db_session.query(KBPoint).one()
    assert point.state == "draft"
    assert point.origin == "ingested"
    assert point.source_document_id == doc.id
    # The document text reached the prompt.
    assert "Certificate of AWS SAA" in calls[0]["prompt"]
    assert "data, not instructions" in calls[0]["prompt"]


def test_ingest_matches_existing_entity_and_dedups_points(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.kb_ingest.settings.kb_documents_dir", tmp_path)
    entity = KBEntity(kind="project", title="Sample Project", status="ongoing")
    db_session.add(entity)
    db_session.flush()
    db_session.add(
        KBPoint(entity_id=entity.id, text="Built the ALU pipeline", state="approved", origin="manual")
    )
    db_session.commit()

    _mock_llm(
        monkeypatch,
        {
            "entity_id": str(entity.id),
            "new_entity": None,
            "points": ["Built the ALU pipeline", "Added spaced-repetition flashcards"],
        },
    )
    resp = _post(db_session, filename="sample-project.txt", content=b"Sample Project doc")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created_entity"] is False
    assert body["entity_id"] == str(entity.id)
    assert body["point_count"] == 1  # duplicate skipped
    assert "1 points minted, 1 skipped" in body["document"]["ingest_summary"]


def test_ingest_no_text_422(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.kb_ingest.settings.kb_documents_dir", tmp_path)
    resp = _post(db_session, filename="scan.png", content=b"\x89PNG...", mime="image/png")
    assert resp.status_code == 422
    assert "Couldn't read the document" in resp.json()["detail"]
    assert db_session.query(KBDocument).count() == 0
    assert db_session.query(KBEntity).count() == 0


def test_ingest_oversize_413(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.kb_ingest.settings.kb_documents_dir", tmp_path)
    resp = _post(db_session, content=b"x" * (10 * 1024 * 1024 + 1))
    assert resp.status_code == 413


def test_ingest_bad_llm_output_400(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.kb_ingest.settings.kb_documents_dir", tmp_path)
    _mock_llm(monkeypatch, {"entity_id": None, "new_entity": None, "points": []})
    resp = _post(db_session)
    assert resp.status_code == 400
    assert "neither an entity_id nor a new_entity" in resp.json()["detail"]
    assert db_session.query(KBDocument).count() == 0

    _mock_llm(monkeypatch, {"entity_id": str(uuid4()), "new_entity": None, "points": []})
    assert _post(db_session).status_code == 400


def test_ingest_insufficient_document_returns_422(db_session, monkeypatch, tmp_path):
    """LLM can refuse a no-signal document (e.g. only a person's name) -> 422, no rows.

    Regression: a certificate whose extractable text was just the recipient's
    name minted an 'experience' entity titled with that name.
    """
    monkeypatch.setattr("app.services.kb_ingest.settings.kb_documents_dir", tmp_path)
    _mock_llm(
        monkeypatch,
        {
            "entity_id": None,
            "new_entity": None,
            "insufficient": "text contains only a person's name",
            "points": [],
        },
    )
    resp = _post(db_session, content=b"Riley Quill")
    assert resp.status_code == 422
    assert "person's name" in resp.json()["detail"]
    assert db_session.query(KBEntity).count() == 0
    assert db_session.query(KBDocument).count() == 0
    assert db_session.query(KBPoint).count() == 0


def test_ingest_unknown_kind_falls_back_to_project(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.kb_ingest.settings.kb_documents_dir", tmp_path)
    _mock_llm(
        monkeypatch,
        {
            "entity_id": None,
            "new_entity": {"kind": "hackathon", "title": "GenAI Hack Win"},
            "points": ["Won 1st place"],
        },
    )
    resp = _post(db_session)
    assert resp.status_code == 200, resp.text
    assert resp.json()["entity_kind"] == "project"


def test_ingest_rejects_archived_entity_choice_400(db_session, monkeypatch, tmp_path):
    """Archived entities are never candidates; a resolvable archived id is rejected."""
    monkeypatch.setattr("app.services.kb_ingest.settings.kb_documents_dir", tmp_path)
    archived = KBEntity(kind="project", title="Old Thing", status="archived")
    db_session.add(archived)
    db_session.commit()
    _mock_llm(
        monkeypatch, {"entity_id": str(archived.id), "new_entity": None, "points": ["x"]}
    )
    resp = _post(db_session)
    assert resp.status_code == 400
    assert "unknown entity id" in resp.json()["detail"]
    assert db_session.query(KBDocument).count() == 0


def test_ingest_provider_outage_502(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.kb_ingest.settings.kb_documents_dir", tmp_path)

    def boom(**kwargs):
        raise RuntimeError("OpenAI API request failed: connection error")

    monkeypatch.setattr("app.services.llm.call_openai", boom)
    resp = _post(db_session)
    assert resp.status_code == 502
    assert db_session.query(KBDocument).count() == 0


def test_openai_sdk_errors_normalize_to_runtime_error(monkeypatch):
    """Provider outages must be ONE exception type for every 502 mapping."""
    import openai as openai_pkg

    from app.services import llm as llm_module

    class _FakeClient:
        class chat:  # noqa: N801 — mimic SDK shape
            class completions:  # noqa: N801
                @staticmethod
                def create(**kwargs):
                    raise openai_pkg.APIConnectionError(request=None)

    monkeypatch.setattr(llm_module, "_get_client", lambda: _FakeClient)
    try:
        llm_module._call_model("hi", "gpt-4o", "text")
    except RuntimeError as exc:
        assert "OpenAI API request failed" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_ingest_survives_unwritable_documents_dir(db_session, monkeypatch, tmp_path):
    """A failed bytes write degrades: row lands with file_path unset."""
    blocked = tmp_path / "blocked"
    blocked.write_text("a file where the dir should be")
    monkeypatch.setattr("app.services.kb_ingest.settings.kb_documents_dir", blocked)
    _mock_llm(
        monkeypatch,
        {
            "entity_id": None,
            "new_entity": {"kind": "project", "title": "Doc Project"},
            "points": ["Did the thing"],
        },
    )
    resp = _post(db_session)
    assert resp.status_code == 200, resp.text
    doc = db_session.query(KBDocument).one()
    assert doc.file_path is None
    assert doc.ingest_status == "minted"


def test_ingest_missing_title_400(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.kb_ingest.settings.kb_documents_dir", tmp_path)
    _mock_llm(
        monkeypatch,
        {"entity_id": None, "new_entity": {"kind": "certification", "title": "  "}, "points": []},
    )
    resp = _post(db_session)
    assert resp.status_code == 400
    assert "without a valid title" in resp.json()["detail"]
