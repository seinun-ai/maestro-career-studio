"""Parity proof for the consolidated op pipeline (SYSTEM.md §11 #2).

Every surface — REST edit endpoints, MCP (wrapping REST), and chat — now runs
services/resume_ops.py. These tests pin the parity so a future surface-local
'quick fix' that reintroduces drift fails loudly.
"""
import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.db import get_db
from app.main import app
from app.models.application import Application
from app.models.base_resume import BaseResume
from app.models.job import Job
from app.models.resume_version import ResumeVersion
from app.services.chat_tools import ToolContext, tool_edit_resume
from tests.ats.fixtures import SAMPLE_RESUME


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


def _seed_base(db_session, tmp_path, monkeypatch, slug):
    monkeypatch.setattr(settings, "base_resumes_dir", tmp_path)
    (tmp_path / f"{slug}.json").write_text(json.dumps(SAMPLE_RESUME))
    db_session.add(BaseResume(slug=slug, data_json=SAMPLE_RESUME))
    db_session.commit()
    return slug


_SEQ = iter(range(1000))


def _seed_application(db_session):
    job = Job(
        raw_text="jd",
        raw_text_hash=f"parity-hash-{next(_SEQ)}",
        extracted_json={"title": "DS", "company": "Acme"},
        extracted_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.commit()
    application = Application(
        job_id=job.id,
        base_resume="data_scientist",
        status="draft",
        customized_json=SAMPLE_RESUME,
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)
    return application


OPS = [{"kind": "replace_summary", "value": "Parity-checked summary."}]


def _versions(db_session, kind, key):
    return list(
        db_session.scalars(
            select(ResumeVersion)
            .where(ResumeVersion.resume_kind == kind, ResumeVersion.resume_key == key)
            .order_by(ResumeVersion.version_number)
        )
    )


def test_base_edits_rest_and_chat_produce_identical_results(
    db_session, tmp_path, monkeypatch
):
    rest_slug = _seed_base(db_session, tmp_path, monkeypatch, "parity_rest")
    chat_slug = _seed_base(db_session, tmp_path, monkeypatch, "parity_chat")

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        resp = TestClient(app).patch(
            f"/api/base-resumes/{rest_slug}/edits", json={"ops": OPS}
        )
        assert resp.status_code == 200, resp.text
    finally:
        app.dependency_overrides.clear()

    ctx = ToolContext(db=db_session, message_id="msg-1", selections=[])
    card = tool_edit_resume(ctx, "base", chat_slug, OPS)["change_card"]

    rest_row = db_session.get(BaseResume, rest_slug)
    chat_row = db_session.get(BaseResume, chat_slug)
    assert rest_row.data_json == chat_row.data_json
    # identical on-disk writes
    assert json.loads((tmp_path / f"{rest_slug}.json").read_text()) == json.loads(
        (tmp_path / f"{chat_slug}.json").read_text()
    )
    # one version each, same summary, per-surface source tags
    (rest_v,) = _versions(db_session, "base", rest_slug)[-1:]
    (chat_v,) = _versions(db_session, "base", chat_slug)[-1:]
    assert rest_v.source == "edit_ops"
    assert chat_v.source == "chat" and chat_v.source_ref == "msg-1"
    assert rest_v.summary == chat_v.summary == card["summary"]


def test_application_edits_rest_and_chat_produce_identical_results(db_session):
    app_rest = _seed_application(db_session)
    app_chat = _seed_application(db_session)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        resp = TestClient(app).patch(
            f"/api/applications/{app_rest.id}/edits", json={"ops": OPS}
        )
        assert resp.status_code == 200, resp.text
    finally:
        app.dependency_overrides.clear()

    ctx = ToolContext(db=db_session, message_id="msg-2", selections=[])
    tool_edit_resume(ctx, "application", str(app_chat.id), OPS)

    db_session.refresh(app_rest)
    db_session.refresh(app_chat)
    assert app_rest.customized_json == app_chat.customized_json
    assert app_rest.customized_json["summary"] == "Parity-checked summary."


def test_chat_base_edit_persists_render_error_like_rest(
    db_session, tmp_path, monkeypatch
):
    """Chat used to swallow render failures silently; the shared pipeline gives
    it REST's semantics — edit committed, render_error persisted."""
    slug = _seed_base(db_session, tmp_path, monkeypatch, "parity_render_fail")
    from app.services import base_resume_render, resume_ops  # noqa: PLC0415

    def boom(*a, **k):
        raise RuntimeError("pdflatex exploded")

    monkeypatch.setattr(base_resume_render, "render_base_resume", boom)
    monkeypatch.setattr(
        resume_ops.base_resume_render, "render_base_resume", boom, raising=False
    )

    ctx = ToolContext(db=db_session, message_id="msg-3", selections=[])
    tool_edit_resume(ctx, "base", slug, OPS)

    row = db_session.get(BaseResume, slug)
    assert row.data_json["summary"] == "Parity-checked summary."  # edit survived
    assert "pdflatex exploded" in (row.render_error or "")
