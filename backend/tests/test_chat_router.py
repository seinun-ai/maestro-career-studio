import io
import json

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.services import chat_agent


def _client(db_session) -> TestClient:
    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_session_crud(db_session):
    client = _client(db_session)

    created = client.post("/api/chat/sessions", json={}).json()
    assert created["title"] is None

    listed = client.get("/api/chat/sessions").json()
    assert [s["id"] for s in listed] == [created["id"]]

    patched = client.patch(
        f"/api/chat/sessions/{created['id']}",
        json={"title": "Resume edits", "context": {"target_kind": "base", "target_key": "ds"}},
    ).json()
    assert patched["title"] == "Resume edits"
    assert patched["context_json"]["target_key"] == "ds"

    detail = client.get(f"/api/chat/sessions/{created['id']}").json()
    assert detail["messages"] == []

    assert client.delete(f"/api/chat/sessions/{created['id']}").status_code == 204
    assert client.get(f"/api/chat/sessions/{created['id']}").status_code == 404


def test_send_message_streams_sse(db_session, monkeypatch):
    client = _client(db_session)
    session_id = client.post("/api/chat/sessions", json={}).json()["id"]

    def fake_run_turn(db, row, content, context, **kwargs):
        assert content == "hello"
        yield {"type": "delta", "text": "hi"}
        yield {"type": "done", "session_id": str(row.id)}

    monkeypatch.setattr(chat_agent, "run_turn", fake_run_turn)

    with client.stream(
        "POST", f"/api/chat/sessions/{session_id}/messages", json={"content": "hello"}
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = "".join(resp.iter_text())

    events = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]
    assert [e["type"] for e in events] == ["delta", "done"]


def test_send_empty_message_rejected(db_session):
    client = _client(db_session)
    session_id = client.post("/api/chat/sessions", json={}).json()["id"]
    resp = client.post(f"/api/chat/sessions/{session_id}/messages", json={"content": "   "})
    assert resp.status_code == 400


def test_upload_attachment_md(db_session):
    client = _client(db_session)
    session_id = client.post("/api/chat/sessions", json={}).json()["id"]

    resp = client.post(
        f"/api/chat/sessions/{session_id}/attachments",
        files={"file": ("notes.md", io.BytesIO(b"# Churn project\nCut churn 12%"), "text/markdown")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["filename"] == "notes.md"
    assert "Churn project" in body["preview"]

    bad = client.post(
        f"/api/chat/sessions/{session_id}/attachments",
        files={"file": ("x.png", io.BytesIO(b"\x89PNG"), "image/png")},  # corrupt image bytes
    )
    assert bad.status_code == 400


def test_upload_attachment_certificate_pdf_stores_transcript(db_session, monkeypatch):
    """Image-based certificate PDFs reach the chat model as a real transcript,
    not just the recipient-name text layer."""
    from tests.pdf_fixtures import image_pdf_bytes

    data = image_pdf_bytes("Riley Quill")

    monkeypatch.setattr(
        "app.services.llm.call_openai",
        lambda **kwargs: "Certificate of Completion\nAnthropic Academy",
    )
    monkeypatch.setattr(
        "app.services.model_settings.get_fast_model", lambda session=None: "fast-model"
    )

    client = _client(db_session)
    session_id = client.post("/api/chat/sessions", json={}).json()["id"]
    resp = client.post(
        f"/api/chat/sessions/{session_id}/attachments",
        files={"file": ("certificate.pdf", io.BytesIO(data), "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "Anthropic Academy" in body["preview"]

    from app.models.chat import ChatAttachment

    row = db_session.get(ChatAttachment, body["id"])
    assert "Anthropic Academy" in row.text_content
    assert "Riley Quill" in row.text_content
